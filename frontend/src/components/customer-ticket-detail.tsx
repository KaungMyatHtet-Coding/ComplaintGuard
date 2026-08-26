"use client";

import React, { useEffect, useId, useRef, useState } from "react";
import { CustomerFeedbackPanel } from "@/components/customer-feedback-panel";
import type { Locale, MessageKey } from "@/lib/i18n";
import { translate } from "@/lib/i18n";
import {
  CustomerWorkflowError,
  type CustomerTicketDetail,
  type CustomerTicketStatus,
  type CustomerTimelineType,
} from "@/lib/customer-workflow";

type CustomerTicketDetailProps = {
  locale: Locale;
  ticket: CustomerTicketDetail | null;
  loading: boolean;
  onSendMessage: (text: string) => Promise<void>;
  onCancelMessage: () => void;
  onSubmitFeedback: (rating: number, comments: string) => Promise<void>;
};

export function CustomerTicketDetailView({
  locale,
  ticket,
  loading,
  onSendMessage,
  onCancelMessage,
  onSubmitFeedback,
}: CustomerTicketDetailProps) {
  const [messageText, setMessageText] = useState("");
  const [sendingMsg, setSendingMsg] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);
  const messageDialogRef = useRef<HTMLDivElement>(null);
  const messageOpenerRef = useRef<HTMLButtonElement>(null);
  const messageOpenerTicketIdRef = useRef<string | null>(null);
  const messageDialogTitleId = useId();

  useEffect(() => () => {
    onCancelMessage();
  }, [onCancelMessage]);

  useEffect(() => {
    if (messageOpenerTicketIdRef.current && messageOpenerTicketIdRef.current !== ticket?.id) {
      messageOpenerRef.current = null;
      messageOpenerTicketIdRef.current = null;
      setIsChatOpen(false);
    }
  }, [ticket?.id]);

  useEffect(() => {
    if (!isChatOpen) return;
    const dialog = messageDialogRef.current;
    const focusTarget = dialog?.querySelector<HTMLElement>("#customer-message-input")
      ?? dialog?.querySelector<HTMLElement>("button:not([disabled])");
    focusTarget?.focus();
  }, [isChatOpen]);

  if (loading) {
    return (
      <div className="cust-detail" style={{ textAlign: 'center', padding: '3rem 1.5rem' }}>
        <div className="spinner" />
        <p style={{ marginTop: '0.75rem', color: 'var(--muted)', fontSize: '0.875rem' }}>
          {translate(locale, "loading")}
        </p>
      </div>
    );
  }

  if (!ticket) {
    return (
      <div className="cust-empty">
        {translate(locale, "customerHistorySelect")}
      </div>
    );
  }

  const submitMessage = async () => {
    if (!messageText.trim() || sendingMsg) return;
    setErrorMsg(null);
    setSendingMsg(true);
    try {
      await onSendMessage(messageText.trim());
      setMessageText("");
    } catch (error) {
      const code = error instanceof CustomerWorkflowError ? error.code : "backend";
      if (code === "unknown") setErrorMsg(translate(locale, "customerMessageUnknownOutcome"));
      else if (code === "idempotency_conflict") setErrorMsg(translate(locale, "customerMessageIdempotencyConflict"));
      else if (code === "closed_ticket") setErrorMsg(translate(locale, "customerMessageClosedConflict"));
      else if (code !== "aborted") setErrorMsg(translate(locale, "customerMessageSafeFailure"));
    } finally {
      setSendingMsg(false);
    }
  };

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    void submitMessage();
  };

  const handleRetry = () => {
    void submitMessage();
  };

  const closeMessages = () => {
    const opener = messageOpenerRef.current;
    const canRestoreFocus = Boolean(
      opener
      && messageOpenerTicketIdRef.current === ticket.id
      && opener.isConnected
      && document.contains(opener),
    );
    onCancelMessage();
    setIsChatOpen(false);
    messageOpenerRef.current = null;
    messageOpenerTicketIdRef.current = null;
    if (canRestoreFocus) opener?.focus();
  };

  const handleMessageDialogKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMessages();
      return;
    }
    if (event.key !== "Tab") return;
    const dialog = messageDialogRef.current;
    if (!dialog) return;
    const focusable = Array.from(dialog.querySelectorAll<HTMLElement>(
      'button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [href], [tabindex]:not([tabindex="-1"])',
    )).filter((element) => !element.hasAttribute("hidden") && element.getAttribute("aria-hidden") !== "true");
    if (!focusable.length) {
      event.preventDefault();
      return;
    }
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const timelineLabels: Record<CustomerTimelineType, MessageKey> = {
    complaint_received: "customerTimelineComplaintReceived",
    assigned_to_team: "customerTimelineAssignedToTeam",
    review_started: "customerTimelineReviewStarted",
    information_requested: "customerTimelineInformationRequested",
    team_replied: "customerTimelineTeamReplied",
    customer_replied: "customerTimelineCustomerReplied",
    complaint_resolved: "customerTimelineResolved",
    complaint_closed: "customerTimelineClosed",
  };

  const statusLabels: Record<CustomerTicketStatus, MessageKey> = {
    submitted: "statusSubmitted",
    triaged: "statusTriaged",
    in_progress: "statusInProgress",
    awaiting_customer: "statusAwaitingCustomer",
    resolved: "statusResolved",
    closed: "statusClosed",
  };

  const statusGuidance: Record<CustomerTicketStatus, MessageKey> = {
    submitted: "customerStatusGuidanceSubmitted",
    triaged: "customerStatusGuidanceTriaged",
    in_progress: "customerStatusGuidanceInProgress",
    awaiting_customer: "customerStatusGuidanceAwaitingCustomer",
    resolved: "customerStatusGuidanceResolved",
    closed: "customerStatusGuidanceClosed",
  };

  const currentStatusLabel = statusLabels[ticket.status];
  const currentStatusGuidance = statusGuidance[ticket.status];

  const isResolvedOrClosed = ticket.status === "resolved" || ticket.status === "closed";

  return (
    <>
      <article className="cust-detail" aria-labelledby="customer-ticket-detail-title">
        <div className="cust-detail-header">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2 id="customer-ticket-detail-title">
            {translate(locale, "staffDetailTitle")}
          </h2>
        </div>
          <div className="cust-detail-subrow">
            <span className="cust-ticket-id">
              {translate(locale, "customerTicketId")}: {ticket.id}
            </span>
            <span className="cust-detail-meta">
              {translate(locale, "staffCreated")}:{" "}
              {new Date(ticket.createdAt).toLocaleString(
                locale === "my" ? "my-MM" : "en-US"
              )}
            </span>
          </div>
        </div>

        <div className="cust-scroll-area">
          {errorMsg && (
            <div
              id="customer-message-error"
              className="cust-error"
              role="alert"
              style={{ marginBottom: '1rem' }}
            >
              {errorMsg}
            </div>
          )}

        {currentStatusLabel && currentStatusGuidance ? (
        <section className="cust-status-guidance" aria-labelledby="customer-status-guidance-title">
          <h3 id="customer-status-guidance-title">{translate(locale, "customerCurrentStatus")}</h3>
          <p className="cust-status-guidance-status">
            <strong>{translate(locale, currentStatusLabel)}</strong>
          </p>
          <div>
            <h4>{translate(locale, "customerWhatHappensNext")}</h4>
            <p className="cust-status-guidance-copy">
              {translate(locale, currentStatusGuidance)}
            </p>
          </div>
        </section>
        ) : null}

        {/* Visual Timeline */}
        <div style={{ marginBottom: '1.5rem' }}>
          <span className="cust-section-label">
            {translate(locale, "customerTimelineTitle")}
          </span>
          <div className="cust-timeline">
            {ticket.timeline.map((item, idx) => {
              const isLast = idx === ticket.timeline.length - 1;
              return (
                <React.Fragment key={`${item.type}-${item.occurredAt}-${idx}`}>
                  <div className="cust-step">
                    <div className="cust-step-dot done">
                      {idx + 1}
                    </div>
                    <span className="cust-step-label">
                      {translate(locale, timelineLabels[item.type])}
                    </span>
                  </div>
                  {!isLast && (
                    <div className="cust-step-connector done" />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        {/* Complaint Body */}
        <div style={{ marginTop: '1.5rem' }}>
          <span className="cust-section-label">
            {translate(locale, "complaintTextLabel")}
          </span>
          <div className="cust-body-block">
            {ticket.complaintText}
          </div>
        
          <div style={{ marginTop: '2rem', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              ref={messageOpenerRef}
              className="cust-refresh-btn"
              onClick={(event) => {
                messageOpenerTicketIdRef.current = ticket.id;
                setIsChatOpen(true);
                messageOpenerRef.current = event.currentTarget;
              }}
              style={{ background: 'var(--ink)', color: 'white', border: 'none' }}
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
              {translate(locale, "staffMessages")}
            </button>
          </div>
        </div>
        </div>
      </article>

      {isChatOpen && (
        <div className="cust-modal-overlay" onClick={(event) => { if (event.target === event.currentTarget) closeMessages(); }}>
          <div
            ref={messageDialogRef}
            className="cust-modal-content"
            role="dialog"
            aria-modal="true"
            aria-labelledby={messageDialogTitleId}
            onKeyDown={handleMessageDialogKeyDown}
          >
            <div className="cust-modal-header">
              <h2 id={messageDialogTitleId} className="cust-compose-title" style={{ margin: 0 }}>{translate(locale, "staffMessages")}</h2>
              <button
                type="button"
                className="icon-button"
                aria-label={translate(locale, "customerCloseMessages")}
                onClick={closeMessages}
              >
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>
            
            <div className="cust-compose">
              
              <div className="cust-messages">

          {ticket.messages.length === 0 ? (
            <p className="cust-no-messages">
              {translate(locale, "staffNoMessages")}
            </p>
          ) : (
            <div style={{ display: 'grid', gap: '0.75rem', maxHeight: '20rem', overflowY: 'auto' }}>
              {ticket.messages.map((m, index) => {
                const isMe = m.senderRole === "customer";
                return (
                  <div key={`${m.createdAt}-${index}`} className={`cust-msg ${isMe ? "is-mine" : "is-theirs"}`}>
                    <div className="cust-msg-bubble">
                      <div className="cust-msg-sender">
                        {isMe
                          ? translate(locale, "customerMessageYou")
                          : translate(locale, "customerMessageStaff")}
                      </div>
                      <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{m.body}</p>
                    </div>
                    <span className="cust-msg-time">
                      {new Date(m.createdAt).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Message Input Form */}
          {!isResolvedOrClosed && (
            <form onSubmit={handleSend} className="cust-msg-composer">
              <input
                type="text"
                id="customer-message-input"
                value={messageText}
                onChange={(e) => { setMessageText(e.target.value); setErrorMsg(null); }}
                placeholder={translate(locale, "customerSendMessage")}
                disabled={sendingMsg}
                className="cust-msg-input"
                aria-label={translate(locale, "customerSendMessage")}
                aria-describedby={errorMsg ? "customer-message-error" : undefined}
                aria-invalid={errorMsg ? true : undefined}
              />
              <button
                type="submit"
                disabled={sendingMsg || !messageText.trim()}
                className="cust-send-btn flex items-center justify-center p-3"
                aria-label={translate(locale, "customerSend")}
                title={translate(locale, "customerSend")}
              >
                {sendingMsg ? (
                  <svg className="animate-spin h-5 w-5" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>
                ) : (
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
                )}
              </button>
            </form>
          )}
          {errorMsg && errorMsg === translate(locale, "customerMessageUnknownOutcome") ? (
            <button type="button" className="cust-refresh-btn" onClick={handleRetry} disabled={sendingMsg}>
              {translate(locale, "customerMessageRetry")}
            </button>
          ) : null}
        </div>
        </div>
        </div>
        </div>
      )}

      {/* Rating & Feedback Section (When Resolved) */}
      {isResolvedOrClosed ? (
        <div className="cust-detail" style={{ gridColumn: '1 / -1', marginTop: '1.5rem' }}>
          <CustomerFeedbackPanel
            locale={locale}
            feedback={ticket.feedback ?? null}
            onSubmitFeedback={onSubmitFeedback}
          />
        </div>
      ) : null}
    </>
  );
}
