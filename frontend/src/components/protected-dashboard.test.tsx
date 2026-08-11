import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: vi.fn() }),
}));

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    locale: "en",
    profile: {
      role: "staff",
      displayName: "Synthetic Card Staff",
      departmentId: "card_atm",
    },
    status: "authenticated",
    t: (key: string) => key,
  }),
}));

vi.mock("@/components/app-header", () => ({ AppHeader: () => null }));
vi.mock("@/components/customer-dashboard-workflow", () => ({ CustomerDashboardWorkflow: () => null }));
vi.mock("@/components/manager-dashboard-workflow", () => ({ ManagerDashboardWorkflow: () => null }));
vi.mock("@/components/staff-ticket-queue", () => ({ StaffTicketQueue: () => null }));

import { ProtectedDashboard } from "./protected-dashboard";

describe("ProtectedDashboard", () => {
  it("renders a localized staff department label instead of the raw ID", () => {
    const markup = renderToStaticMarkup(<ProtectedDashboard />);

    expect(markup).toContain("Card &amp; ATM");
    expect(markup).not.toContain(">card_atm<");
  });
});
