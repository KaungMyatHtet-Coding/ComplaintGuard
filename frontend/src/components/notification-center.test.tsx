import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    profile: { role: "customer" },
    locale: "en",
    signOut: vi.fn(),
    t: (key: string) => ({
      notificationBell: "Notifications",
      notificationCenterTitle: "Notification center",
      notificationClose: "Close notification center",
    })[key] ?? key,
  }),
}));

import { NotificationCenter } from "./notification-center";

describe("NotificationCenter", () => {
  it("renders an accessible bell without claiming unsupported role triggers", () => {
    const markup = renderToStaticMarkup(<NotificationCenter />);
    expect(markup).toContain('aria-label="Notifications"');
    expect(markup).toContain('aria-expanded="false"');
    expect(markup).not.toContain("complaintText");
    expect(markup).not.toContain("recipientUid");
  });
});
