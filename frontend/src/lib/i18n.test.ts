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
      "adminLifecycleManagementTitle",
      "adminLifecycleLoading",
      "adminLifecycleEligibilityTitle",
      "adminLifecycleOperationDisable",
      "adminLifecycleOperationReactivate",
      "adminLifecycleOperationReassign",
      "adminLifecycleRecoveryTitle",
      "adminLifecycleOperatorRequired",
      "adminDirectoryState_active",
      "adminDirectoryState_pending_setup",
      "adminDirectoryState_disabled",
      "adminDirectoryState_inactive_unverified",
      "adminDetailStateActive",
      "adminDetailStatePending",
      "adminDetailStateDisabled",
      "adminDetailStateUnavailable",
    ] as const) {
      expect(translate("en", key)).not.toMatch(/^\[/u);
      expect(translate("my", key)).not.toMatch(/^\[/u);
    }
    expect(translate("my", "adminLifecycleManagementTitle")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "adminLifecycleOperatorRequired")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("en", "adminDirectoryState_disabled")).toBe("Disabled");
    expect(translate("en", "adminDirectoryState_inactive_unverified")).toBe("Inactive status unavailable");
    expect(translate("my", "adminDirectoryState_pending_setup")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "adminDirectoryState_disabled")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "adminDirectoryState_pending_setup")).not.toBe(translate("my", "adminDirectoryState_disabled"));
    expect(translate("my", "modelAnalyticsTitle")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "evidenceTitle")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("en", "evidencePredictionConfidence")).toBe("Model confidence");
    expect(translate("my", "evidencePredictionConfidence")).toBe(
      "မော်ဒယ် ယုံကြည်မှု",
    );
    expect(translate("en", "evidenceConfidenceExplanation")).toContain(
      "does not guarantee correctness",
    );
    expect(translate("my", "loginTitle")).toContain("အကောင့်");
  });

  it("falls back to English for unsupported locale values", () => {
    expect(normalizeLocale("fr")).toBe("en");
    expect(normalizeLocale(null)).toBe("en");
  });
});
