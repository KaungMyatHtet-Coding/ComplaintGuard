import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { StaffTicketRow } from "./staff-ticket-queue";

const longTicketId = "ticket_a2b7c7e5-5a3d-4fb9-bc2e-333333333333333333333333";

describe("StaffTicketRow", () => {
  it("renders long queue references and statuses with the responsive row contract", () => {
    const markup = renderToStaticMarkup(
      <StaffTicketRow
        ticket={{
          ticketId: longTicketId,
          customerId: "customer-1",
          complaintText: "Synthetic complaint text",
          inputLocale: "en",
          departmentId: "card_atm",
          status: "triaged",
          priority: "normal",
          assignedStaffId: null,
          predictedDepartmentId: "card_atm",
          predictionConfidence: 0.7,
          routingSource: "model",
          escalated: false,
          resolutionSummary: null,
          createdAt: "2026-08-11T00:00:00Z",
          updatedAt: "2026-08-11T00:00:00Z",
          resolvedAt: null,
        }}
        locale="en"
        selected={false}
        statusLabel="Triaged"
        priorityLabel="Normal"
        onSelect={vi.fn()}
      />,
    );

    expect(markup).toContain(longTicketId);
    expect(markup).toContain("ticket-row");
    expect(markup).toContain("ticket-reference");
    expect(markup).toContain("ticket-status-badge");
    expect(markup).toContain("Triaged");
  });
});
