import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("Login authentication form polish", () => {
  const source = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");
  const css = readFileSync(new URL("../globals.css", import.meta.url), "utf8");

  it("provides an accessible password visibility control and focuses auth errors", () => {
    expect(source).toContain("showPassword");
    expect(source).toContain('type="button"');
    expect(source).toContain('aria-label={showPassword ? t("hidePassword") : t("showPassword")}');
    expect(source).toContain("errorSummaryRef");
    expect(source).toContain('role="alert"');
  });

  it("uses shared auth styling and complete autofill states", () => {
    expect(source).toContain('className="auth-input"');
    expect(source).toContain('className="auth-submit mt-4"');
    expect(css).toContain("--forest: #064e3b");
    expect(css).toContain("--emerald: #10b981");
    expect(css).toContain("--warm-white: #fafaf9");
    expect(css).toContain(".primary-button");
    expect(css).toContain("background: var(--action)");
    expect(css).toContain(".auth-input:focus-visible");
    expect(css).toContain(".auth-input:-webkit-autofill:hover");
    expect(css).toContain(".auth-input:-webkit-autofill:focus");
    expect(css).toContain(".auth-input:-webkit-autofill:active");
  });
});
