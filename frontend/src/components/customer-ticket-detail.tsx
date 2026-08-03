"use client";

import { useState } from "react";
import { useApp } from "@/components/app-provider";
import type { MessageKey } from "@/lib/i18n";
import type { CustomerTicketDetail } from "@/lib/customer-workflow";

type CustomerTicketDetailViewProps = {
  detail: CustomerTicketDetail;
  onSendMessage: (text: string) => Promise<void>;
  onSubmitFeedback: (rating: number, comments: string) => Promise<void>;
};

const TIMELINE_STEPS = [
  { id: "submitted", key: "customerTimelineSubmitted" },
  { id: "assigned", key: "customerTimelineAssigned" },
  { id: "investigation", key: "customerTimelineInvestigation" },
  { id: "resolved", key: "customerTimelineResolved" },
] as const;

function getStepIndex(status: string): number {
  if (status === "resolved") return 3;
  if (status === "in_progress" || status === "awaiting_customer") return 2;
  if (status === "triaged") return 1;
  return 0;
}

export function CustomerTicketDetailView({
  detail,
  onSendMessage,
  onSubmitFeedback,
}: CustomerTicketDetailViewProps) {
  const { t } = useApp();
  const [msgText, setMsgText] = useState("");
  const [sendingMsg, setSendingMsg] = useState(false);
  const [showRatingModal, setShowRatingModal] = useState(false);
  const [rating, setRating] = useState(5);
  const [feedbackComments, setFeedbackComments] = useState("");
  const [submittingFeedback, setSubmittingFeedback] = useState(false);

  const activeStep = getStepIndex(detail.status);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!msgText.trim()) return;
    setSendingMsg(true);
    try {
      await onSendMessage(msgText);
      setMsgText("");
    } finally {
      setSendingMsg(false);
    }
  };

  const handleFeedbackSubmit = async () => {
    setSubmittingFeedback(true);
    try {
      await onSubmitFeedback(rating, feedbackComments);
      setShowRatingModal(false);
    } finally {
      setSubmittingFeedback(false);
    }
  };

  return (
    <div className="space-y-6 bg-white p-6 rounded-2xl border border-gray-200 shadow-sm">
      <div className="flex justify-between items-start border-b pb-4">
        <div>
          <span className="font-mono text-xs text-gray-500 font-semibold">ID: {detail.id}</span>
          <h2 className="text-xl font-bold text-gray-900 mt-1">{t("staffDetailTitle")}</h2>
        </div>
        {detail.status === "resolved" && !detail.rating && (
          <button
            type="button"
            onClick={() => setShowRatingModal(true)}
            className="px-4 py-2 bg-amber-500 hover:bg-amber-600 text-white text-xs font-bold rounded-lg shadow-sm"
          >
            {t("customerFeedbackBtn")}
          </button>
        )}
      </div>

      {/* Visual Timeline */}
      <div className="space-y-2">
        <p className="text-xs font-bold text-gray-500 uppercase tracking-wider">
          Complaint Status Timeline
        </p>
        <div className="grid grid-cols-4 gap-2 pt-2">
          {TIMELINE_STEPS.map((step, idx) => {
            const isPassed = idx <= activeStep;
            return (
              <div key={step.id} className="text-center space-y-1">
                <div
                  className={`h-2 rounded-full transition-all ${
                    isPassed ? "bg-blue-600" : "bg-gray-200"
                  }`}
                />
                <span
                  className={`text-[11px] font-semibold block ${
                    isPassed ? "text-blue-900" : "text-gray-400"
                  }`}
                >
                  {t(step.key as MessageKey)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Complaint Text */}
      <div className="p-4 bg-gray-50 rounded-xl border border-gray-100 space-y-1">
        <span className="text-xs font-bold text-gray-500 uppercase">Complaint Text</span>
        <p className="text-sm text-gray-800 font-medium whitespace-pre-wrap">
          {detail.complaintText}
        </p>
      </div>

      {/* Messages Thread */}
      <div className="space-y-3 pt-2">
        <h4 className="text-sm font-bold text-gray-900">{t("customerMessagesTitle")}</h4>
        <div className="space-y-3 max-h-80 overflow-y-auto p-3 bg-gray-50 rounded-xl border border-gray-200">
          {detail.messages.length === 0 ? (
            <p className="text-xs text-gray-500 text-center py-4">{t("customerNoMessages")}</p>
          ) : (
            detail.messages.map((m) => {
              const isCust = m.senderRole === "customer";
              return (
                <div
                  key={m.messageId}
                  className={`flex flex-col ${isCust ? "items-end" : "items-start"}`}
                >
                  <div
                    className={`p-3 rounded-xl max-w-xs text-xs font-medium ${
                      isCust
                        ? "bg-blue-600 text-white rounded-br-none"
                        : "bg-white text-gray-800 border border-gray-200 rounded-bl-none shadow-sm"
                    }`}
                  >
                    <span className="block text-[10px] opacity-75 font-bold mb-1">
                      {isCust ? "You" : "Department Staff"}
                    </span>
                    {m.text}
                  </div>
                  <span className="text-[10px] text-gray-400 mt-1">
                    {new Date(m.createdAt).toLocaleTimeString()}
                  </span>
                </div>
              );
            })
          )}
        </div>

        {/* Message Input Box */}
        {detail.status !== "resolved" && (
          <form onSubmit={handleSend} className="flex gap-2 pt-2">
            <input
              type="text"
              value={msgText}
              onChange={(e) => setMsgText(e.target.value)}
              placeholder={t("customerSendMessagePlaceholder")}
              className="flex-1 p-2.5 text-xs border border-gray-300 rounded-xl focus:ring-2 focus:ring-blue-500 focus:outline-none"
            />
            <button
              type="submit"
              disabled={sendingMsg || !msgText.trim()}
              className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl shadow-sm"
            >
              {sendingMsg ? t("customerSendingBtn") : t("customerSendBtn")}
            </button>
          </form>
        )}
      </div>

      {/* Rating Modal */}
      {showRatingModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-white rounded-2xl p-6 space-y-4 shadow-xl border border-gray-200">
            <h4 className="text-lg font-bold text-gray-900">
              {t("customerFeedbackModalTitle")}
            </h4>
            <div className="space-y-1">
              <label className="text-xs font-semibold text-gray-700">
                {t("customerRatingLabel")}
              </label>
              <div className="flex gap-2">
                {[1, 2, 3, 4, 5].map((star) => (
                  <button
                    key={star}
                    type="button"
                    onClick={() => setRating(star)}
                    className={`p-2 rounded-lg text-lg font-bold ${
                      rating >= star
                        ? "bg-amber-100 text-amber-600"
                        : "bg-gray-100 text-gray-400"
                    }`}
                  >
                    ★
                  </button>
                ))}
              </div>
            </div>

            <div className="space-y-1">
              <label className="text-xs font-semibold text-gray-700">
                {t("customerCommentsLabel")}
              </label>
              <textarea
                rows={3}
                value={feedbackComments}
                onChange={(e) => setFeedbackComments(e.target.value)}
                className="w-full p-2 text-xs border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setShowRatingModal(false)}
                className="px-4 py-2 text-xs font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleFeedbackSubmit}
                disabled={submittingFeedback}
                className="px-4 py-2 text-xs font-semibold text-white bg-amber-500 hover:bg-amber-600 rounded-lg shadow-sm"
              >
                {t("customerSubmitFeedbackBtn")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
