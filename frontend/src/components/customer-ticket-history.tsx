"use client";

import React from "react";
import type { Locale } from "@/lib/i18n";
import { translate } from "@/lib/i18n";
import {
  CUSTOMER_HISTORY_DEPARTMENTS,
  CUSTOMER_HISTORY_STATUSES,
  type CustomerDepartmentId,
  type CustomerTicketStatus,
  type CustomerTicketSummary,
} from "@/lib/customer-workflow";
import { getDepartmentLabel } from "@/lib/department-labels";

type CustomerTicketHistoryProps = {
  locale: Locale;
  tickets: CustomerTicketSummary[];
  selectedTicketId: string | null;
  onSelectTicket: (ticketId: string) => void;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  loadingMore: boolean;
  loadMoreError: string | null;
  hasMore: boolean;
  onLoadMore: () => void;
  statusFilter: CustomerTicketStatus | null;
  departmentFilter: CustomerDepartmentId | null;
  onFilterChange: (status: CustomerTicketStatus | null, departmentId: CustomerDepartmentId | null) => void;
};

function statusClass(status: string) {
  switch (status) {
    case "resolved":
    case "closed":
      return "is-resolved";
    case "in_progress":
      return "is-progress";
    case "awaiting_customer":
      return "is-awaiting";
    case "triaged":
      return "is-triaged";
    default:
      return "is-submitted";
  }
}

function formatStatus(status: string, locale: Locale) {
  switch (status) {
    case "triaged":
      return translate(locale, "statusTriaged");
    case "in_progress":
      return translate(locale, "statusInProgress");
    case "awaiting_customer":
      return translate(locale, "statusAwaitingCustomer");
    case "resolved":
      return translate(locale, "statusResolved");
    case "closed":
      return translate(locale, "statusClosed");
    default:
      return translate(locale, "statusSubmitted");
  }
}

export function CustomerTicketHistory({
  locale,
  tickets,
  selectedTicketId,
  onSelectTicket,
  loading,
  error,
  onRefresh,
  loadingMore,
  loadMoreError,
  hasMore,
  onLoadMore,
  statusFilter,
  departmentFilter,
  onFilterChange,
}: CustomerTicketHistoryProps) {
  const filtersActive = statusFilter !== null || departmentFilter !== null;
  return (
    <div className="cust-card">
      <div className="cust-card-header">
        <h3>{translate(locale, "customerHistoryTitle")}</h3>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="cust-refresh-btn"
        >
          {loading ? translate(locale, "loading") : translate(locale, "customerRefreshHistory")}
        </button>
      </div>

      <div className="cust-history-filters" aria-label={translate(locale, "customerHistoryFilters") }>
        <div className="cust-history-filter-field">
          <label htmlFor="customer-history-status">{translate(locale, "customerStatusFilter")}</label>
          <p id="customer-history-status-help" className="cust-filter-help">{translate(locale, "customerStatusFilterHelp")}</p>
          <select
            id="customer-history-status"
            value={statusFilter ?? ""}
            aria-describedby="customer-history-status-help"
            onChange={(event) => onFilterChange(
              event.target.value === "" ? null : event.target.value as CustomerTicketStatus,
              departmentFilter,
            )}
          >
            <option value="">{translate(locale, "customerAllStatuses")}</option>
            {CUSTOMER_HISTORY_STATUSES.map((status) => (
              <option key={status} value={status}>{formatStatus(status, locale)}</option>
            ))}
          </select>
        </div>
        <div className="cust-history-filter-field">
          <label htmlFor="customer-history-department">{translate(locale, "customerDepartmentFilter")}</label>
          <p id="customer-history-department-help" className="cust-filter-help">{translate(locale, "customerDepartmentFilterHelp")}</p>
          <select
            id="customer-history-department"
            value={departmentFilter ?? ""}
            aria-describedby="customer-history-department-help"
            onChange={(event) => onFilterChange(
              statusFilter,
              event.target.value === "" ? null : event.target.value as CustomerDepartmentId,
            )}
          >
            <option value="">{translate(locale, "customerAllDepartments")}</option>
            {CUSTOMER_HISTORY_DEPARTMENTS.map((department) => (
              <option key={department} value={department}>{getDepartmentLabel(department, locale)}</option>
            ))}
          </select>
        </div>
        <button
          type="button"
          className="cust-refresh-btn cust-clear-filters"
          onClick={() => onFilterChange(null, null)}
          disabled={!filtersActive}
          aria-disabled={!filtersActive}
        >
          {translate(locale, "customerClearFilters")}
        </button>
        {filtersActive && (
          <p className="cust-filter-summary" role="status">
            <span>{translate(locale, "customerActiveFilters")}:</span>{" "}
            {statusFilter ? formatStatus(statusFilter, locale) : translate(locale, "customerAllStatuses")}{" · "}
            {departmentFilter ? getDepartmentLabel(departmentFilter, locale) : translate(locale, "customerAllDepartments")}
          </p>
        )}
      </div>

      <div className="cust-scroll-area">
        {error && (
          <div className="cust-error" role="alert" style={{ marginBottom: '1rem' }}>
            {error}
            <button type="button" className="cust-refresh-btn" onClick={onRefresh}>
              {translate(locale, "customerRetryHistory")}
            </button>
          </div>
        )}

      {loading && tickets.length === 0 ? (
        <div className="cust-empty">
          {translate(locale, "loading")}
        </div>
      ) : tickets.length === 0 ? (
        <div className="cust-empty">
          {filtersActive ? translate(locale, "customerFilteredEmpty") : translate(locale, "customerHistoryEmpty")}
        </div>
      ) : (
        <div className="cust-ticket-list">
          {tickets.map((t) => {
            const isSelected = t.complaintId === selectedTicketId;
            return (
              <button
                key={t.complaintId}
                type="button"
                onClick={() => onSelectTicket(t.complaintId)}
                className="cust-ticket-btn"
                aria-pressed={isSelected}
              >
                <div className="cust-ticket-top">
                  <span className="cust-ticket-id">
                    {translate(locale, "customerTicketId")}: {t.complaintId}
                  </span>
                  <span className={`cust-status-pill ${statusClass(t.status)}`}>
                    {formatStatus(t.status, locale)}
                  </span>
                </div>
                <div className="cust-ticket-date">
                  {new Date(t.createdAt).toLocaleDateString(
                    locale === "my" ? "my-MM" : "en-US",
                    { month: "short", day: "numeric", year: "numeric" }
                  )}
                </div>
              </button>
            );
          })}
        </div>
      )}
      {loadMoreError && (
        <div className="cust-error" role="alert">
          {loadMoreError}
          <button type="button" className="cust-refresh-btn" onClick={onLoadMore}>
            {translate(locale, "customerRetryHistory")}
          </button>
        </div>
      )}
      {hasMore && !loadMoreError && (
        <button
          type="button"
          className="cust-refresh-btn"
          onClick={onLoadMore}
          disabled={loadingMore}
          aria-busy={loadingMore}
        >
          {loadingMore ? translate(locale, "loading") : translate(locale, "customerLoadMore")}
        </button>
      )}
      </div>
    </div>
  );
}
