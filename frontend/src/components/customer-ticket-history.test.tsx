import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { CustomerTicketHistory } from "./customer-ticket-history";

describe("CustomerTicketHistory", () => {
  it("keeps a long reference and its status badge in explicit overflow-safe elements", () => {
    const markup = renderToStaticMarkup(
      <CustomerTicketHistory
        locale="en"
        tickets={[{
          complaintId: "ticket_" + "1".repeat(32),
          status: "in_progress",
          departmentId: "card_atm",
          createdAt: "2026-08-11T00:00:00Z",
          updatedAt: "2026-08-11T00:00:00Z",
          resolvedAt: null,
        }]}
        selectedTicketId={"ticket_" + "1".repeat(32)}
        onSelectTicket={vi.fn()}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        loadingMore={false}
        loadMoreError={null}
        hasMore={false}
        onLoadMore={vi.fn()}
        statusFilter={null}
        departmentFilter={null}
        onFilterChange={vi.fn()}
      />,
    );

    expect(markup).toContain("ticket_" + "1".repeat(32));
    expect(markup).toContain("cust-ticket-top");
    expect(markup).toContain("cust-ticket-id");
    expect(markup).toContain("cust-status-pill");
    expect(markup).toContain("In progress");
  });

  it("localizes controls, labels, and empty summaries in Myanmar mode", () => {
    const markup = renderToStaticMarkup(
      <CustomerTicketHistory
        locale="my"
        tickets={[{
          complaintId: "ticket_" + "2".repeat(32),
          status: "submitted",
          departmentId: null,
          createdAt: "2026-08-11T00:00:00Z",
          updatedAt: "2026-08-11T00:00:00Z",
          resolvedAt: null,
        }]}
        selectedTicketId={null}
        onSelectTicket={vi.fn()}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        loadingMore={false}
        loadMoreError={null}
        hasMore={false}
        onLoadMore={vi.fn()}
        statusFilter={null}
        departmentFilter={null}
        onFilterChange={vi.fn()}
      />,
    );

    expect(markup).toContain("ပြန်လည် လန်းဆန်းမည်");
    expect(markup).toContain("တိုင်ကြားစာ အမှတ်");
    expect(markup).not.toContain("တိုင်ကြားစာ အကျဉ်း မရှိသေးပါ။");
    expect(markup).not.toContain(">Refresh<");
  });

  it("renders an accessible Load more control without legacy preview fields", () => {
    const markup = renderToStaticMarkup(
      <CustomerTicketHistory
        locale="en"
        tickets={[{
          complaintId: "ticket_" + "3".repeat(32),
          status: "submitted",
          departmentId: null,
          createdAt: "2026-08-11T00:00:00Z",
          updatedAt: "2026-08-11T00:00:00Z",
          resolvedAt: null,
        }]}
        selectedTicketId={null}
        onSelectTicket={vi.fn()}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        loadingMore={false}
        loadMoreError={null}
        hasMore
        onLoadMore={vi.fn()}
        statusFilter={null}
        departmentFilter={null}
        onFilterChange={vi.fn()}
      />,
    );
    expect(markup).toContain("Load more");
    expect(markup).toContain('type="button"');
    expect(markup).not.toContain("Synthetic complaint summary");
    expect(markup).not.toContain("Priority");
  });

  it("renders Closed explicitly", () => {
    const markup = renderToStaticMarkup(
      <CustomerTicketHistory
        locale="en"
        tickets={[{
          complaintId: "ticket_" + "4".repeat(32),
          status: "closed",
          departmentId: "general_support",
          createdAt: "2026-08-11T00:00:00Z",
          updatedAt: "2026-08-11T00:00:00Z",
          resolvedAt: "2026-08-11T00:00:00Z",
        }]}
        selectedTicketId={null}
        onSelectTicket={vi.fn()}
        loading={false}
        error={null}
        onRefresh={vi.fn()}
        loadingMore={false}
        loadMoreError={null}
        hasMore={false}
        onLoadMore={vi.fn()}
        statusFilter={"closed"}
        departmentFilter={null}
        onFilterChange={vi.fn()}
      />,
    );
    expect(markup).toContain("Closed");
  });
});
