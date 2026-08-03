"use client";

import { useApp } from "@/components/app-provider";
import type { CustomerTicketSummary } from "@/lib/customer-workflow";

type CustomerTicketHistoryProps = {
  tickets: CustomerTicketSummary[];
  selectedTicketId: string | null;
  onSelectTicket: (ticketId: string) => void;
  onRefresh: () => void;
};

export function CustomerTicketHistory({
  tickets,
  selectedTicketId,
  onSelectTicket,
  onRefresh,
}: CustomerTicketHistoryProps) {
  const { t } = useApp();

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h3 className="text-lg font-bold text-gray-900">{t("customerHistoryTitle")}</h3>
        <button
          type="button"
          onClick={onRefresh}
          className="px-3 py-1.5 text-xs font-semibold bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg transition"
        >
          {t("customerRefreshHistory")}
        </button>
      </div>

      {tickets.length === 0 ? (
        <p className="p-4 text-sm text-gray-500 bg-gray-50 rounded-lg border border-gray-200 text-center">
          {t("customerHistoryEmpty")}
        </p>
      ) : (
        <div className="space-y-2">
          {tickets.map((tItem) => {
            const isSelected = tItem.id === selectedTicketId;
            return (
              <button
                key={tItem.id}
                type="button"
                onClick={() => onSelectTicket(tItem.id)}
                className={`w-full text-left p-4 rounded-xl border transition ${
                  isSelected
                    ? "border-blue-500 bg-blue-50/50 shadow-sm"
                    : "border-gray-200 bg-white hover:border-gray-300"
                }`}
              >
                <div className="flex justify-between items-start mb-1">
                  <span className="font-mono text-xs font-bold text-gray-700">
                    ID: {tItem.id}
                  </span>
                  <span
                    className={`px-2 py-0.5 text-xs font-bold rounded-full ${
                      tItem.status === "resolved"
                        ? "bg-emerald-100 text-emerald-800"
                        : "bg-blue-100 text-blue-800"
                    }`}
                  >
                    {tItem.status.replace("_", " ")}
                  </span>
                </div>
                <p className="text-sm font-medium text-gray-900 line-clamp-2">
                  {tItem.complaintText}
                </p>
                <p className="text-xs text-gray-500 mt-2">
                  {new Date(tItem.createdAt).toLocaleDateString()}
                </p>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
