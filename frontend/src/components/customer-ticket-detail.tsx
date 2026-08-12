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

  if (loading) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-sm text-gray-500">
        {translate(locale, "loading")}
      </div>
    );
  }

  if (!ticket) {
    return (
      <div className="bg-white rounded-lg border border-gray-200 p-8 text-center text-sm text-gray-500">
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

    if (currentIdx >= stepIdx) return "completed";
    return "pending";
  };

  const isResolvedOrClosed = ticket.status === "resolved" || ticket.status === "closed";

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-6 space-y-6">
      {/* Header */}
      <div className="ticket-detail-header border-b border-gray-100 pb-4">
        <div className="min-w-0">
          <span className="ticket-reference text-xs text-gray-400 font-mono">
            {translate(locale, "customerTicketId")}: {ticket.id}
          </span>
          <h2 className="text-xl font-bold text-gray-900 mt-1">
            {translate(locale, "staffDetailTitle")}
          </h2>
        </div>
        <div className="ticket-created-meta text-right text-xs text-gray-500">
          <div>
            {translate(locale, "staffCreated")}:{" "}
            {new Date(ticket.createdAt).toLocaleString(
              locale === "my" ? "my-MM" : "en-US"
            )}
          </div>
        </div>
      </div>

      {errorMsg && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded">
          {errorMsg}
        </div>
      )}

      {/* Visual Timeline */}
      <div className="ticket-timeline-wrapper">
        <h3 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          {translate(locale, "customerTimelineTitle")}
        </h3>
        <div className="ticket-timeline flex items-center justify-between w-full max-w-xl mx-auto py-2">
          {steps.map((step, idx) => {
            const status = getStepStatus(step.key);
            const isLast = idx === steps.length - 1;
            return (
              <React.Fragment key={step.key}>
                <div className="flex flex-col items-center text-center">
                  <div
                    className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-xs ${
                      status === "completed"
                        ? "bg-blue-600 text-white"
                        : "bg-gray-100 text-gray-400 border border-gray-300"
                    }`}
                  >
                    {idx + 1}
                  </div>
                  <span className="text-xs font-medium text-gray-700 mt-1 max-w-[80px]">
                    {step.label}
                  </span>
                </div>
                {!isLast && (
                  <div
                    className={`flex-1 h-0.5 mx-2 ${
                      status === "completed" ? "bg-blue-600" : "bg-gray-200"
                    }`}
                  />
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

      <div className="bg-gray-50 rounded-lg p-4 border border-gray-200">
        <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
          {translate(locale, "complaintTextLabel")}
        </h4>
        <p className="text-sm text-gray-800 whitespace-pre-wrap break-words">
          {ticket.complaintText}
        </p>
      </div>

      {/* Message Thread */}
      <div className="space-y-4">
        <h3 className="text-sm font-bold text-gray-900">
          {translate(locale, "staffMessages")}
        </h3>

        <div className="space-y-3 max-h-80 overflow-y-auto pr-1">
          {ticket.messages.length === 0 ? (
            <p className="text-xs text-gray-400 italic">
              {translate(locale, "staffNoMessages")}
            </p>
          ) : (
            ticket.messages.map((m) => {
              const isMe = m.senderRole === "customer";
              return (
                <div
                  key={m.id}
                  className={`flex flex-col ${
                    isMe ? "items-end" : "items-start"
                  }`}
                >
                  <div
                    className={`ticket-message-bubble max-w-md rounded-lg p-3 text-sm ${
                      isMe
                        ? "bg-blue-600 text-white rounded-br-none"
                        : "bg-gray-100 text-gray-900 rounded-bl-none border border-gray-200"
                    }`}
                  >
                    <div className="text-[10px] opacity-75 mb-1 font-semibold">
                      {isMe
                        ? translate(locale, "customerMessageYou")
                        : translate(locale, "customerMessageStaff")}
                    </div>
                    <p className="whitespace-pre-wrap break-words">{m.text}</p>
                  </div>
                  <span className="text-[10px] text-gray-400 mt-1">
                    {new Date(m.createdAt).toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* Message Input Form */}
        {!isResolvedOrClosed && (
          <form onSubmit={handleSend} className="ticket-message-composer flex gap-2 pt-2">
            <input
              type="text"
              value={messageText}
              onChange={(e) => setMessageText(e.target.value)}
              placeholder={translate(locale, "customerSendMessage")}
              disabled={sendingMsg}
              className="ticket-message-input flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <button
              type="submit"
              disabled={sendingMsg || !messageText.trim()}
              className="ticket-message-send bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white font-medium text-sm px-4 py-2 rounded-lg transition-colors"
            >
              {sendingMsg
                ? translate(locale, "customerSending")
                : translate(locale, "customerSend")}
            </button>
          </form>
        )}
      </div>

      {/* Rating & Feedback Section (When Resolved) */}
      {isResolvedOrClosed ? (
        <CustomerFeedbackPanel
          locale={locale}
          feedback={ticket.feedback ?? null}
          onSubmitFeedback={onSubmitFeedback}
        />
      ) : null}
    </div>
  );
}
