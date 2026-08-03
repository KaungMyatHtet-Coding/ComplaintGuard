"use client";

import { useCallback, useEffect, useState } from "react";
import { useApp } from "@/components/app-provider";
import { ComplaintForm } from "@/components/complaint-form";
import { CustomerTicketDetailView } from "@/components/customer-ticket-detail";
import { CustomerTicketHistory } from "@/components/customer-ticket-history";
import { getFirebaseServices } from "@/lib/firebase";
import {
  type CustomerTicketDetail,
  type CustomerTicketSummary,
  fetchCustomerTicketDetail,
  fetchCustomerTickets,
  postCustomerMessage,
  submitCustomerFeedback,
} from "@/lib/customer-workflow";

async function currentToken() {
  const user = getFirebaseServices().auth.currentUser;
  if (!user) return null;
  return user.getIdToken();
}

export function CustomerDashboardWorkflow() {
  const { t } = useApp();
  const [tickets, setTickets] = useState<CustomerTicketSummary[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [ticketDetail, setTicketDetail] = useState<CustomerTicketDetail | null>(null);
  const [loadingList, setLoadingList] = useState(true);
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
      setError(t("customerLoadError"));
    } finally {
      setLoadingList(false);
    }
  }, [selectedTicketId, t]);

  const loadDetail = useCallback(async (ticketId: string) => {
    try {
      const idToken = await currentToken();
      if (!idToken) return;
      const detail = await fetchCustomerTicketDetail(idToken, ticketId);
      setTicketDetail(detail);
    } catch {
      // Ignore
    }
  }, []);

  useEffect(() => {
    queueMicrotask(() => {
      void loadTickets();
    });
  }, [loadTickets]);

  useEffect(() => {
    if (selectedTicketId) {
      queueMicrotask(() => {
        void loadDetail(selectedTicketId);
      });
    }
  }, [selectedTicketId, loadDetail]);

  const handleSendMessage = async (text: string) => {
    if (!selectedTicketId) return;
    const idToken = await currentToken();
    if (!idToken) return;
    await postCustomerMessage(idToken, selectedTicketId, text);
    await loadDetail(selectedTicketId);
  };

  const handleSubmitFeedback = async (rating: number, comments: string) => {
    if (!selectedTicketId) return;
    const idToken = await currentToken();
    if (!idToken) return;
    await submitCustomerFeedback(idToken, selectedTicketId, rating, comments);
    await loadDetail(selectedTicketId);
  };

  return (
    <div className="space-y-8 mt-6">
      <ComplaintForm />

      <hr className="border-gray-200" />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-1">
          {loadingList ? (
            <div className="p-8 text-center space-y-2">
              <div className="spinner mx-auto" />
              <p className="text-xs text-gray-500">{t("loading")}</p>
            </div>
          ) : (
            <CustomerTicketHistory
              tickets={tickets}
              selectedTicketId={selectedTicketId}
              onSelectTicket={(id) => setSelectedTicketId(id)}
              onRefresh={() => void loadTickets()}
            />
          )}

          {error && (
            <div className="p-3 bg-red-50 text-red-700 text-xs font-semibold rounded-xl border border-red-200 mt-3">
              {error}
            </div>
          )}
        </div>

        <div className="lg:col-span-2">
          {ticketDetail ? (
            <CustomerTicketDetailView
              detail={ticketDetail}
              onSendMessage={handleSendMessage}
              onSubmitFeedback={handleSubmitFeedback}
            />
          ) : (
            <div className="p-8 bg-white rounded-2xl border border-gray-200 text-center text-xs text-gray-500">
              Select a complaint ticket to view details and status.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
