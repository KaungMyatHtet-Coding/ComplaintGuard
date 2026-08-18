"use client";

import React from "react";
import type { Locale } from "@/lib/i18n";
import { translate } from "@/lib/i18n";
import type { CustomerTicketSummary } from "@/lib/customer-workflow";

type CustomerTicketHistoryProps = {
  locale: Locale;
  tickets: CustomerTicketSummary[];
  selectedTicketId: string | null;
  onSelectTicket: (ticketId: string) => void;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
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
}: CustomerTicketHistoryProps) {
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

      <div className="cust-scroll-area">
        {error && (
          <div className="cust-error" role="alert" style={{ marginBottom: '1rem' }}>
            {error}
          </div>
        )}

      {loading && tickets.length === 0 ? (
        <div className="cust-empty">
          {translate(locale, "loading")}
        </div>
      ) : tickets.length === 0 ? (
        <div className="cust-empty">
          {translate(locale, "customerHistoryEmpty")}
        </div>
      ) : (
        <div className="cust-ticket-list">
          {tickets.map((t) => {
            const isSelected = t.id === selectedTicketId;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => onSelectTicket(t.id)}
                className="cust-ticket-btn"
                aria-pressed={isSelected}
              >
                <div className="cust-ticket-top">
                  <span className="cust-ticket-id">
                    {translate(locale, "customerTicketId")}: {t.id}
                  </span>
                  <span className={`cust-status-pill ${statusClass(t.status)}`}>
                    {formatStatus(t.status, locale)}
                  </span>
                </div>
                <p className="cust-ticket-summary">
                  {t.summaryText || translate(locale, "customerNoSummary")}
                </p>
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
      </div>
    </div>
  );
}
