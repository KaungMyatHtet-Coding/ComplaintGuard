import { describe, expect, it } from "vitest";

import { isV2DepartmentId, validateFoundationPayload } from "./admin-v2-foundation";

describe("V2 foundation client contracts", () => {
  it("accepts only approved department IDs", () => {
    expect(isV2DepartmentId("general_complaints")).toBe(true);
    expect(isV2DepartmentId("general_support")).toBe(false);
  });

  it("rejects unknown and raw snake_case fields", () => {
    expect(() => validateFoundationPayload({ nameEn: "x", unexpected: true }, ["nameEn"])).toThrow();
    expect(() => validateFoundationPayload({ name_en: "x" }, ["nameEn"])).toThrow();
    expect(validateFoundationPayload({ nameEn: "x" }, ["nameEn"])).toEqual({ nameEn: "x" });
  });
});
