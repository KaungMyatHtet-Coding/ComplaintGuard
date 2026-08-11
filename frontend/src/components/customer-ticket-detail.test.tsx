import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AppProvider } from "./app-provider";
import { CustomerTicketDetailView } from "./customer-ticket-detail";

const longTicketId = "ticket_0dc5f6c2-3c20-4d14-9bba-222222222222222222222222";

describe("CustomerTicketDetailView", () => {
  it("keeps a long reference in the responsive detail header", () => {
    const markup = renderToStaticMarkup(
      <AppProvider>
        <CustomerTicketDetailView
          locale="en"
          ticket={{
            id: longTicketId,
            customerId: "customer-1",
            status: "in_progress",
            complaintText: "Synthetic complaint text",
            inputLocale: "en",
            priority: "normal",
            createdAt: "2026-08-11T00:00:00Z",
            updatedAt: "2026-08-11T00:00:00Z",
            messages: [],
          }}
          loading={false}
          onSendMessage={vi.fn()}
          onSubmitFeedback={vi.fn()}
        />
      </AppProvider>,
    );

    expect(markup).toContain(longTicketId);
    expect(markup).toContain("ticket-detail-header");
    expect(markup).toContain("ticket-reference");
    expect(markup).toContain("break-words");
  });
});
