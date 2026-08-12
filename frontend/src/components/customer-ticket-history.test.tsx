import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { CustomerTicketHistory } from "./customer-ticket-history";

const longTicketId = "ticket_9e9669cd-76f0-4e27-9b75-111111111111111111111111";

describe("CustomerTicketHistory", () => {
  it("keeps a long reference and its status badge in explicit overflow-safe elements", () => {
    const markup = renderToStaticMarkup(
      <CustomerTicketHistory
        locale="en"
        tickets={[{
          id: longTicketId,
          status: "in_progress",
          createdAt: "2026-08-11T00:00:00Z",
          updatedAt: "2026-08-11T00:00:00Z",
          summaryText: "Synthetic complaint summary",
        }]}
        selectedTicketId={longTicketId}
        onSelectTicket={vi.fn()}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(markup).toContain(longTicketId);
    expect(markup).toContain("ticket-summary-header");
    expect(markup).toContain("ticket-reference");
    expect(markup).toContain("ticket-status-badge");
    expect(markup).toContain("In progress");
  });

  it("localizes controls, labels, and empty summaries in Myanmar mode", () => {
    const markup = renderToStaticMarkup(
      <CustomerTicketHistory
        locale="my"
        tickets={[{
          id: longTicketId,
          status: "submitted",
          createdAt: "2026-08-11T00:00:00Z",
          updatedAt: "2026-08-11T00:00:00Z",
          summaryText: "",
        }]}
        selectedTicketId={null}
        onSelectTicket={vi.fn()}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
      />,
    );

    expect(markup).toContain("ပြန်လည် လန်းဆန်းမည်");
    expect(markup).toContain("တိုင်ကြားစာ အမှတ်");
    expect(markup).toContain("တိုင်ကြားစာ အကျဉ်း မရှိသေးပါ။");
    expect(markup).not.toContain(">Refresh<");
  });
});
