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
});
