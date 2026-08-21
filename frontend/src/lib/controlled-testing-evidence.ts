import rawEvidence from "@/generated/controlled_testing_evidence_v1.json";

import { departmentIds, type DepartmentId } from "@/lib/department-labels";

export type ControlledCase = Readonly<{
  caseId: string;
  textLengthCategory: "short" | "medium" | "long";
  expectedDepartmentId: DepartmentId;
  predictedDepartmentId: DepartmentId | null;
  predictionConfidence: number | null;
  routingSource: "model" | "manual_review";
  manualReview: boolean;
  manualReviewReason: string | null;
  finalRouteDepartmentId: DepartmentId | null;
  classifierPredictionMatches: boolean;
  correctAutomaticRoute: boolean;
}>;

export type ControlledSummary = Readonly<{
  totalCases: number;
  classifierPredictionMatchCount: number;
  classifierPredictionMatchRate: number;
  automaticRouteCount: number;
  automaticRouteCoverage?: number;
  correctAutomaticRouteCount: number;
  automaticRoutingSuccessRate: number;
  manualReviewCount: number;
  manualReviewRate?: number;
  correctPredictionsSentToManualReview?: number;
  incorrectPredictionsSentToManualReview?: number;
  confidentlyIncorrectAutomaticRouteCount?: number;
  managerOverrideCount: number;
}>;

export type ControlledEvidence = Readonly<{
  contractVersion: string;
  sourceArtifacts: Readonly<Record<"v1" | "v2a" | "v2b", Readonly<{ path: string; sha256: string }>>>;
  v1: Readonly<{ profile: string; caseShape: string; summary: ControlledSummary; cases: readonly ControlledCase[] }>;
  v2: Readonly<{ profile: string; caseShape: string; summary: ControlledSummary; cases: readonly ControlledCase[] }>;
  disclosures: readonly string[];
}>;

function isDepartmentId(value: unknown): value is DepartmentId {
  return typeof value === "string" && departmentIds.includes(value as DepartmentId);
}

function validateCase(value: unknown): ControlledCase {
  if (!value || typeof value !== "object") throw new Error("Controlled evidence case must be an object");
  const item = value as Record<string, unknown>;
  if (!isDepartmentId(item.expectedDepartmentId)) throw new Error("Controlled evidence expected department is invalid");
  if (item.predictedDepartmentId !== null && !isDepartmentId(item.predictedDepartmentId)) throw new Error("Controlled evidence predicted department is invalid");
  if (item.finalRouteDepartmentId !== null && !isDepartmentId(item.finalRouteDepartmentId)) throw new Error("Controlled evidence final route is invalid");
  if (typeof item.caseId !== "string" || typeof item.textLengthCategory !== "string") throw new Error("Controlled evidence case identity is invalid");
  if (typeof item.classifierPredictionMatches !== "boolean" || typeof item.correctAutomaticRoute !== "boolean") throw new Error("Controlled evidence correctness is invalid");
  return item as unknown as ControlledCase;
}

function validateSection(value: unknown): { profile: string; caseShape: string; summary: ControlledSummary; cases: readonly ControlledCase[] } {
  if (!value || typeof value !== "object") throw new Error("Controlled evidence section is invalid");
  const section = value as Record<string, unknown>;
  if (typeof section.profile !== "string" || typeof section.caseShape !== "string" || !section.summary || !Array.isArray(section.cases)) {
    throw new Error("Controlled evidence section is incomplete");
  }
  const cases = section.cases.map(validateCase);
  if (cases.length !== 6) throw new Error("Controlled evidence must contain six cases");
  return { profile: section.profile, caseShape: section.caseShape, summary: section.summary as ControlledSummary, cases };
}

const parsed: ControlledEvidence = {
  contractVersion: rawEvidence.contractVersion,
  sourceArtifacts: rawEvidence.sourceArtifacts,
  v1: validateSection(rawEvidence.v1),
  v2: validateSection(rawEvidence.v2),
  disclosures: rawEvidence.disclosures,
};

export const controlledTestingEvidence = Object.freeze(parsed);
