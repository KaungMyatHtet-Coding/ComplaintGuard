import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    profile: {
      role: "customer",
    },
    signOut: vi.fn(),
    setLocale: vi.fn(),
    locale: "en",
    t: (key: string) =>
      ({
        brand: "ComplaintGuard",
        language: "Language",
        english: "English",
        myanmar: "Myanmar",
        signOut: "Sign out",
      })[key] ?? key,
  }),
}));

import { AppHeader } from "./app-header";

describe("AppHeader", () => {
  it("keeps the role, language, and sign-out controls available", () => {
    const markup = renderToStaticMarkup(<AppHeader />);

    expect(markup).toContain('class="header-actions"');
    expect(markup).toContain('class="role-chip"');
    expect(markup).toContain('class="language-switcher"');
    expect(markup).toContain("English");
    expect(markup).toContain("Myanmar");
    expect(markup).toContain("Sign out");
  });
});
