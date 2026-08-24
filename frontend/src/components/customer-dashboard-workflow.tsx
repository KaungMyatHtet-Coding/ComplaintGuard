"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
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
import type { ComplaintAttempt, ComplaintSuccess } from "@/lib/complaint-submission";

async function currentToken(): Promise<string> {
  const user = getFirebaseServices().auth.currentUser;
  if (!user) throw new Error("Unauthenticated");
  return user.getIdToken();
}

export function CustomerDashboardWorkflow() {
  const { locale, profile, t } = useApp();
  const [isComposeOpen, setIsComposeOpen] = useState(false);
  const [tickets, setTickets] = useState<CustomerTicketSummary[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [ticketDetail, setTicketDetail] = useState<CustomerTicketDetail | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submissionAttempt, setSubmissionAttempt] = useState<ComplaintAttempt | null>(null);
  const listRequestRef = useRef(0);
  const detailRequestRef = useRef(0);
  const selectedTicketRef = useRef<string | null>(null);
  const confirmedComplaintRef = useRef<{ sessionUid: string; complaintId: string } | null>(null);
  const sessionUid = profile?.role === "customer" && profile.active ? profile.uid : null;

  useEffect(() => {
    selectedTicketRef.current = selectedTicketId;
  }, [selectedTicketId]);

  useEffect(() => {
    listRequestRef.current += 1;
    detailRequestRef.current += 1;
    queueMicrotask(() => {
      setTickets([]);
      setSelectedTicketId(null);
      setTicketDetail(null);
      setError(null);
      setSubmissionAttempt(null);
      confirmedComplaintRef.current = null;
    });
  }, [sessionUid]);

  const loadTickets = useCallback(async (preferredTicketId?: string) => {
    if (!sessionUid) return;
    const requestId = ++listRequestRef.current;
    const requestSessionUid = sessionUid;
    setLoadingList(true);
    setError(null);
    try {
      const idToken = await currentToken();
      if (!idToken) throw new Error("No token");
      const list = await fetchCustomerTickets(idToken);
      if (
        requestId !== listRequestRef.current ||
        sessionUid !== requestSessionUid ||
        profile?.uid !== requestSessionUid ||
        getFirebaseServices().auth.currentUser?.uid !== requestSessionUid
      ) return;
      setTickets(list);
      const confirmed = confirmedComplaintRef.current;
      const requestedId = preferredTicketId ?? (
        confirmed?.sessionUid === requestSessionUid ? confirmed.complaintId : undefined
      );
      const nextId = requestedId && list.some((ticket) => ticket.id === requestedId)
        ? requestedId
        : selectedTicketRef.current && list.some((ticket) => ticket.id === selectedTicketRef.current)
          ? selectedTicketRef.current
          : list[0]?.id ?? null;
      setSelectedTicketId(nextId);
      if (confirmed?.sessionUid === requestSessionUid && list.some((ticket) => ticket.id === confirmed.complaintId)) {
        confirmedComplaintRef.current = null;
      }
    } catch {
      if (requestId === listRequestRef.current && sessionUid === requestSessionUid && profile?.uid === requestSessionUid) {
        setError(t("customerLoadError"));
      }
    } finally {
      if (requestId === listRequestRef.current) setLoadingList(false);
    }
  }, [profile, sessionUid, t]);

  const loadTicketDetail = useCallback(
    async (ticketId: string) => {
      if (!sessionUid) return;
      const requestId = ++detailRequestRef.current;
      const requestSessionUid = sessionUid;
      setLoadingDetail(true);
      setError(null);
      try {
        const idToken = await currentToken();
        if (!idToken) throw new Error("No token");
        const detail = await fetchCustomerTicketDetail(ticketId, idToken);
        if (
          requestId !== detailRequestRef.current ||
          selectedTicketRef.current !== ticketId ||
          sessionUid !== requestSessionUid ||
          profile?.uid !== requestSessionUid ||
          getFirebaseServices().auth.currentUser?.uid !== requestSessionUid
        ) return;
        setTicketDetail(detail);
      } catch {
        if (requestId === detailRequestRef.current && sessionUid === requestSessionUid && profile?.uid === requestSessionUid) {
          setError(t("customerDetailLoadError"));
        }
      } finally {
        if (requestId === detailRequestRef.current) setLoadingDetail(false);
      }
    },
    [profile, sessionUid, t]
  );

  useEffect(() => {
    const requestedTicket = new URLSearchParams(window.location.search).get("ticketRef");
    if (requestedTicket && /^[A-Za-z0-9_-]{1,128}$/.test(requestedTicket)) {
      queueMicrotask(() => setSelectedTicketId(requestedTicket));
    }
  }, []);

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

  const handleComplaintSuccess = useCallback((result: ComplaintSuccess) => {
    if (!sessionUid || profile?.role !== "customer" || !profile.active || profile.uid !== sessionUid || getFirebaseServices().auth.currentUser?.uid !== sessionUid) return;
    confirmedComplaintRef.current = { sessionUid, complaintId: result.complaintId };
    setSubmissionAttempt(null);
    setIsComposeOpen(false);
    void loadTickets(result.complaintId);
  }, [loadTickets, profile, sessionUid]);

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
      <div id="new-complaint" className="cust-page-header-row">
        <div />
        <button type="button" className="cust-compose-submit" onClick={() => setIsComposeOpen(true)}>
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
            {sessionUid ? (
              <ComplaintForm
                sessionUid={sessionUid}
                attempt={submissionAttempt}
                onAttemptChange={setSubmissionAttempt}
                onSuccess={handleComplaintSuccess}
                hideTitle={true}
              />
            ) : null}
          </div>
        </div>
      )}

      {/* Master-detail: sidebar list + detail */}
      <div className="cust-split">
        <aside id="complaint-history" className="cust-sidebar">
          <CustomerTicketHistory
            locale={locale}
            tickets={tickets}
            selectedTicketId={selectedTicketId}
            onSelectTicket={(id) => {
              selectedTicketRef.current = id;
              setTicketDetail(null);
              setSelectedTicketId(id);
            }}
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
