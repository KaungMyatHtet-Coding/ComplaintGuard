import { describe, expect, it } from "vitest";

import { applyThemePreference, readThemePreference } from "./theme-control";

describe("theme preference", () => {
  it("defaults invalid storage values to system", () => {
    expect(readThemePreference({ getItem: () => "neon" })).toBe("system");
    expect(readThemePreference(null)).toBe("system");
    expect(readThemePreference({ getItem: () => "dark" })).toBe("dark");
  });

  it("applies only the validated theme preference to the document root", () => {
    const root = { dataset: {} as DOMStringMap } as HTMLElement;
    applyThemePreference("light", root);
    expect(root.dataset.theme).toBe("light");
    expect(JSON.stringify(root.dataset)).not.toContain("uid");
    expect(JSON.stringify(root.dataset)).not.toContain("token");
  });

  it("keeps System tied to the operating-system media preference", async () => {
    const source = await import("node:fs").then(({ readFileSync }) =>
      readFileSync(new URL("./theme-control.tsx", import.meta.url), "utf8"),
    );
    const css = await import("node:fs").then(({ readFileSync }) =>
      readFileSync(new URL("../app/globals.css", import.meta.url), "utf8"),
    );
    expect(source).toContain('matchMedia("(prefers-color-scheme: dark)")');
    expect(source).toContain('preferenceRef.current === "system"');
    expect(css).toContain(':root:not([data-theme="light"])');
    expect(css).toContain('html:not([data-theme="light"])');
  });
});
