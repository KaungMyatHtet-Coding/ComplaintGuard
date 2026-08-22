import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    t: (key: string) => ({
      adminOverviewEyebrow: "Team overview",
      adminOverviewTitle: "Team directory overview",
      adminOverviewLead: "Visible profiles.",
      adminDirectoryVisibleCounts: "Staff/Manager directory counts",
      adminOverviewTotal: "Visible team accounts",
      adminOverviewStaff: "Staff profiles",
      adminOverviewManager: "Manager profiles",
      adminOverviewActive: "Active profiles",
      adminOverviewPending: "Pending profiles",
    }[key] ?? key),
  }),
}));

import { AdminOverview } from "./admin-overview";

describe("AdminOverview", () => {
  it("counts only visible Staff/Manager directory rows", () => {
    const markup = renderToStaticMarkup(<AdminOverview snapshot={{ state: "ready", rows: [
      { email: "staff@example.test", displayName: "Staff", locale: "en", role: "staff", departmentId: "card_atm", active: true, setupStatus: "active" },
      { email: "manager@example.test", displayName: "Manager", locale: "my", role: "manager", departmentId: null, active: false, setupStatus: "pending_setup" },
    ] }} />);
    expect(markup).toContain("Visible team accounts");
    expect(markup).toContain("Staff profiles");
    expect(markup).toContain("Manager profiles");
    expect(markup).not.toContain("all users");
    expect(markup).not.toContain("customer");
  });

  it("has truthful loading and empty states", () => {
    expect(renderToStaticMarkup(<AdminOverview snapshot={{ state: "loading", rows: [] }} />)).toContain("adminOverviewLoading");
    expect(renderToStaticMarkup(<AdminOverview snapshot={{ state: "empty", rows: [] }} />)).toContain("adminOverviewEmpty");
  });
});
