import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AppProvider } from "./app-provider";
import { CustomerTicketDetailView } from "./customer-ticket-detail";

const longTicketId = "ticket_0dc5f6c2-3c20-4d14-9bba-222222222222222222222222";
const longMessage = "SyntheticVisualVerificationStringWithoutSpacesForResponsiveWrapping".repeat(4);

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
            messages: [
              {
                id: "message-1",
                senderId: "staff-1",
                senderRole: "staff",
                text: longMessage,
                createdAt: "2026-08-11T00:00:00Z",
              },
              {
                id: "message-2",
                senderId: "customer-1",
                senderRole: "customer",
                text: "မြန်မာစာအရှည်အတွက်စာသား",
                createdAt: "2026-08-11T00:01:00Z",
              },
            ],
          }}
          loading={false}
          onSendMessage={vi.fn()}
          onSubmitFeedback={vi.fn()}
        />
      </AppProvider>,
    );

    expect(markup).toContain(longTicketId);
    expect(markup).toContain("cust-detail-header");
    expect(markup).toContain("cust-ticket-id");
    expect(markup).toContain('class="cust-ticket-id"');
    expect(markup).toContain("Messages");
    expect(markup).toContain("cust-timeline");
    expect(markup).toContain("Waiting for your reply");
    expect(markup).toContain("Synthetic complaint text");
    const css = readFileSync(new URL("../app/globals.css", import.meta.url), "utf8");
    expect(css).toContain(".cust-ticket-id");
    expect(css).toContain("overflow-wrap: anywhere");
    expect(markup).not.toContain("Model confidence");
    expect(markup).not.toContain("Operational threshold");
    expect(markup).not.toContain("Privacy-safe model evidence");
    expect(markup).not.toContain("TF-IDF");
    expect(markup).not.toContain("Dataset evidence");
  });
});
