import { describe, expect, it } from "vitest";

import { normalizeLocale, translate } from "./i18n";

describe("localization foundation", () => {
  it("supports English and Myanmar UI copy", () => {
    expect(translate("en", "loginTitle")).toBe("Sign in");
    expect(translate("en", "complaintTitle")).toBe("Submit a complaint");
    expect(translate("my", "complaintTitle")).toContain("တိုင်ကြားချက်");
    expect(translate("my", "loginTitle")).toContain("အကောင့်");
  });

  it("falls back to English for unsupported locale values", () => {
    expect(normalizeLocale("fr")).toBe("en");
    expect(normalizeLocale(null)).toBe("en");
  });
});
