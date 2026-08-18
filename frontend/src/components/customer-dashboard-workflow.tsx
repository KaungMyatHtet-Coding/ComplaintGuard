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
  CustomerWorkflowError,
  type CustomerTicketDetail,
  type CustomerTicketSummary,
} from "@/lib/customer-workflow";

async function currentToken(): Promise<string> {
  const user = getFirebaseServices().auth.currentUser;
  if (!user) throw new Error("Unauthenticated");
  return user.getIdToken();
}

export function CustomerDashboardWorkflow() {
  const { locale, t } = useApp();
  const [isComposeOpen, setIsComposeOpen] = useState(false);
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
      setError(t("customerLoadError"));
    } finally {
      setLoadingList(false);
    }
  }, [selectedTicketId, t]);

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
        setError(t("customerDetailLoadError"));
      } finally {
        setLoadingDetail(false);
      }
    },
    [t]
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
    try {
      await submitCustomerFeedback(selectedTicketId, rating, comments, idToken);
      await loadTicketDetail(selectedTicketId);
    } catch (error) {
      if (error instanceof CustomerWorkflowError && error.code === "conflict") {
        await loadTicketDetail(selectedTicketId);
      }
      throw error;
    }
  };

  return (
    <div className="cust-layout">
      {/* Top action bar and title */}
      <div className="cust-page-header-row">
        <div className="cust-page-header">
          <h1>Dashboard</h1>
          <span>customer</span>
        </div>
        <button className="cust-compose-submit" onClick={() => setIsComposeOpen(true)}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          New Complaint
        </button>
      </div>

      {isComposeOpen && (
        <div className="cust-modal-overlay">
          <div className="cust-modal-content">
            <div className="cust-modal-header">
              <h2 className="cust-compose-title" style={{ margin: 0 }}>
                {t("complaintTitle")}
              </h2>
              <button className="icon-button" onClick={() => setIsComposeOpen(false)}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
            <ComplaintForm onSuccess={loadTickets} hideTitle={true} />
          </div>
        </div>
      )}

      {/* Master-detail: sidebar list + detail */}
      <div className="cust-split">
        <aside className="cust-sidebar">
          <CustomerTicketHistory
            locale={locale}
            tickets={tickets}
            selectedTicketId={selectedTicketId}
            onSelectTicket={(id) => setSelectedTicketId(id)}
            loading={loadingList}
            error={error}
            onRefresh={loadTickets}
          />
        </aside>
        <CustomerTicketDetailView
          locale={locale}
          ticket={ticketDetail}
          loading={loadingDetail}
          onSendMessage={handleSendMessage}
          onSubmitFeedback={handleSubmitFeedback}
        />
      </div>
    </div>
  );
}
