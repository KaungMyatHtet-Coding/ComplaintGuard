import { readFileSync } from "node:fs";
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
            manualReviewReason: "low_prediction_confidence",
            detectedLanguage: "en",
          }]}
          onOverride={vi.fn()}
        />
      </AppProvider>,
    );

    expect(markup).toContain("Card &amp; ATM");
    expect(markup).not.toContain(">card_atm<");
    expect(markup).toContain('class="mng-table"');
    expect(markup).toContain("ticket-reference");
    expect(markup).toContain('tabindex="0"');
  });

  it("has explicit confirm and alternate-department decisions and preserves the full narrative view", () => {
    const source = readFileSync(new URL("./manager-low-confidence-review.tsx", import.meta.url), "utf8");
    expect(source).toContain("managerConfirmAiSuggestion");
    expect(source).toContain("managerChooseDepartment");
    expect(source).toContain("whiteSpace: \"pre-wrap\"");
    expect(source).toContain("hasReliableSuggestion");
  });
});
