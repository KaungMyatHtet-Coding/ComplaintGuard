"use client";

import React, { useState } from "react";
import { CustomerFeedbackPanel } from "@/components/customer-feedback-panel";
import { DatasetEvidencePanel } from "@/components/dataset-evidence-panel";
import type { Locale } from "@/lib/i18n";
import { translate } from "@/lib/i18n";
import type { CustomerTicketDetail } from "@/lib/customer-workflow";

type CustomerTicketDetailProps = {
  locale: Locale;
  ticket: CustomerTicketDetail | null;
  loading: boolean;
  onSendMessage: (text: string) => Promise<void>;
  onSubmitFeedback: (rating: number, comments: string) => Promise<void>;
};

export function CustomerTicketDetailView({
  locale,
  ticket,
  loading,
  onSendMessage,
  onSubmitFeedback,
}: CustomerTicketDetailProps) {
  const [messageText, setMessageText] = useState("");
  const [sendingMsg, setSendingMsg] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isChatOpen, setIsChatOpen] = useState(false);

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

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!messageText.trim() || sendingMsg) return;
    setErrorMsg(null);
    setSendingMsg(true);
    try {
      await onSendMessage(messageText.trim());
      setMessageText("");
    } catch {
      setErrorMsg(translate(locale, "customerMessageSendError"));
    } finally {
      setSendingMsg(false);
    }
  };

  // Timeline steps
  const steps = [
    { key: "submitted", label: translate(locale, "customerTimelineSubmitted") },
    { key: "triaged", label: translate(locale, "customerTimelineTriaged") },
    { key: "in_progress", label: translate(locale, "customerTimelineInProgress") },
    { key: "awaiting_customer", label: translate(locale, "customerTimelineAwaitingCustomer") },
    { key: "resolved", label: translate(locale, "customerTimelineResolved") },
  ];

  const getStepStatus = (stepKey: string) => {
    const order = ["submitted", "triaged", "in_progress", "awaiting_customer", "resolved", "closed"];
    const currentIdx = order.indexOf(ticket.status);
    const stepIdx = order.indexOf(stepKey);
    return currentIdx >= stepIdx ? "completed" : "pending";
  };

  const isResolvedOrClosed = ticket.status === "resolved" || ticket.status === "closed";

  return (
    <>
      <div className="cust-detail">
        <div className="cust-detail-header">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h2>
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
            <div className="cust-error" role="alert" style={{ marginBottom: '1rem' }}>{errorMsg}</div>
          )}

        {/* Visual Timeline */}
        <div style={{ marginBottom: '1.5rem' }}>
          <span className="cust-section-label">
            {translate(locale, "customerTimelineTitle")}
          </span>
          <div className="cust-timeline">
            {steps.map((step, idx) => {
              const status = getStepStatus(step.key);
              const isLast = idx === steps.length - 1;
              return (
                <React.Fragment key={step.key}>
                  <div className="cust-step">
                    <div className={`cust-step-dot ${status === "completed" ? "done" : "pending"}`}>
                      {idx + 1}
                    </div>
                    <span className="cust-step-label">{step.label}</span>
                  </div>
                  {!isLast && (
                    <div className={`cust-step-connector ${status === "completed" ? "done" : "pending"}`} />
                  )}
                </React.Fragment>
              );
            })}
          </div>
        </div>

        <DatasetEvidencePanel
          predictedDepartmentId={ticket.predictedDepartmentId}
          predictionConfidence={ticket.predictionConfidence}
          routingSource={ticket.routingSource}
          assignedDepartmentId={ticket.assignedDepartmentId}
        />

        {/* Complaint Body */}
        <div style={{ marginTop: '1.5rem' }}>
          <span className="cust-section-label">
            {translate(locale, "complaintTextLabel")}
          </span>
          <div className="cust-body-block">
            {ticket.complaintText}
          </div>
        
          <div style={{ marginTop: '2rem', display: 'flex', justifyContent: 'flex-end' }}>
            <button className="cust-refresh-btn" onClick={() => setIsChatOpen(true)} style={{ background: 'var(--ink)', color: 'white', border: 'none' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
              </svg>
              {translate(locale, "staffMessages")}
            </button>
          </div>
        </div>
        </div>
      </div>

      {isChatOpen && (
        <div className="cust-modal-overlay">
          <div className="cust-modal-content">
            <div className="cust-modal-header">
              <h2 className="cust-compose-title" style={{ margin: 0 }}>{translate(locale, "staffMessages")}</h2>
              <button className="icon-button" onClick={() => setIsChatOpen(false)}>
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
              {ticket.messages.map((m) => {
                const isMe = m.senderRole === "customer";
                return (
                  <div key={m.id} className={`cust-msg ${isMe ? "is-mine" : "is-theirs"}`}>
                    <div className="cust-msg-bubble">
                      <div className="cust-msg-sender">
                        {isMe
                          ? translate(locale, "customerMessageYou")
                          : translate(locale, "customerMessageStaff")}
                      </div>
                      <p style={{ margin: 0, whiteSpace: 'pre-wrap' }}>{m.text}</p>
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
                value={messageText}
                onChange={(e) => setMessageText(e.target.value)}
                placeholder={translate(locale, "customerSendMessage")}
                disabled={sendingMsg}
                className="cust-msg-input"
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
