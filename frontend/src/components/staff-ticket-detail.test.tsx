import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { StaffTicketMetadata } from "./staff-ticket-detail";
import { StaffResolutionDetails } from "./staff-resolution-details";

describe("StaffResolutionDetails", () => {
  it("renders the complete saved resolution summary and resolved timestamp", () => {
    const summary = "Unauthorized withdrawal report reviewed. Customer confirmed account access.";
    const formatDate = vi.fn(() => "Aug 8, 2026, 3:54 PM");

    const markup = renderToStaticMarkup(
      <StaffResolutionDetails
        resolutionSummary={summary}
        resolvedAt="2026-08-08T15:54:14.452Z"
        resolutionLabel="Resolution summary"
        resolvedAtLabel="Resolved at"
        formatDate={formatDate}
      />,
    );

    expect(markup).toContain(summary);
    expect(markup).toContain("Resolution summary");
    expect(markup).toContain("Resolved at");
    expect(markup).toContain("Aug 8, 2026, 3:54 PM");
    expect(markup).toContain('dateTime="2026-08-08T15:54:14.452Z"');
    expect(formatDate).toHaveBeenCalledWith(new Date("2026-08-08T15:54:14.452Z"));
  });

  it("does not render an empty resolution block for an unresolved ticket", () => {
    const formatDate = vi.fn(() => "unused");

    const markup = renderToStaticMarkup(
      <StaffResolutionDetails
        resolutionSummary={null}
        resolvedAt={null}
        resolutionLabel="Resolution summary"
        resolvedAtLabel="Resolved at"
        formatDate={formatDate}
      />,
    );

    expect(markup).toBe("");
    expect(formatDate).not.toHaveBeenCalled();
  });
});

describe("StaffTicketMetadata", () => {
  it("uses the ticket reference overflow contract in the responsive metadata grid", () => {
    const ticketId = "ticket_7cd45298-8c0a-4827-b1a1-444444444444444444444444";
    const markup = renderToStaticMarkup(
      <StaffTicketMetadata
        ticketId={ticketId}
        referenceLabel="Reference"
        statusTitle="Status"
        statusLabel="Triaged"
        priorityTitle="Priority"
        priorityLabel="Normal"
        createdTitle="Created"
        updatedTitle="Updated"
        createdAtLabel="Aug 11, 2026"
        updatedAtLabel="Aug 12, 2026"
        departmentTitle="Department"
        departmentLabel="Card & ATM Support"
      />,
    );

    expect(markup).toContain("ticket-metadata");
    expect(markup).toContain("ticket-reference");
    expect(markup).toContain(ticketId);
  });
});

describe("Staff ticket tab workspace", () => {
  const source = readFileSync(new URL("./staff-ticket-detail.tsx", import.meta.url), "utf8");

  it("defines an accessible tab pattern with keyboard navigation and button controls", () => {
    expect(source).toContain('role="tablist"');
    expect(source).toContain('role="tab"');
    expect(source).toContain('role="tabpanel"');
    expect(source).toContain('aria-controls={`staff-panel-${tab.id}`}');
    expect(source).toContain('aria-labelledby="staff-tab-overview"');
    expect(source).toContain('event.key === "ArrowRight"');
    expect(source).toContain('event.key === "ArrowLeft"');
    expect(source).toContain('event.key === "Home"');
    expect(source).toContain('event.key === "End"');
    expect(source).toContain('type="button"');
    expect(source).toContain('useState<"overview" | "messages" | "activity" | "model">("overview")');
  });

  it("keeps technical evidence in Model Data and localizes activity events", () => {
    expect(source).toContain('activeTab === "model"');
    expect(source).toContain("DatasetEvidencePanel");
    expect(source).toContain("staff_reply");
    expect(source).toContain("customer_reply");
    expect(source).toContain("status_transition");
    expect(source).toContain("manager_override");
    expect(source).toContain('return labels[type] ?? t("staffEventUpdate")');
    expect(source).not.toContain("event.type}</strong>");
  });
});
