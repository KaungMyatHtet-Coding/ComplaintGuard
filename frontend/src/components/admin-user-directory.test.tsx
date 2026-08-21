import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

const state = vi.hoisted(() => ({ profile: { role: "admin", active: true, departmentId: null } as { role: string; active: boolean; departmentId: null } | null }));
vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    locale: "en",
    profile: state.profile,
    t: (key: string) => key,
  }),
}));
vi.mock("@/lib/admin-directory", () => ({ loadAdminDirectory: vi.fn(() => new Promise(() => undefined)) }));

import { AdminUserDirectory } from "./admin-user-directory";

describe("AdminUserDirectory", () => {
  it("renders read-only accessible filters and no mutation controls", () => {
    const markup = renderToStaticMarkup(<AdminUserDirectory />);
    expect(markup).toContain('for="admin-directory-role"');
    expect(markup).toContain('for="admin-directory-department"');
    expect(markup).toContain('for="admin-directory-status"');
    expect(markup).toContain('for="admin-directory-search"');
    expect(markup).toContain("adminDirectoryTitle");
    expect(markup).not.toContain("activate");
    expect(markup).not.toContain("delete");
    expect(markup).not.toContain("password");
    expect(markup).not.toContain("uid");
  });

  it("does not render for non-Admins", () => {
    state.profile = { role: "manager", active: true, departmentId: null };
    expect(renderToStaticMarkup(<AdminUserDirectory />)).toBe("");
    state.profile = { role: "admin", active: true, departmentId: null };
  });
});
