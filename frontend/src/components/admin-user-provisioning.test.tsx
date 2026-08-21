import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    locale: "en",
    t: (key: string) => key,
  }),
}));

import { AdminUserProvisioning } from "./admin-user-provisioning";

describe("AdminUserProvisioning", () => {
  it("renders accessible bilingual-ready Staff/Manager provisioning controls without credentials", () => {
    const markup = renderToStaticMarkup(<AdminUserProvisioning />);
    expect(markup).toContain('for="admin-role"');
    expect(markup).toContain('for="admin-email"');
    expect(markup).toContain('for="admin-display-name"');
    expect(markup).toContain('for="admin-locale"');
    expect(markup).toContain('for="admin-department"');
    expect(markup).toContain("adminStaff");
    expect(markup).toContain("adminManager");
    expect(markup).not.toContain("password");
    expect(markup).not.toContain("uid");
  });
});
