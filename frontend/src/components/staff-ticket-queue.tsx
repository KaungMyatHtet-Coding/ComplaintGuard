"use client";

import { useCallback, useEffect, useState } from "react";

import { useApp } from "@/components/app-provider";
import { StaffTicketDetail } from "@/components/staff-ticket-detail";
import { getFirebaseServices } from "@/lib/firebase";
import {
  StaffWorkflowError,
  loadStaffTickets,
  type StaffFilters,
  type StaffTicket,
  type StaffWorkflowErrorCode,
} from "@/lib/staff-workflow";

const errorKeys = {
  authentication: "staffAuthError",
  permission: "staffPermissionError",
  not_found: "staffNotFoundError",
  validation: "staffValidationError",
  conflict: "staffConflictError",
  backend: "staffBackendError",
} as const;

async function currentToken() {
  const user = getFirebaseServices().auth.currentUser;
  if (!user) throw new StaffWorkflowError("authentication");
  return user.getIdToken();
}

type StaffTicketRowProps = {
  ticket: StaffTicket;
  locale: string;
  selected: boolean;
  statusLabel: string;
  priorityLabel: string;
  onSelect: (ticketId: string) => void;
};

export function StaffTicketRow({
  ticket,
  locale,
  selected,
  statusLabel,
  priorityLabel,
  onSelect,
}: StaffTicketRowProps) {
  return (
    <button
      className="ticket-row"
      onClick={() => onSelect(ticket.ticketId)}
      aria-pressed={selected}
    >
      <strong className="ticket-reference">{ticket.ticketId}</strong>
      <span className="ticket-status-badge">{statusLabel}</span>
      <span>{priorityLabel}</span>
      <time>{new Intl.DateTimeFormat(locale).format(new Date(ticket.createdAt))}</time>
    </button>
  );
}

export function StaffTicketQueue() {
  const { locale, t } = useApp();
  const [filters, setFilters] = useState<StaffFilters>({});
  const [tickets, setTickets] = useState<StaffTicket[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<StaffWorkflowErrorCode | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setTickets(await loadStaffTickets(await currentToken(), filters));
    } catch (value) {
      setError(value instanceof StaffWorkflowError ? value.code : "backend");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    queueMicrotask(() => void reload());
  }, [reload]);

  return (
    <section className="unified-workspace" aria-labelledby="staff-queue-title">
      <div className="staff-queue-panel">
        <h2 id="staff-queue-title">{t("staffQueueTitle")}</h2>
        <div className="staff-filters" aria-label={t("staffFiltersLabel")}>
          <label>{t("staffStatusFilter")}
            <select value={filters.status ?? ""} onChange={(event) => setFilters((current) => ({ ...current, status: event.target.value as StaffFilters["status"] || undefined }))}>
              <option value="">{t("staffAll")}</option>
              <option value="triaged">{t("statusTriaged")}</option>
              <option value="in_progress">{t("statusInProgress")}</option>
              <option value="awaiting_customer">{t("statusAwaitingCustomer")}</option>
              <option value="resolved">{t("statusResolved")}</option>
            </select>
          </label>
          <label>{t("staffPriorityFilter")}
            <select value={filters.priority ?? ""} onChange={(event) => setFilters((current) => ({ ...current, priority: event.target.value as StaffFilters["priority"] || undefined }))}>
              <option value="">{t("staffAll")}</option>
              <option value="normal">{t("priorityNormal")}</option>
              <option value="high">{t("priorityHigh")}</option>
              <option value="urgent">{t("priorityUrgent")}</option>
            </select>
          </label>
          <label>{t("staffDateFrom")}<input type="date" value={filters.createdFrom?.slice(0, 10) ?? ""} onChange={(event) => setFilters((current) => ({ ...current, createdFrom: event.target.value ? `${event.target.value}T00:00:00Z` : undefined }))} /></label>
          <label>{t("staffDateTo")}<input type="date" value={filters.createdTo?.slice(0, 10) ?? ""} onChange={(event) => setFilters((current) => ({ ...current, createdTo: event.target.value ? `${event.target.value}T23:59:59Z` : undefined }))} /></label>
        </div>
        {loading ? <p role="status">{t("staffLoading")}</p> : null}
        {error ? <div className="error-panel" role="alert">{t(errorKeys[error])}</div> : null}
        {!loading && !error && tickets.length === 0 ? <p className="empty-state">{t("staffEmpty")}</p> : null}
        <div className="ticket-list">
          {tickets.map((ticket) => (
            <StaffTicketRow
              key={ticket.ticketId}
              ticket={ticket}
              locale={locale}
              selected={selectedId === ticket.ticketId}
              statusLabel={t(`status_${ticket.status}` as "status_triaged")}
              priorityLabel={t(`priority_${ticket.priority}` as "priority_normal")}
              onSelect={setSelectedId}
            />
          ))}
        </div>
      </div>
      {selectedId ? <StaffTicketDetail ticketId={selectedId} getToken={currentToken} onChanged={reload} /> : <div className="staff-detail-panel empty-state">{t("staffSelectTicket")}</div>}
    </section>
  );
}
