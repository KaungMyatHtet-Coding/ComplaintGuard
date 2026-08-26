import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AppProvider } from "./app-provider";
import { CustomerTicketDetailView } from "./customer-ticket-detail";
import { translate, type MessageKey } from "@/lib/i18n";

const longTicketId = "ticket_" + "0".repeat(32);
const longMessage = "SyntheticVisualVerificationStringWithoutSpacesForResponsiveWrapping".repeat(4);

describe("CustomerTicketDetailView", () => {
  it("renders status-driven guidance for every allowed status in both locales", () => {
    const statuses = [
      "submitted", "triaged", "in_progress", "awaiting_customer", "resolved", "closed",
    ] as const;
    for (const status of statuses) {
      const ticket = {
        id: "ticket_" + "2".repeat(32),
        status,
        complaintText: "Synthetic complaint",
        inputLocale: "en" as const,
        departmentId: status === "submitted" ? null : "card_atm" as const,
        createdAt: "2026-08-11T00:00:00Z",
        updatedAt: "2026-08-11T00:00:00Z",
        resolvedAt: status === "resolved" || status === "closed" ? "2026-08-11T00:00:00Z" : null,
        timeline: [{ type: "complaint_received" as const, occurredAt: "2026-08-11T00:00:00Z", departmentId: null }],
        messages: [],
        feedback: null,
      };
      const english = renderToStaticMarkup(<CustomerTicketDetailView locale="en" ticket={ticket} loading={false} onSendMessage={vi.fn()} onCancelMessage={vi.fn()} onSubmitFeedback={vi.fn()} />);
      const myanmar = renderToStaticMarkup(<CustomerTicketDetailView locale="my" ticket={ticket} loading={false} onSendMessage={vi.fn()} onCancelMessage={vi.fn()} onSubmitFeedback={vi.fn()} />);
      const labelKey = ({ submitted: "statusSubmitted", triaged: "statusTriaged", in_progress: "statusInProgress", awaiting_customer: "statusAwaitingCustomer", resolved: "statusResolved", closed: "statusClosed" } as const)[status];
      const guidanceKey = `customerStatusGuidance${status === "awaiting_customer" ? "AwaitingCustomer" : status === "in_progress" ? "InProgress" : status[0].toUpperCase() + status.slice(1)}` as MessageKey;
      expect(english).toContain(translate("en", labelKey));
      expect(english).toContain(translate("en", guidanceKey));
      expect(myanmar).toContain(translate("my", labelKey));
      expect(myanmar).toContain(translate("my", guidanceKey));
      expect(myanmar).not.toMatch(/[\uFFFD]/u);
      expect(english).toContain("customer-status-guidance-title");
    }
  });

  it("uses ticket status rather than the final historical timeline event", () => {
    const ticket = {
      id: "ticket_" + "3".repeat(32), status: "awaiting_customer" as const,
      complaintText: "Synthetic complaint", inputLocale: "en" as const, departmentId: "card_atm" as const,
      createdAt: "2026-08-11T00:00:00Z", updatedAt: "2026-08-11T00:00:00Z", resolvedAt: null,
      timeline: [{ type: "complaint_resolved" as const, occurredAt: "2026-08-11T00:00:00Z", departmentId: null }], messages: [], feedback: null,
    };
    const markup = renderToStaticMarkup(<CustomerTicketDetailView locale="en" ticket={ticket} loading={false} onSendMessage={vi.fn()} onCancelMessage={vi.fn()} onSubmitFeedback={vi.fn()} />);
    expect(markup).toContain(translate("en", "statusAwaitingCustomer"));
    expect(markup).toContain(translate("en", "customerStatusGuidanceAwaitingCustomer"));
    expect(markup).not.toContain(translate("en", "customerStatusGuidanceResolved"));
  });

  it("does not render authoritative guidance while loading or without a ticket", () => {
    const props = { locale: "en" as const, ticket: null, loading: true, onSendMessage: vi.fn(), onCancelMessage: vi.fn(), onSubmitFeedback: vi.fn() };
    expect(renderToStaticMarkup(<CustomerTicketDetailView {...props} />)).not.toContain("customer-status-guidance-title");
    expect(renderToStaticMarkup(<CustomerTicketDetailView {...props} loading={false} />)).not.toContain("customer-status-guidance-title");
  });

  it("does not expose a fallback for an out-of-contract status", () => {
    const ticket = {
      id: "ticket_" + "5".repeat(32), status: "unknown_status" as never,
      complaintText: "Synthetic complaint", inputLocale: "en" as const, departmentId: null,
      createdAt: "2026-08-11T00:00:00Z", updatedAt: "2026-08-11T00:00:00Z", resolvedAt: null,
      timeline: [], messages: [], feedback: null,
    };
    const markup = renderToStaticMarkup(<CustomerTicketDetailView locale="en" ticket={ticket} loading={false} onSendMessage={vi.fn()} onCancelMessage={vi.fn()} onSubmitFeedback={vi.fn()} />);
    expect(markup).not.toContain("customer-status-guidance-title");
    expect(markup).not.toContain("unknown_status");
  });

  it("keeps closed messaging unavailable and resolved feedback behavior intact", () => {
    const base = { id: "ticket_" + "4".repeat(32), complaintText: "Synthetic complaint", inputLocale: "en" as const, departmentId: "card_atm" as const, createdAt: "2026-08-11T00:00:00Z", updatedAt: "2026-08-11T00:00:00Z", timeline: [], messages: [], feedback: null };
    const closed = renderToStaticMarkup(<CustomerTicketDetailView locale="en" ticket={{ ...base, status: "closed" as const, resolvedAt: "2026-08-11T00:00:00Z" }} loading={false} onSendMessage={vi.fn()} onCancelMessage={vi.fn()} onSubmitFeedback={vi.fn()} />);
    const resolved = renderToStaticMarkup(<CustomerTicketDetailView locale="en" ticket={{ ...base, status: "resolved" as const, resolvedAt: "2026-08-11T00:00:00Z" }} loading={false} onSendMessage={vi.fn()} onCancelMessage={vi.fn()} onSubmitFeedback={vi.fn()} />);
    expect(closed).toContain(translate("en", "customerStatusGuidanceClosed"));
    expect(closed).not.toContain("customer-message-input");
    expect(resolved).toContain(translate("en", "customerStatusGuidanceResolved"));
    expect(resolved).toContain("cust-feedback");
  });

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
