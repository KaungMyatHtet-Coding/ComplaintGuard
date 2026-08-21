import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("Registration authentication form polish", () => {
  const source = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");

  it("keeps both accessible password controls and the focused error summary", () => {
    expect(source).toContain('id="register-password"');
    expect(source).toContain('id="register-confirm-password"');
    expect(source).toContain("auth-password-toggle");
    expect(source).toContain("errorSummaryRef");
    expect(source).toContain('role="alert"');
  });

  it("uses shared auth inputs without changing registration autocomplete", () => {
    expect(source).toContain('autoComplete="email"');
    expect(source).toContain('autoComplete="name"');
    expect(source).toContain('autoComplete="new-password"');
    expect(source).toContain('className="auth-input"');
    expect(source).toContain('className="auth-submit"');
  });
});
