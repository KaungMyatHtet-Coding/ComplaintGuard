import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { AppProvider } from "./app-provider";
import { ManagerLowConfidenceReview } from "./manager-low-confidence-review";

describe("ManagerLowConfidenceReview", () => {
  it("uses localized department names while preserving IDs only as form values", () => {
    const markup = renderToStaticMarkup(
      <AppProvider>
        <ManagerLowConfidenceReview
          tickets={[{
            id: "ticket_5c968a58-758d-43b8-a21b-555555555555555555555555",
            customerId: "customer-1",
            complaintText: "Synthetic ATM complaint",
            inputLocale: "en",
            predictedDepartmentId: "card_atm",
            predictionConfidence: 0.3,
            departmentId: "card_atm",
            status: "submitted",
            priority: "normal",
            routingSource: "manual_review",
            createdAt: "2026-08-11T00:00:00Z",
          }]}
          onOverride={vi.fn()}
        />
      </AppProvider>,
    );

    expect(markup).toContain("Card &amp; ATM");
    expect(markup).not.toContain(">card_atm<");
    expect(markup).toContain("manager-review-table");
    expect(markup).toContain("ticket-reference");
    expect(markup).toContain('tabindex="0"');
  });
});
