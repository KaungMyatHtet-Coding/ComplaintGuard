import { describe, expect, it } from "vitest";

import { normalizeLocale, translate } from "./i18n";

describe("localization foundation", () => {
  it("supports English and Myanmar UI copy", () => {
    expect(translate("en", "loginTitle")).toBe("Sign in");
    expect(translate("en", "complaintTitle")).toBe("Submit a complaint");
    expect(translate("my", "complaintTitle")).toContain("တိုင်ကြားချက်");
    expect(translate("en", "staffQueueTitle")).toBe("Department complaint queue");
    expect(translate("my", "staffQueueTitle")).toContain("ဌာန");
    expect(translate("en", "status_awaiting_customer")).toBe("Awaiting customer");
    for (const key of [
      "staffLoading",
      "staffEmpty",
      "staffBackendError",
      "staffDetailTitle",
      "staffStatusFilter",
      "staffPriorityFilter",
      "staffDateFrom",
      "staffRequestReassignment",
      "staffRequestEscalation",
      "status_triaged",
      "priority_urgent",
      "modelAnalyticsTitle",
      "confidenceNotAccuracy",
      "evidenceTitle",
      "evidenceSimilarityLocalOnly",
      "managerDashboardLoading",
    ] as const) {
      expect(translate("en", key)).not.toMatch(/^\[/u);
      expect(translate("my", key)).not.toMatch(/^\[/u);
    }
    expect(translate("my", "modelAnalyticsTitle")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "evidenceTitle")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "loginTitle")).toContain("အကောင့်");
  });

  it("falls back to English for unsupported locale values", () => {
    expect(normalizeLocale("fr")).toBe("en");
    expect(normalizeLocale(null)).toBe("en");
  });
});
