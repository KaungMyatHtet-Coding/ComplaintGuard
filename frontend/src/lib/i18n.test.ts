import { describe, expect, it } from "vitest";

import { normalizeLocale, translate } from "./i18n";

describe("localization foundation", () => {
  it("covers public navigation and presentation copy in both locales", () => {
    const keys = [
      "backToHome",
      "authenticationNavigation",
      "publicWhatTitle",
      "publicWhatItems",
      "publicHowTitle",
      "publicHowItems",
      "publicWhyTitle",
      "publicWhyItems",
      "publicOversightTitle",
      "publicOversight",
      "publicPrivacyTitle",
      "publicPrivacyItems",
      "publicScopeTitle",
      "publicScope",
      "publicCtaTitle",
    ] as const;
    for (const key of keys) {
      expect(translate("en", key)).not.toMatch(/^\[/u);
      expect(translate("my", key)).toMatch(/[\u1000-\u109f]/u);
      expect(translate("my", key)).not.toMatch(/[\uFFFD]/u);
    }
  });

  it("supports English and Myanmar UI copy", () => {
    expect(translate("en", "loginTitle")).toBe("Sign in");
    expect(translate("en", "complaintTitle")).toBe("Submit a complaint");
    expect(translate("en", "closeComplaintDialog")).toBe("Close complaint dialog");
    expect(translate("my", "closeComplaintDialog")).toMatch(/[\u1000-\u109f]/u);
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
      "complaintUnknownOutcome",
      "complaintRetryUnknown",
      "complaintUnknownEdit",
    ] as const) {
      expect(translate("en", key)).not.toMatch(/^\[/u);
      expect(translate("my", key)).not.toMatch(/^\[/u);
    }
    expect(translate("my", "adminLifecycleManagementTitle")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "adminLifecycleOperatorRequired")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("en", "complaintUnknownOutcome")).toContain("could not confirm");
    expect(translate("en", "complaintRetryUnknown")).toBe("Retry safely");
    expect(translate("my", "complaintUnknownOutcome")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "complaintRetryUnknown")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "complaintUnknownOutcome")).not.toMatch(/[\uFFFD]/u);
    expect(translate("my", "complaintRetryUnknown")).not.toMatch(/[\uFFFD]/u);
    expect(translate("en", "complaintUnknownEdit")).toContain("restore");
    expect(translate("my", "complaintUnknownEdit")).toMatch(/[\u1000-\u109f]/u);
    expect(translate("my", "complaintUnknownEdit")).not.toMatch(/[\uFFFD]/u);
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

  it("provides localized Customer History filter labels", () => {
    const keys = [
      "customerHistoryFilters", "customerStatusFilter", "customerStatusFilterHelp",
      "customerAllStatuses", "customerDepartmentFilter", "customerDepartmentFilterHelp",
      "customerAllDepartments", "customerClearFilters", "customerActiveFilters",
      "customerFilteredEmpty",
    ] as const;
    for (const key of keys) {
      expect(translate("en", key)).not.toBe("");
      expect(translate("my", key)).not.toBe("");
      expect(translate("my", key)).not.toMatch(/[\uFFFD]/u);
    }
    expect(translate("en", "statusClosed")).toBe("Closed");
    expect(translate("en", "statusClosed")).not.toBe(translate("en", "statusSubmitted"));
    expect(translate("my", "statusClosed")).toMatch(/[\u1000-\u109f]/u);
  });

  it("provides complete English and Myanmar Customer status guidance", () => {
    const keys = [
      "customerCurrentStatus", "customerWhatHappensNext",
      "customerStatusGuidanceSubmitted", "customerStatusGuidanceTriaged",
      "customerStatusGuidanceInProgress", "customerStatusGuidanceAwaitingCustomer",
      "customerStatusGuidanceResolved", "customerStatusGuidanceClosed",
    ] as const;
    for (const key of keys) {
      expect(translate("en", key)).not.toMatch(/^\[/u);
      expect(translate("my", key)).toMatch(/[\u1000-\u109f]/u);
      expect(translate("my", key)).not.toMatch(/[\uFFFD]/u);
    }
  });

  it("provides localized safe Customer message retry states", () => {
    for (const key of [
      "customerSending",
      "customerMessageUnknownOutcome",
      "customerMessageRetry",
      "customerMessageIdempotencyConflict",
      "customerMessageClosedConflict",
      "customerMessageSafeFailure",
      "customerCloseMessages",
    ] as const) {
      expect(translate("en", key)).not.toMatch(/^\[/u);
      expect(translate("my", key)).toMatch(/[\u1000-\u109f]/u);
      expect(translate("my", key)).not.toMatch(/[\uFFFD]/u);
    }
  });
});
