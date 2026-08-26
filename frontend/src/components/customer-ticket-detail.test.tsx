import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AppProvider } from "./app-provider";
import { CustomerTicketDetailView } from "./customer-ticket-detail";
import { translate } from "@/lib/i18n";

const longTicketId = "ticket_" + "0".repeat(32);
const longMessage = "SyntheticVisualVerificationStringWithoutSpacesForResponsiveWrapping".repeat(4);

describe("CustomerTicketDetailView", () => {
  it("localizes server-projected timeline labels in English and Myanmar", () => {
    const ticket = {
      id: "ticket_" + "1".repeat(32),
      status: "in_progress" as const,
      complaintText: "Synthetic complaint",
      inputLocale: "en" as const,
      departmentId: "card_atm" as const,
      createdAt: "2026-08-11T00:00:00Z",
      updatedAt: "2026-08-11T00:00:00Z",
      resolvedAt: null,
      timeline: [{ type: "team_replied" as const, occurredAt: "2026-08-11T00:01:00Z", departmentId: null }],
      messages: [],
      feedback: null,
    };

    const english = renderToStaticMarkup(
      <CustomerTicketDetailView
        locale="en"
        ticket={ticket}
        loading={false}
        onSendMessage={vi.fn()}
        onCancelMessage={vi.fn()}
        onSubmitFeedback={vi.fn()}
      />,
    );
    const myanmar = renderToStaticMarkup(
      <CustomerTicketDetailView
        locale="my"
        ticket={ticket}
        loading={false}
        onSendMessage={vi.fn()}
        onCancelMessage={vi.fn()}
        onSubmitFeedback={vi.fn()}
      />,
    );

    expect(english).toContain(translate("en", "customerTimelineTeamReplied"));
    expect(myanmar).toContain(translate("my", "customerTimelineTeamReplied"));
  });

  it("keeps a long reference in the responsive detail header", () => {
    const markup = renderToStaticMarkup(
      <AppProvider>
        <CustomerTicketDetailView
          locale="en"
          ticket={{
            id: longTicketId,
            status: "in_progress" as const,
            complaintText: "Synthetic complaint text",
            inputLocale: "en" as const,
            departmentId: "card_atm" as const,
            timeline: [
              { type: "complaint_received", occurredAt: "2026-08-11T00:00:00Z", departmentId: null },
              { type: "review_started", occurredAt: "2026-08-11T00:01:00Z", departmentId: null },
            ],
            resolvedAt: null,
            feedback: null,
            createdAt: "2026-08-11T00:00:00Z",
            updatedAt: "2026-08-11T00:00:00Z",
            messages: [
              {
                senderRole: "support_team",
                body: longMessage,
                createdAt: "2026-08-11T00:00:00Z",
              },
              {
                senderRole: "customer",
                body: "မြန်မာစာအရှည်အတွက်စာသား",
                createdAt: "2026-08-11T00:01:00Z",
              },
            ],
          }}
          loading={false}
          onSendMessage={vi.fn()}
          onCancelMessage={vi.fn()}
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
    expect(markup).toContain("Team started reviewing");
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
