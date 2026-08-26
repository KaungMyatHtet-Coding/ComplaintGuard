import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    locale: "en",
    profile: { role: "customer", displayName: "Mg Mg", departmentId: null },
    t: (key: string) => ({
      dashboardWelcome: "Welcome",
      dashboardWorkspaceLabel: "Your workspace",
      dashboardCustomerSupport: "Follow complaints.",
      dashboardFallbackName: "there",
      skipToContent: "Skip to dashboard content",
      closeNavigation: "Close dashboard navigation",
    }[key] ?? key),
  }),
}));
vi.mock("@/components/app-header", () => ({ AppHeader: () => <header>Header</header> }));

import { DashboardShell } from "./dashboard-shell";

describe("DashboardShell", () => {
  it("provides skip navigation, one main landmark, and a compact personalized heading", () => {
    const markup = renderToStaticMarkup(<DashboardShell><section>Content</section></DashboardShell>);
    expect(markup).toContain("Skip to dashboard content");
    expect(markup).toContain("Welcome, Mg Mg");
    expect((markup.match(/<main /g) ?? []).length).toBe(1);
    expect(markup).not.toContain(">Dashboard<");
  });
});
