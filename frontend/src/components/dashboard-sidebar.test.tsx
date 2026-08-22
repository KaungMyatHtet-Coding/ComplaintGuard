import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({ t: (key: string) => ({
    dashboardNavOverview: "Overview",
    dashboardNavNewComplaint: "New complaint",
    dashboardNavHistory: "Complaint history",
    dashboardNavNotifications: "Notifications",
    dashboardNavQueue: "Department queue",
    dashboardNavOperations: "Operations",
    dashboardNavReview: "Low-confidence review",
    dashboardNavAnalytics: "Operational analytics",
    dashboardNavModelEvidence: "Model evidence",
    dashboardNavCreateAccount: "Create team account",
    dashboardNavAccounts: "Account directory",
    dashboardNavigationLabel: "Dashboard navigation",
    collapseNavigation: "Collapse dashboard navigation",
    expandNavigation: "Expand dashboard navigation",
  }[key] ?? key) }),
}));

import { DashboardSidebar, getDashboardNavigation } from "./dashboard-sidebar";

describe("dashboard navigation", () => {
  it("keeps role navigation limited to existing authorized destinations", () => {
    expect(getDashboardNavigation("customer").map((item) => item.href)).toEqual([
      "#overview", "#new-complaint", "#complaint-history", "#notification-center",
    ]);
    expect(getDashboardNavigation("staff").map((item) => item.href)).not.toContain("#my-work");
    expect(getDashboardNavigation("manager").map((item) => item.href)).toEqual([
      "#manager-operations", "#manager-review", "#manager-analytics", "#manager-model-evidence", "#notification-center",
    ]);
    expect(getDashboardNavigation("admin").map((item) => item.labelKey)).not.toContain("managerModelEvidence");
  });

  it("renders localized labels and accessible collapse control", () => {
    const markup = renderToStaticMarkup(<DashboardSidebar role="customer" expanded mobileOpen={false} onToggle={vi.fn()} onCloseMobile={vi.fn()} />);
    expect(markup).toContain("Complaint history");
    expect(markup).toContain("Collapse dashboard navigation");
    expect(markup).toContain('aria-current="page"');
  });
});
