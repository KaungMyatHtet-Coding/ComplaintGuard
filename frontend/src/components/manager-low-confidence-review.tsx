"use client";

import { useState } from "react";
import { useApp } from "@/components/app-provider";
import type { LowConfidenceTicket } from "@/lib/manager-workflow";

const DEPARTMENTS = [
  { id: "transfer_payment", label: "Transfer & Payments" },
  { id: "account_support", label: "Account Support" },
  { id: "card_atm", label: "Card & ATM" },
  { id: "fraud_security", label: "Fraud & Security" },
  { id: "loan_credit", label: "Loan & Credit" },
  { id: "general_support", label: "General Support" },
];

type ManagerLowConfidenceReviewProps = {
  tickets: LowConfidenceTicket[];
  onOverride: (ticketId: string, newDeptId: string, reason: string) => Promise<void>;
};

export function ManagerLowConfidenceReview({
  tickets,
  onOverride,
}: ManagerLowConfidenceReviewProps) {
  const { t } = useApp();
  const [selectedTicket, setSelectedTicket] = useState<LowConfidenceTicket | null>(null);
  const [targetDeptId, setTargetDeptId] = useState<string>("fraud_security");
  const [reason, setReason] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);

  const handleOpenModal = (ticket: LowConfidenceTicket) => {
    setSelectedTicket(ticket);
    setTargetDeptId(ticket.assignedDepartmentId || "fraud_security");
    setReason("");
  };

  const handleConfirmOverride = async () => {
    if (!selectedTicket) return;
    setSubmitting(true);
    try {
      await onOverride(selectedTicket.id, targetDeptId, reason);
      setSelectedTicket(null);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <h3 className="text-lg font-bold text-gray-900">{t("managerLowConfidenceQueue")}</h3>

      {tickets.length === 0 ? (
        <p className="p-4 text-sm text-gray-500 bg-gray-50 rounded-lg border border-gray-200">
          {t("managerNoLowConfidence")}
        </p>
      ) : (
        <div className="overflow-x-auto border border-gray-200 rounded-xl bg-white shadow-sm">
          <table className="min-w-full divide-y divide-gray-200 text-left text-xs">
            <thead className="bg-gray-50 text-gray-700 font-semibold uppercase">
              <tr>
                <th className="px-4 py-3">Ticket ID</th>
                <th className="px-4 py-3">Complaint Snippet</th>
                <th className="px-4 py-3">Predicted Dept</th>
                <th className="px-4 py-3">Confidence</th>
                <th className="px-4 py-3">Current Dept</th>
                <th className="px-4 py-3">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200 text-gray-800 font-medium">
              {tickets.map((t) => (
                <tr key={t.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-mono text-gray-900 font-bold">{t.id}</td>
                  <td className="px-4 py-3 max-w-xs truncate" title={t.complaintText}>
                    {t.complaintText}
                  </td>
                  <td className="px-4 py-3">{t.predictedDepartmentId || "N/A"}</td>
                  <td className="px-4 py-3">
                    <span
                      className={`px-2 py-0.5 rounded-full text-xs font-bold ${
                        (t.predictionConfidence ?? 0) < 0.6
                          ? "bg-amber-100 text-amber-800"
                          : "bg-emerald-100 text-emerald-800"
                      }`}
                    >
                      {t.predictionConfidence !== null
                        ? `${Math.round(t.predictionConfidence * 100)}%`
                        : "Manual"}
                    </span>
                  </td>
                  <td className="px-4 py-3">{t.assignedDepartmentId}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => handleOpenModal(t)}
                      className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg shadow-sm transition"
                    >
                      Reassign
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Override Modal */}
      {selectedTicket && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="w-full max-w-md bg-white rounded-2xl p-6 space-y-4 shadow-xl border border-gray-200">
            <h4 className="text-lg font-bold text-gray-900">{t("managerOverrideModalTitle")}</h4>
            <p className="text-xs text-gray-500 font-mono">Ticket: {selectedTicket.id}</p>

            <div className="space-y-1">
              <label htmlFor="dept-select" className="text-xs font-semibold text-gray-700">
                {t("managerSelectDepartment")}
              </label>
              <select
                id="dept-select"
                value={targetDeptId}
                onChange={(e) => setTargetDeptId(e.target.value)}
                className="w-full p-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              >
                {DEPARTMENTS.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label htmlFor="override-reason" className="text-xs font-semibold text-gray-700">
                {t("managerOverrideReason")}
              </label>
              <textarea
                id="override-reason"
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder="Reason for manual reassignment..."
                className="w-full p-2 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none"
              />
            </div>

            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setSelectedTicket(null)}
                disabled={submitting}
                className="px-4 py-2 text-xs font-semibold text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmOverride}
                disabled={submitting}
                className="px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm"
              >
                {submitting ? "Saving..." : t("managerConfirmOverride")}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
