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
      adminOverviewDisabled: "Disabled profiles",
      adminOverviewInactiveUnavailable: "Inactive status unavailable",
    }[key] ?? key),
  }),
}));

import { AdminOverview } from "./admin-overview";

describe("AdminOverview", () => {
  it("counts only visible all-role directory rows", () => {
    const markup = renderToStaticMarkup(<AdminOverview snapshot={{ state: "ready", rows: [
      { accountRef: "acct_v1_0000000000000000000000000000000000000000000000000000000000000000", email: "customer@example.test", displayName: "Customer", locale: "en", role: "customer", departmentId: null, active: true, accountState: "active" },
      { accountRef: "acct_v1_1111111111111111111111111111111111111111111111111111111111111111", email: "staff@example.test", displayName: "Staff", locale: "en", role: "staff", departmentId: "card_atm", active: true, accountState: "active" },
      { accountRef: "acct_v1_2222222222222222222222222222222222222222222222222222222222222222", email: "manager@example.test", displayName: "Manager", locale: "my", role: "manager", departmentId: null, active: false, accountState: "pending_setup" },
      { accountRef: "acct_v1_3333333333333333333333333333333333333333333333333333333333333333", email: "admin@example.test", displayName: "Admin", locale: "en", role: "admin", departmentId: null, active: false, accountState: "disabled" },
    ] }} />);
    expect(markup).toContain("Visible team accounts");
    expect(markup).toContain("Staff profiles");
    expect(markup).toContain("Manager profiles");
    expect(markup).toContain("Customer profiles");
    expect(markup).toContain("Admin profiles");
    expect(markup).toContain("Pending profiles");
    expect(markup).toContain("Disabled profiles");
    expect(markup).toContain("Inactive status unavailable");
    expect(markup).not.toContain("all users");
  });

  it("has truthful loading and empty states", () => {
    expect(renderToStaticMarkup(<AdminOverview snapshot={{ state: "loading", rows: [] }} />)).toContain("adminOverviewLoading");
    expect(renderToStaticMarkup(<AdminOverview snapshot={{ state: "empty", rows: [] }} />)).toContain("adminOverviewEmpty");
  });
});
