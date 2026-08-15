"use client";

import { useEffect, useRef, useState } from "react";
import { useApp } from "@/components/app-provider";
import { DatasetEvidencePanel } from "@/components/dataset-evidence-panel";
import { departmentIds, getDepartmentLabel } from "@/lib/department-labels";
import type { LowConfidenceTicket } from "@/lib/manager-workflow";
import { modelEvaluation } from "@/lib/model-evaluation";

type ManagerLowConfidenceReviewProps = {
  tickets: LowConfidenceTicket[];
  onOverride: (ticketId: string, newDeptId: string, reason: string) => Promise<void>;
};

export function ManagerLowConfidenceReview({
  tickets,
  onOverride,
}: ManagerLowConfidenceReviewProps) {
  const { locale, t } = useApp();
  const departmentName = (departmentId: string | null | undefined) =>
    getDepartmentLabel(departmentId, locale) ?? t("managerNotAvailable");
  const [selectedTicket, setSelectedTicket] = useState<LowConfidenceTicket | null>(null);
  const [targetDeptId, setTargetDeptId] = useState<string>("fraud_security");
  const [reason, setReason] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const cancelRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!selectedTicket) return;
    cancelRef.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !submitting) setSelectedTicket(null);
    };
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("keydown", closeOnEscape);
      triggerRef.current?.focus();
    };
  }, [selectedTicket, submitting]);

  const handleOpenModal = (ticket: LowConfidenceTicket) => {
    triggerRef.current = document.activeElement as HTMLButtonElement | null;
    setSelectedTicket(ticket);
    setTargetDeptId(ticket.departmentId || "fraud_security");
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
    <section className="analytics-card flex flex-col gap-5 overflow-hidden w-full">
      <div className="section-heading" style={{ marginBottom: 0 }}>
        <h3 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0 }}>{t("managerLowConfidenceQueue")}</h3>
      </div>

      {tickets.length === 0 ? (
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '4rem 2rem', background: 'var(--surface)', borderRadius: '1rem', border: '1px dashed var(--line)' }}>
          <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--muted)" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: '1rem', opacity: 0.7 }}>
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
            <polyline points="22 4 12 14.01 9 11.01"></polyline>
          </svg>
          <p style={{ color: 'var(--ink)', fontWeight: 600, fontSize: '1rem', margin: 0, textAlign: 'center' }}>
            {t("managerNoLowConfidence")}
          </p>
        </div>
      ) : (
        <div
          className="mng-table-wrap"
          tabIndex={0}
          aria-label={t("managerLowConfidenceQueue")}
          style={{ border: 'none', background: 'transparent', borderRadius: 0 }}
        >
          <table className="mng-table">
            <thead>
              <tr>
                <th>{t("managerTicketId")}</th>
                <th>{t("managerComplaintSnippet")}</th>
                <th>{t("managerPredictedDepartment")}</th>
                <th>{t("managerConfidence")}</th>
                <th>{t("managerCurrentDepartment")}</th>
                <th>{t("managerAction")}</th>
              </tr>
            </thead>
            <tbody>
              {tickets.map((ticket) => (
                <tr key={ticket.id}>
                  <td className="ticket-reference" style={{ fontFamily: 'monospace', fontWeight: 'bold' }}>
                    {ticket.id}
                  </td>
                  <td style={{ maxWidth: '16rem', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }} title={ticket.complaintText}>
                    {ticket.complaintText}
                  </td>
                  <td>
                    {departmentName(ticket.predictedDepartmentId)}
                  </td>
                  <td>
                    <span
                      className={`cust-status-pill ${
                        ticket.predictionConfidence !== null && ticket.predictionConfidence < modelEvaluation.confidence.threshold
                          ? 'is-awaiting'
                          : 'is-resolved'
                      }`}
                    >
                      {ticket.predictionConfidence !== null
                        ? `${Math.round(ticket.predictionConfidence * 100)}%`
                        : t("managerManualRouting")}
                    </span>
                  </td>
                  <td>{departmentName(ticket.departmentId)}</td>
                  <td>
                    <button
                      type="button"
                      onClick={() => handleOpenModal(ticket)}
                      aria-haspopup="dialog"
                      style={{ background: 'var(--ink)', color: 'white', padding: '0.25rem 0.75rem', borderRadius: '0.5rem', border: 'none', fontWeight: 600, fontSize: '0.75rem', cursor: 'pointer' }}
                    >
                      {t("managerReassignBtn")}
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
        <div className="cust-modal-overlay">
          <div className="cust-modal-content" role="dialog" aria-modal="true" aria-labelledby="manager-override-title" style={{ maxWidth: '42rem' }}>
            <div className="cust-modal-header" style={{ paddingBottom: 0 }}>
              <div>
                <h4 id="manager-override-title" style={{ fontSize: '1.125rem', fontWeight: 700, margin: 0 }}>{t("managerOverrideModalTitle")}</h4>
                <p className="ticket-reference" style={{ fontSize: '0.75rem', color: 'var(--muted)', fontFamily: 'monospace', margin: '0.25rem 0 0 0' }}>
                  {t("managerTicketLabel")}: {selectedTicket.id}
                </p>
              </div>
              <button className="icon-button" onClick={() => setSelectedTicket(null)}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18"></line>
                  <line x1="6" y1="6" x2="18" y2="18"></line>
                </svg>
              </button>
            </div>

            <div className="cust-scroll-area" style={{ display: 'flex', flexDirection: 'column', gap: '1rem', padding: '1.5rem' }}>

            <DatasetEvidencePanel
              predictedDepartmentId={selectedTicket.predictedDepartmentId}
              predictionConfidence={selectedTicket.predictionConfidence}
              routingSource={selectedTicket.routingSource}
              assignedDepartmentId={selectedTicket.departmentId}
            />

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <label htmlFor="dept-select" style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)' }}>
                {t("managerSelectDepartment")}
              </label>
              <select
                id="dept-select"
                value={targetDeptId}
                onChange={(e) => setTargetDeptId(e.target.value)}
                style={{ width: '100%', padding: '0.5rem', fontSize: '0.875rem', borderRadius: '0.5rem', border: '1px solid var(--line)', background: 'var(--background)' }}
              >
                {departmentIds.map((departmentId) => (
                  <option key={departmentId} value={departmentId}>
                    {departmentName(departmentId)}
                  </option>
                ))}
              </select>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
              <label htmlFor="override-reason" style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)' }}>
                {t("managerOverrideReason")}
              </label>
              <textarea
                id="override-reason"
                rows={3}
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                placeholder={t("managerReasonPlaceholder")}
                aria-describedby="override-reason-help"
                style={{ width: '100%', padding: '0.5rem', fontSize: '0.875rem', borderRadius: '0.5rem', border: '1px solid var(--line)', background: 'var(--background)', resize: 'vertical' }}
              />
            </div>
            <p id="override-reason-help" className="field-help">{t("managerOverrideReasonRequired")}</p>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', paddingTop: '0.5rem' }}>
              <button
                type="button"
                ref={cancelRef}
                onClick={() => setSelectedTicket(null)}
                disabled={submitting}
                style={{ padding: '0.5rem 1rem', fontSize: '0.75rem', fontWeight: 600, borderRadius: '0.5rem', background: '#f4f4f4', border: 'none', cursor: 'pointer' }}
              >
                {t("managerCancel")}
              </button>
              <button
                type="button"
                onClick={handleConfirmOverride}
                disabled={submitting || !reason.trim()}
                style={{ padding: '0.5rem 1rem', fontSize: '0.75rem', fontWeight: 600, borderRadius: '0.5rem', background: 'var(--ink)', color: 'white', border: 'none', cursor: submitting || !reason.trim() ? 'not-allowed' : 'pointer' }}
              >
                {submitting ? t("managerSaving") : t("managerConfirmOverride")}
              </button>
            </div>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
