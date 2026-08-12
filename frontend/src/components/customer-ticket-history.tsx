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

export function CustomerTicketHistory({
  locale,
  tickets,
  selectedTicketId,
  onSelectTicket,
  loading,
  error,
  onRefresh,
}: CustomerTicketHistoryProps) {
  const getStatusBadge = (status: string) => {
    switch (status) {
      case "resolved":
      case "closed":
        return "bg-green-100 text-green-800 border-green-300";
      case "in_progress":
      case "awaiting_customer":
        return "bg-blue-100 text-blue-800 border-blue-300";
      case "triaged":
        return "bg-yellow-100 text-yellow-800 border-yellow-300";
      default:
        return "bg-gray-100 text-gray-800 border-gray-300";
    }
  };

  const formatStatus = (status: string) => {
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
  };

  return (
    <div className="bg-white rounded-lg border border-gray-200 shadow-sm p-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-gray-900">
          {translate(locale, "customerHistoryTitle")}
        </h3>
        <button
          type="button"
          onClick={onRefresh}
          disabled={loading}
          className="text-xs bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium py-1 px-3 rounded transition-colors"
        >
          {loading ? translate(locale, "loading") : translate(locale, "customerRefreshHistory")}
        </button>
      </div>

      {error && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 text-red-700 text-sm rounded">
          {error}
        </div>
      )}

      {loading && tickets.length === 0 ? (
        <div className="py-8 text-center text-sm text-gray-500">
          {translate(locale, "loading")}
        </div>
      ) : tickets.length === 0 ? (
        <div className="py-8 text-center text-sm text-gray-500 bg-gray-50 rounded border border-dashed border-gray-200">
          {translate(locale, "customerHistoryEmpty")}
        </div>
      ) : (
        <div className="space-y-2 max-h-96 overflow-y-auto pr-1">
          {tickets.map((t) => {
            const isSelected = t.id === selectedTicketId;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => onSelectTicket(t.id)}
                className={`w-full text-left p-3 rounded-lg border transition-all ${
                  isSelected
                    ? "border-blue-600 bg-blue-50/50 shadow-sm"
                    : "border-gray-200 hover:border-gray-300 hover:bg-gray-50"
                }`}
              >
                <div className="ticket-summary-header mb-1">
                  <span className="ticket-reference font-mono text-xs text-gray-500">
                    {translate(locale, "customerTicketId")}: {t.id}
                  </span>
                  <span
                    className={`ticket-status-badge inline-block px-2 py-0.5 text-xs font-semibold rounded-full border ${getStatusBadge(
                      t.status
                    )}`}
                  >
                    {formatStatus(t.status)}
                  </span>
                </div>
                <p className="text-sm font-medium text-gray-900 line-clamp-2">
                  {t.summaryText || translate(locale, "customerNoSummary")}
                </p>
                <div className="mt-2 text-xs text-gray-400">
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
  );
}
