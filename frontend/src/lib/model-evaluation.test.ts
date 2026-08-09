import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import rawEvaluation from "../../../evaluation/day18/model_evaluation_v1.json";
import {
  ModelEvaluationSchemaError,
  departmentIds,
  formatCount,
  formatMetric,
  modelEvaluation,
  parseModelEvaluation,
} from "./model-evaluation";

function copyArtifact(): unknown {
  return structuredClone(rawEvaluation);
}

function object(value: unknown): Record<string, unknown> {
  expect(value).toBeTypeOf("object");
  return value as Record<string, unknown>;
}

describe("Day 18 model evaluation parser", () => {
  it("accepts the committed primary artifact without changing its values", () => {
    expect(modelEvaluation.metrics.accuracy).toBe(rawEvaluation.metrics.accuracy);
    expect(modelEvaluation.metrics.macro.f1).toBe(rawEvaluation.metrics.macro.f1);
    expect(modelEvaluation.datasetPipeline.rawRecords).toBe(
      rawEvaluation.dataset_pipeline.raw_records,
    );
    expect(modelEvaluation.partitions.test).toBe(rawEvaluation.partitions.test.rows);
    expect(modelEvaluation.confidence.threshold).toBe(
      rawEvaluation.confidence_analysis.operational_analysis_threshold,
    );
    expect(modelEvaluation.similarity.referenceRecords).toBe(29_942);
    expect(Object.isFrozen(modelEvaluation)).toBe(true);
  });

  it("rejects missing, wrong, and incomplete schema metadata", () => {
    const missing = object(copyArtifact());
    delete missing.schema_version;
    expect(() => parseModelEvaluation(missing)).toThrow(ModelEvaluationSchemaError);
    const wrong = object(copyArtifact());
    wrong.schema_version = 2;
    expect(() => parseModelEvaluation(wrong)).toThrow("schema_version must be 1");
    const incomplete = object(copyArtifact());
    delete incomplete.metrics;
    expect(() => parseModelEvaluation(incomplete)).toThrow("metrics is required");
  });

  it.each([Number.NaN, Number.POSITIVE_INFINITY, -0.1, 1.1])(
    "rejects invalid metric %s",
    (value) => {
      const artifact = object(copyArtifact());
      object(artifact.metrics).accuracy = value;
      expect(() => parseModelEvaluation(artifact)).toThrow(ModelEvaluationSchemaError);
    },
  );

  it("requires exactly the six stable departments in the fixed order", () => {
    const missing = object(copyArtifact());
    delete object(object(missing.metrics).per_department).general_support;
    expect(() => parseModelEvaluation(missing)).toThrow("exactly the six departments");

    const wrongOrder = object(copyArtifact());
    object(object(wrongOrder.metrics).confusion_matrix).label_order = [...departmentIds].reverse();
    expect(() => parseModelEvaluation(wrongOrder)).toThrow("label ordering is invalid");
  });

  it("requires a 6 by 6 matrix and reconciles every row with support", () => {
    const wrongShape = object(copyArtifact());
    const shapeValues = object(object(wrongShape.metrics).confusion_matrix).values as unknown[][];
    shapeValues[0].pop();
    expect(() => parseModelEvaluation(wrongShape)).toThrow("6x6");

    const wrongSupport = object(copyArtifact());
    const supportValues = object(object(wrongSupport.metrics).confusion_matrix).values as number[][];
    supportValues[0][0] += 1;
    expect(() => parseModelEvaluation(wrongSupport)).toThrow("reconcile with support");
  });

  it("reconciles confidence bins, partitions, dataset counts, and privacy flags", () => {
    const wrongBins = object(copyArtifact());
    const bins = object(wrongBins.confidence_analysis).bins as Record<string, unknown>[];
    bins[0].count = Number(bins[0].count) + 1;
    expect(() => parseModelEvaluation(wrongBins)).toThrow("confidence bin counts");

    const wrongPipeline = object(copyArtifact());
    const pipeline = object(wrongPipeline.dataset_pipeline);
    pipeline.successfully_mapped_records = Number(pipeline.successfully_mapped_records) - 1;
    expect(() => parseModelEvaluation(wrongPipeline)).toThrow("pipeline counts");

    const unsafe = object(copyArtifact());
    object(unsafe.privacy).contains_narratives = true;
    expect(() => parseModelEvaluation(unsafe)).toThrow("must be false");
  });

  it("formats only validated values", () => {
    expect(formatMetric(modelEvaluation.metrics.accuracy)).toBe("82.8%");
    expect(formatCount(modelEvaluation.partitions.test)).toBe("29,942");
  });
});

describe("supporting Day 18 artifacts", () => {
  const evaluationDir = resolve(process.cwd(), "../evaluation/day18");

  it("keeps the generated build input byte-identical to the primary source", () => {
    expect(
      readFileSync(resolve(process.cwd(), "src/generated/model_evaluation_v1.json"), "utf8"),
    ).toBe(readFileSync(resolve(evaluationDir, "model_evaluation_v1.json"), "utf8"));
  });

  it("reconciles supporting JSON with the primary source", () => {
    const counts = JSON.parse(
      readFileSync(resolve(evaluationDir, "dataset_pipeline_counts.json"), "utf8"),
    );
    const confidence = JSON.parse(
      readFileSync(resolve(evaluationDir, "confidence_analysis.json"), "utf8"),
    );
    const similarity = JSON.parse(
      readFileSync(resolve(evaluationDir, "historical_similarity_metadata.json"), "utf8"),
    );
    expect(counts).toEqual(rawEvaluation.dataset_pipeline);
    expect(confidence).toEqual(rawEvaluation.confidence_analysis);
    expect(similarity).toEqual(rawEvaluation.historical_similarity);
  });

  it("reconciles department and confusion CSV files with the primary source", () => {
    const departmentRows = readFileSync(
      resolve(evaluationDir, "per_department_metrics.csv"),
      "utf8",
    ).trim().split(/\r?\n/u);
    expect(departmentRows).toHaveLength(7);
    for (const row of departmentRows.slice(1)) {
      const [id, precision, recall, f1, support] = row.split(",");
      expect(rawEvaluation.metrics.per_department[id as keyof typeof rawEvaluation.metrics.per_department]).toEqual({
        precision: Number(precision),
        recall: Number(recall),
        f1: Number(f1),
        support: Number(support),
      });
    }

    const matrixRows = readFileSync(resolve(evaluationDir, "confusion_matrix.csv"), "utf8")
      .trim().split(/\r?\n/u).slice(1).map((row) => row.split(",").slice(1).map(Number));
    expect(matrixRows).toEqual(rawEvaluation.metrics.confusion_matrix.values);
  });
});
