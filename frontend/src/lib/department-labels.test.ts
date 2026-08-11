import { describe, expect, it } from "vitest";

import { getDepartmentLabel, isDepartmentId } from "./department-labels";

describe("department labels", () => {
  it("returns the existing localized label for every stable department ID", () => {
    expect(getDepartmentLabel("card_atm", "en")).toBe("Card & ATM");
    expect(getDepartmentLabel("card_atm", "my")).toBe("ကတ်နှင့် ATM");
    expect(isDepartmentId("transfer_payment")).toBe(true);
  });

  it("handles unknown and missing values without exposing an internal fallback", () => {
    expect(getDepartmentLabel("unknown_department", "en")).toBeNull();
    expect(getDepartmentLabel(null, "en")).toBeNull();
    expect(getDepartmentLabel(undefined, "my")).toBeNull();
    expect(isDepartmentId("unknown_department")).toBe(false);
  });
});
