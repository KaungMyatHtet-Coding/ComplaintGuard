import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    t: (key: string) => ({
      adminOverviewEyebrow: "Team overview",
      adminOverviewTitle: "Team directory overview",
      adminOverviewLead: "Visible profiles.",
      adminDirectoryVisibleCounts: "Visible loaded directory results",
      adminOverviewTotal: "Visible team accounts",
      adminOverviewCustomer: "Customer profiles",
      adminOverviewStaff: "Staff profiles",
      adminOverviewManager: "Manager profiles",
      adminOverviewAdmin: "Admin profiles",
      adminOverviewActive: "Active profiles",
      adminOverviewPending: "Pending profiles",
    }[key] ?? key),
  }),
}));

import { AdminOverview } from "./admin-overview";

describe("AdminOverview", () => {
  it("counts only visible all-role directory rows", () => {
    const markup = renderToStaticMarkup(<AdminOverview snapshot={{ state: "ready", rows: [
      { email: "customer@example.test", displayName: "Customer", locale: "en", role: "customer", departmentId: null, active: true, setupStatus: "active" },
      { email: "staff@example.test", displayName: "Staff", locale: "en", role: "staff", departmentId: "card_atm", active: true, setupStatus: "active" },
      { email: "manager@example.test", displayName: "Manager", locale: "my", role: "manager", departmentId: null, active: false, setupStatus: "pending_setup" },
      { email: "admin@example.test", displayName: "Admin", locale: "en", role: "admin", departmentId: null, active: true, setupStatus: "active" },
    ] }} />);
    expect(markup).toContain("Visible team accounts");
    expect(markup).toContain("Staff profiles");
    expect(markup).toContain("Manager profiles");
    expect(markup).toContain("Customer profiles");
    expect(markup).toContain("Admin profiles");
    expect(markup).not.toContain("all users");
  });

  it("has truthful loading and empty states", () => {
    expect(renderToStaticMarkup(<AdminOverview snapshot={{ state: "loading", rows: [] }} />)).toContain("adminOverviewLoading");
    expect(renderToStaticMarkup(<AdminOverview snapshot={{ state: "empty", rows: [] }} />)).toContain("adminOverviewEmpty");
  });
});
