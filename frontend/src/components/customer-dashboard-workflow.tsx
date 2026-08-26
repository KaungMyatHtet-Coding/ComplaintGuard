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
  normalizeCustomerMessageText,
  sendCustomerMessage,
  submitCustomerFeedback,
  CustomerWorkflowError,
  type CustomerDepartmentId,
  type CustomerTicketDetail,
  type CustomerTicketStatus,
  type CustomerTicketSummary,
} from "@/lib/customer-workflow";
import type { ComplaintAttempt, ComplaintSuccess } from "@/lib/complaint-submission";

async function currentToken(forceRefresh = false): Promise<string> {
  const user = getFirebaseServices().auth.currentUser;
  if (!user) throw new Error("Unauthenticated");
  return user.getIdToken(forceRefresh);
}

type CustomerMessageAttempt = {
  sessionUid: string;
  ticketId: string;
  normalizedText: string;
  actionId: string;
};

export function CustomerDashboardWorkflow() {
  const { locale, profile, t } = useApp();
  const [isComposeOpen, setIsComposeOpen] = useState(false);
  const [tickets, setTickets] = useState<CustomerTicketSummary[]>([]);
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null);
  const [ticketDetail, setTicketDetail] = useState<CustomerTicketDetail | null>(null);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [loadMoreError, setLoadMoreError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submissionAttempt, setSubmissionAttempt] = useState<ComplaintAttempt | null>(null);
  const [statusFilter, setStatusFilter] = useState<CustomerTicketStatus | null>(null);
  const [departmentFilter, setDepartmentFilter] = useState<CustomerDepartmentId | null>(null);
  const listRequestRef = useRef(0);
  const listAbortRef = useRef<AbortController | null>(null);
  const loadingMoreRef = useRef(false);
  const detailRequestRef = useRef(0);
  const detailAbortRef = useRef<AbortController | null>(null);
  const messageAbortRef = useRef<AbortController | null>(null);
  const messageAttemptRef = useRef<CustomerMessageAttempt | null>(null);
  const messageInFlightRef = useRef(false);
  const selectedTicketRef = useRef<string | null>(null);
  const pendingFilterSelectionRef = useRef<string | null>(null);
  const confirmedComplaintRef = useRef<{ sessionUid: string; complaintId: string } | null>(null);
  const composeOpenerRef = useRef<HTMLButtonElement | null>(null);
  const composeOpenerSessionRef = useRef<string | null>(null);
  const composeDialogRef = useRef<HTMLDivElement | null>(null);
  const sessionUid = profile?.role === "customer" && profile.active ? profile.uid : null;

  const closeCompose = useCallback(() => {
    setIsComposeOpen(false);
  }, []);

  const restoreComposeFocus = useCallback(() => {
    const opener = composeOpenerRef.current;
    if (opener && opener.isConnected && composeOpenerSessionRef.current === sessionUid) {
      opener.focus();
    }
    composeOpenerRef.current = null;
    composeOpenerSessionRef.current = null;
  }, [sessionUid]);

  useEffect(() => {
    if (isComposeOpen) {
      const textarea = composeDialogRef.current?.querySelector<HTMLTextAreaElement>("textarea");
      textarea?.focus();
      return;
    }
    restoreComposeFocus();
  }, [isComposeOpen, restoreComposeFocus]);

  useEffect(() => () => {
    composeOpenerRef.current = null;
    composeOpenerSessionRef.current = null;
  }, []);

  useEffect(() => {
    if (isComposeOpen && composeOpenerSessionRef.current !== sessionUid) {
      composeOpenerRef.current = null;
      composeOpenerSessionRef.current = null;
      setIsComposeOpen(false);
    }
  }, [isComposeOpen, sessionUid]);

  function handleComposeKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeCompose();
      return;
    }
    if (event.key !== "Tab") return;
    const dialog = composeDialogRef.current;
    if (!dialog) return;
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      ),
    ).filter((element) => element.isConnected && element.getClientRects().length > 0);
    if (!focusable.length) {
      event.preventDefault();
      dialog.focus();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    const active = dialog.ownerDocument.activeElement;
    if (event.shiftKey && active === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && active === last) {
      event.preventDefault();
      first.focus();
    }
  }

  useEffect(() => {
    selectedTicketRef.current = selectedTicketId;
  }, [selectedTicketId]);

  useEffect(() => {
    listRequestRef.current += 1;
    detailRequestRef.current += 1;
    listAbortRef.current?.abort();
    detailAbortRef.current?.abort();
    listAbortRef.current = null;
    detailAbortRef.current = null;
    selectedTicketRef.current = null;
    pendingFilterSelectionRef.current = null;
    queueMicrotask(() => {
      setTickets([]);
      setSelectedTicketId(null);
      setTicketDetail(null);
      setError(null);
      setLoadMoreError(null);
      setNextCursor(null);
      setHasMore(false);
      loadingMoreRef.current = false;
      setLoadingList(false);
      setLoadingMore(false);
      setLoadingDetail(false);
      setSubmissionAttempt(null);
      confirmedComplaintRef.current = null;
      messageAbortRef.current?.abort();
      messageAbortRef.current = null;
      messageAttemptRef.current = null;
      messageInFlightRef.current = false;
      setStatusFilter(null);
      setDepartmentFilter(null);
    });
  }, [sessionUid]);

  useEffect(() => {
    messageAbortRef.current?.abort();
    messageAbortRef.current = null;
    messageAttemptRef.current = null;
    messageInFlightRef.current = false;
  }, [selectedTicketId]);

  useEffect(() => () => {
    messageAbortRef.current?.abort();
  }, []);

  const loadTickets = useCallback(async (preferredTicketId?: string) => {
    if (!sessionUid) return;
    listAbortRef.current?.abort();
    const requestId = ++listRequestRef.current;
    const requestSessionUid = sessionUid;
    const requestStatus = statusFilter;
    const requestDepartment = departmentFilter;
    const controller = new AbortController();
    listAbortRef.current = controller;
    loadingMoreRef.current = false;
    setLoadingMore(false);
    setLoadingList(true);
    setError(null);
    setLoadMoreError(null);
    try {
      const idToken = await currentToken();
      if (!idToken) throw new Error("No token");
      const page = await fetchCustomerTickets(idToken, {
        pageSize: 25,
        status: requestStatus,
        departmentId: requestDepartment,
        signal: controller.signal,
      });
      if (
        requestId !== listRequestRef.current ||
        controller.signal.aborted ||
        sessionUid !== requestSessionUid ||
        profile?.uid !== requestSessionUid ||
        getFirebaseServices().auth.currentUser?.uid !== requestSessionUid
        || statusFilter !== requestStatus
        || departmentFilter !== requestDepartment
      ) return;
      setTickets(page.tickets);
      setNextCursor(page.nextCursor);
      setHasMore(page.hasMore);
      const confirmed = confirmedComplaintRef.current;
      const preservedSelection = pendingFilterSelectionRef.current;
      pendingFilterSelectionRef.current = null;
      const requestedId = preferredTicketId ?? (
        confirmed?.sessionUid === requestSessionUid ? confirmed.complaintId : undefined
      );
      const nextId = requestedId
        ? (page.tickets.some((ticket) => ticket.complaintId === requestedId) ? requestedId : null)
        : (preservedSelection ?? selectedTicketRef.current) && page.tickets.some(
          (ticket) => ticket.complaintId === (preservedSelection ?? selectedTicketRef.current),
        )
          ? preservedSelection ?? selectedTicketRef.current
          : page.tickets[0]?.complaintId ?? null;
      setSelectedTicketId(nextId);
      if (confirmed?.sessionUid === requestSessionUid && page.tickets.some((ticket) => ticket.complaintId === confirmed.complaintId)) {
        confirmedComplaintRef.current = null;
      }
    } catch {
      if (!controller.signal.aborted && requestId === listRequestRef.current && sessionUid === requestSessionUid && profile?.uid === requestSessionUid) {
        setError(t("customerLoadError"));
      }
    } finally {
      if (requestId === listRequestRef.current) {
        setLoadingList(false);
        if (listAbortRef.current === controller) listAbortRef.current = null;
      }
    }
  }, [departmentFilter, profile, sessionUid, statusFilter, t]);

  const loadMoreTickets = useCallback(async () => {
    if (!sessionUid || loadingList || loadingMoreRef.current || !hasMore || !nextCursor) return;
    const requestId = listRequestRef.current;
    const requestSessionUid = sessionUid;
    const requestStatus = statusFilter;
    const requestDepartment = departmentFilter;
    const requestCursor = nextCursor;
    const controller = new AbortController();
    listAbortRef.current = controller;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    setLoadMoreError(null);
    try {
      const idToken = await currentToken();
      const page = await fetchCustomerTickets(idToken, {
        pageSize: 25,
        cursor: requestCursor,
        status: requestStatus,
        departmentId: requestDepartment,
        signal: controller.signal,
      });
      if (
        controller.signal.aborted
        || requestId !== listRequestRef.current
        || sessionUid !== requestSessionUid
        || profile?.uid !== requestSessionUid
        || getFirebaseServices().auth.currentUser?.uid !== requestSessionUid
        || nextCursor !== requestCursor
        || statusFilter !== requestStatus
        || departmentFilter !== requestDepartment
      ) return;
      setTickets((current) => {
        const seen = new Set(current.map((ticket) => ticket.complaintId));
        return [...current, ...page.tickets.filter((ticket) => !seen.has(ticket.complaintId))];
      });
      setNextCursor(page.nextCursor);
      setHasMore(page.hasMore);
    } catch {
      if (!controller.signal.aborted && requestId === listRequestRef.current) setLoadMoreError(t("customerLoadError"));
    } finally {
      if (requestId === listRequestRef.current) {
        setLoadingMore(false);
        loadingMoreRef.current = false;
        if (listAbortRef.current === controller) listAbortRef.current = null;
      }
    }
  }, [departmentFilter, hasMore, loadingList, nextCursor, profile, sessionUid, statusFilter, t]);

  const changeFilters = useCallback((nextStatus: CustomerTicketStatus | null, nextDepartment: CustomerDepartmentId | null) => {
    if (nextStatus === statusFilter && nextDepartment === departmentFilter) return;
    listRequestRef.current += 1;
    detailRequestRef.current += 1;
    listAbortRef.current?.abort();
    detailAbortRef.current?.abort();
    listAbortRef.current = null;
    detailAbortRef.current = null;
    loadingMoreRef.current = false;
    pendingFilterSelectionRef.current = pendingFilterSelectionRef.current ?? selectedTicketRef.current;
    setStatusFilter(nextStatus);
    setDepartmentFilter(nextDepartment);
    setTickets([]);
    setSelectedTicketId(null);
    setTicketDetail(null);
    setNextCursor(null);
    setHasMore(false);
    setLoadMoreError(null);
    setError(null);
    setLoadingList(false);
    setLoadingMore(false);
    setLoadingDetail(false);
  }, [departmentFilter, statusFilter]);

  const loadTicketDetail = useCallback(
    async (ticketId: string) => {
      if (!sessionUid) return;
      detailAbortRef.current?.abort();
      const requestId = ++detailRequestRef.current;
      const requestSessionUid = sessionUid;
      const controller = new AbortController();
      detailAbortRef.current = controller;
      setLoadingDetail(true);
      setError(null);
      try {
        const idToken = await currentToken();
        if (!idToken) throw new Error("No token");
        const detail = await fetchCustomerTicketDetail(ticketId, idToken, fetch, controller.signal);
        if (
          requestId !== detailRequestRef.current ||
          controller.signal.aborted ||
          selectedTicketRef.current !== ticketId ||
          sessionUid !== requestSessionUid ||
          profile?.uid !== requestSessionUid ||
          getFirebaseServices().auth.currentUser?.uid !== requestSessionUid
        ) return;
        setTicketDetail(detail);
      } catch {
        if (!controller.signal.aborted && requestId === detailRequestRef.current && sessionUid === requestSessionUid && profile?.uid === requestSessionUid) {
          setError(t("customerDetailLoadError"));
        }
      } finally {
      if (requestId === detailRequestRef.current) {
        setLoadingDetail(false);
        if (detailAbortRef.current === controller) detailAbortRef.current = null;
      }
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
    closeCompose();
    void loadTickets(result.complaintId);
  }, [closeCompose, loadTickets, profile, sessionUid]);

  const handleSendMessage = async (text: string) => {
    if (!selectedTicketId || !sessionUid || messageInFlightRef.current) {
      throw new CustomerWorkflowError("aborted");
    }
    const normalizedText = normalizeCustomerMessageText(text);
    if (!normalizedText) throw new CustomerWorkflowError("validation");
    const previous = messageAttemptRef.current;
    const attempt = previous
      && previous.sessionUid === sessionUid
      && previous.ticketId === selectedTicketId
      && previous.normalizedText === normalizedText
      ? previous
      : {
        sessionUid,
        ticketId: selectedTicketId,
        normalizedText,
        actionId: crypto.randomUUID(),
      };
    messageAttemptRef.current = attempt;
    const controller = new AbortController();
    messageAbortRef.current = controller;
    messageInFlightRef.current = true;
    try {
      let idToken: string;
      try { idToken = await currentToken(true); }
      catch { throw new CustomerWorkflowError("auth"); }
      await sendCustomerMessage(
        selectedTicketId,
        normalizedText,
        idToken,
        fetch,
        attempt.actionId,
        controller.signal,
      );
      if (
        controller.signal.aborted
        || sessionUid !== attempt.sessionUid
        || selectedTicketRef.current !== attempt.ticketId
        || getFirebaseServices().auth.currentUser?.uid !== attempt.sessionUid
      ) return;
      await loadTicketDetail(attempt.ticketId);
      messageAttemptRef.current = null;
    } catch (error) {
      if (!(error instanceof CustomerWorkflowError) || error.code !== "unknown") {
        messageAttemptRef.current = null;
      }
      throw error;
    } finally {
      messageInFlightRef.current = false;
      if (messageAbortRef.current === controller) messageAbortRef.current = null;
    }
  };

  const cancelMessageAttempt = useCallback(() => {
    messageAbortRef.current?.abort();
    messageAbortRef.current = null;
  }, []);

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
        <button
          type="button"
          className="cust-compose-submit"
          onClick={(event) => {
            composeOpenerRef.current = event.currentTarget;
            composeOpenerSessionRef.current = sessionUid;
            setIsComposeOpen(true);
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <line x1="12" y1="5" x2="12" y2="19"></line>
            <line x1="5" y1="12" x2="19" y2="12"></line>
          </svg>
          New Complaint
        </button>
      </div>

      {isComposeOpen && (
        <div
          className="cust-modal-overlay"
          onClick={(event) => {
            if (event.target === event.currentTarget) closeCompose();
          }}
        >
          <div
            className="cust-modal-content"
            role="dialog"
            aria-modal="true"
            aria-labelledby="complaint-modal-title"
            ref={composeDialogRef}
            tabIndex={-1}
            onKeyDown={handleComposeKeyDown}
          >
            <div className="cust-modal-header">
              <h2 id="complaint-modal-title" className="cust-compose-title" style={{ margin: 0 }}>
                {t("complaintTitle")}
              </h2>
              <button
                type="button"
                className="icon-button"
                aria-label={t("closeComplaintDialog")}
                onClick={closeCompose}
              >
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
            loadingMore={loadingMore}
            loadMoreError={loadMoreError}
            hasMore={hasMore}
            onLoadMore={loadMoreTickets}
            statusFilter={statusFilter}
            departmentFilter={departmentFilter}
            onFilterChange={changeFilters}
          />
        </aside>
        <CustomerTicketDetailView
          key={`${sessionUid ?? "none"}:${selectedTicketId ?? "none"}`}
          locale={locale}
          ticket={ticketDetail}
          loading={loadingDetail}
          onSendMessage={handleSendMessage}
          onCancelMessage={cancelMessageAttempt}
          onSubmitFeedback={handleSubmitFeedback}
        />
      </div>
    </div>
  );
}
