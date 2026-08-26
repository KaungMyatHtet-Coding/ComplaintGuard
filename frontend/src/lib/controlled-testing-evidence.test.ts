import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { controlledTestingEvidence } from "./controlled-testing-evidence";

const root = resolve(process.cwd(), "..");

function sha256(relativePath: string): string {
  return createHash("sha256")
    .update(readFileSync(resolve(root, relativePath)))
    .digest("hex")
    .toUpperCase();
}

function source(relativePath: string): { cases: Record<string, unknown>[]; summary?: Record<string, number> } {
  return JSON.parse(readFileSync(resolve(root, relativePath), "utf8")) as { cases: Record<string, unknown>[]; summary?: Record<string, number> };
}

function safeCaseProjection(item: Record<string, unknown>, textLengthCategory: string): Record<string, unknown> {
  return {
    caseId: item.caseId,
    textLengthCategory,
    expectedDepartmentId: item.expectedDepartmentId,
    predictedDepartmentId: item.predictedDepartmentId,
    predictionConfidence: item.predictionConfidence,
    routingSource: item.routingSource,
    manualReview: item.manualReview,
    manualReviewReason: item.manualReviewReason,
    finalRouteDepartmentId: item.finalRouteDepartmentId,
    classifierPredictionMatches: item.classifierPredictionMatches,
    correctAutomaticRoute: item.correctAutomaticRoute,
  };
}

describe("controlled frontend evidence artifact", () => {
  it("keeps every source hash tied to the committed evidence", () => {
    for (const source of Object.values(controlledTestingEvidence.sourceArtifacts)) {
      expect(sha256(source.path)).toBe(source.sha256);
    }
  });

  it("preserves the separate V1 and V2 aggregate contracts", () => {
    expect(controlledTestingEvidence.v1.summary).toMatchObject({
      classifierPredictionMatchCount: 2,
      automaticRouteCount: 1,
      correctAutomaticRouteCount: 0,
      manualReviewCount: 5,
      managerOverrideCount: 0,
    });
    expect(controlledTestingEvidence.v2.summary).toMatchObject({
      classifierPredictionMatchCount: 2,
      automaticRouteCount: 2,
      automaticRouteCoverage: 33.3333,
      correctAutomaticRouteCount: 2,
      automaticRoutingSuccessRate: 100,
      manualReviewCount: 4,
      managerOverrideCount: 0,
    });
    expect(controlledTestingEvidence.v1.cases).toHaveLength(6);
    expect(controlledTestingEvidence.v2.cases).toHaveLength(6);
  });

  it("matches the source artifacts through an aggregate-safe projection", () => {
    const v1 = source("evaluation/controlled/six_department_synthetic_v1.json");
    const v2 = source("evaluation/controlled/six_department_long_english_supported_use_v2b.json");
    expect(controlledTestingEvidence.v1.cases).toEqual(v1.cases.map((item) => safeCaseProjection(item, String(item.textLengthCategory))));
    expect(controlledTestingEvidence.v2.cases).toEqual(v2.cases.map((item) => safeCaseProjection(item, "long")));
  });

  it("contains no complaint text or private identifiers", () => {
    const serialized = JSON.stringify(controlledTestingEvidence);
    expect(serialized).not.toContain("syntheticInput");
    expect(serialized).not.toContain("complaintText");
    expect(serialized).not.toMatch(/\b(?:phone|email|address|account number|card number)\b/iu);
  });
});
