"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useApp } from "@/components/app-provider";
import { ComplaintForm } from "@/components/complaint-form";
import { CustomerTicketHistory } from "@/components/customer-ticket-history";
import { CustomerTicketDetailView } from "@/components/customer-ticket-detail";
import { getFirebaseServices } from "@/lib/firebase";
import {
  fetchCustomerTickets,
  fetchCustomerTicketDetail,
  sendCustomerMessage,
  submitCustomerFeedback,
  type CustomerTicketDetail,
  type CustomerTicketSummary,
} from "@/lib/customer-workflow";

async function currentToken(): Promise<string> {
  const user = getFirebaseServices().auth.currentUser;
  if (!user) throw new Error("Unauthenticated");
  return user.getIdToken();
}

export function CustomerDashboardWorkflow() {
  const { locale } = useApp();
  const [tickets, setTickets] = useState<CustomerTicketSummary[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [ticketDetail, setTicketDetail] = useState<CustomerTicketDetail | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadTickets = useCallback(async () => {
    setLoadingList(true);
    setError(null);
    try {
      const idToken = await currentToken();
      if (!idToken) throw new Error("No token");
      const list = await fetchCustomerTickets(idToken);
      setTickets(list);
      if (list.length > 0 && !selectedTicketId) {
        setSelectedTicketId(list[0].id);
      }
    } catch {
      setError("Failed to load your complaint history.");
    } finally {
      setLoadingList(false);
    }
  }, [selectedTicketId]);

  const loadTicketDetail = useCallback(
    async (ticketId: string) => {
      setLoadingDetail(true);
      setError(null);
      try {
        const idToken = await currentToken();
        if (!idToken) throw new Error("No token");
        const detail = await fetchCustomerTicketDetail(ticketId, idToken);
        setTicketDetail(detail);
      } catch {
        setError("Failed to load complaint detail.");
      } finally {
        setLoadingDetail(false);
      }
    },
    []
  );

  useEffect(() => {
    queueMicrotask(() => void loadTickets());
  }, [loadTickets]);

  useEffect(() => {
    if (selectedTicketId) {
      queueMicrotask(() => void loadTicketDetail(selectedTicketId));
    } else {
      queueMicrotask(() => setTicketDetail(null));
    }
  }, [selectedTicketId, loadTicketDetail]);

  const handleSendMessage = async (text: string) => {
    if (!selectedTicketId) return;
    const idToken = await currentToken();
    if (!idToken) return;
    await sendCustomerMessage(selectedTicketId, text, idToken);
    await loadTicketDetail(selectedTicketId);
  };

  const handleSubmitFeedback = async (rating: number, comments: string) => {
    if (!selectedTicketId) return;
    const idToken = await currentToken();
    if (!idToken) return;
    await submitCustomerFeedback(selectedTicketId, rating, comments, idToken);
    await loadTicketDetail(selectedTicketId);
  };

  return (
    <div className="space-y-8 max-w-6xl mx-auto">
      {/* Complaint Submission Section */}
      <ComplaintForm />

      {/* History and Detail Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 pt-4 border-t border-gray-200">
        <div className="lg:col-span-1">
          <CustomerTicketHistory
            locale={locale}
            tickets={tickets}
            selectedTicketId={selectedTicketId}
            onSelectTicket={(id) => setSelectedTicketId(id)}
            loading={loadingList}
            error={error}
            onRefresh={loadTickets}
          />
        </div>
        <div className="lg:col-span-2">
          <CustomerTicketDetailView
            locale={locale}
            ticket={ticketDetail}
            loading={loadingDetail}
            onSendMessage={handleSendMessage}
            onSubmitFeedback={handleSubmitFeedback}
          />
        </div>
      </div>
    </div>
  );
}
