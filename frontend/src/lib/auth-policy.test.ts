import { describe, expect, it } from "vitest";

import {
  isAppRole,
  parseUserProfile,
  roleNavigation,
  roles,
  validateCredentials,
} from "./auth-policy";

describe("authentication policy", () => {
  it("keeps the four approved roles stable", () => {
    expect(roles).toEqual(["customer", "staff", "manager", "admin"]);
    for (const role of roles) expect(roleNavigation[role]).toEqual(["dashboard"]);
  });

  it("validates credentials without retaining the password", () => {
    expect(validateCredentials(" user@example.test ", "synthetic-secret")).toEqual({
      valid: true,
      email: "user@example.test",
    });
    expect(validateCredentials("", "x")).toEqual({
      valid: false,
      code: "invalid_email",
    });
    expect(validateCredentials("user@example.test", "")).toEqual({
      valid: false,
      code: "missing_password",
    });
  });

  it("rejects unknown and inactive roles", () => {
    expect(isAppRole("owner")).toBe(false);
    expect(() =>
      parseUserProfile("synthetic-uid", "staff@example.test", {
        role: "staff",
        active: false,
        departmentId: "card_atm",
      }),
    ).toThrow("profile_unauthorized");
  });

  it("requires staff department membership", () => {
    expect(() =>
      parseUserProfile("synthetic-uid", "staff@example.test", {
        role: "staff",
        active: true,
      }),
    ).toThrow("profile_department_missing");
  });

  it("accepts a valid synthetic profile and normalizes locale", () => {
    expect(
      parseUserProfile("synthetic-uid", "customer@example.test", {
        role: "customer",
        active: true,
        locale: "my",
        displayName: "Demo Customer",
      }),
    ).toMatchObject({
      uid: "synthetic-uid",
      role: "customer",
      locale: "my",
      departmentId: null,
    });
  });
});
