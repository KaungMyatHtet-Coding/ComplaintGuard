import rawEvaluation from "@/generated/model_evaluation_v1.json";

export const departmentIds = [
  "transfer_payment",
  "account_support",
  "card_atm",
  "fraud_security",
  "loan_credit",
  "general_support",
] as const;

export type DepartmentId = (typeof departmentIds)[number];

type MetricSet = Readonly<{ precision: number; recall: number; f1: number }>;
type DepartmentMetric = MetricSet & Readonly<{ support: number }>;
type LabelCounts = Readonly<Record<DepartmentId, number>>;

export type ConfidenceBin = Readonly<{
  lowerInclusive: number;
  upper: number;
  upperInclusive: boolean;
  count: number;
  correct: number;
  incorrect: number;
  empiricalAccuracy: number | null;
}>;

export type ModelEvaluation = Readonly<{
  schemaVersion: 1;
  metadata: Readonly<{
    createdAtUtc: string;
    modelVersion: string;
    datasetVersion: string;
    mappingVersion: string;
    randomSeed: number;
    evaluationPartition: string;
    modelRetrained: false;
    lockedMetricsReconciled: true;
  }>;
  datasetPipeline: Readonly<{
    rawRecords: number;
    recordsWithNarratives: number;
    usableNarrativeRecords: number;
    mappedRecords: number;
    selectedModelingRecords: number;
  }>;
  partitions: Readonly<{
    naturalTraining: number;
    trainingUsedForFit: number;
    validation: number;
    test: number;
    splitMethod: string;
    exactDuplicatesCrossPartitions: false;
  }>;
  classDistribution: Readonly<{
    mappedCorpus: LabelCounts;
    heldOutTestTrue: LabelCounts;
    heldOutTestPredicted: LabelCounts;
  }>;
  metrics: Readonly<{
    accuracy: number;
    balancedAccuracy: number;
    macro: MetricSet;
    weighted: MetricSet;
    perDepartment: Readonly<Record<DepartmentId, DepartmentMetric>>;
    confusionMatrix: Readonly<{
      labelOrder: readonly DepartmentId[];
      values: readonly (readonly number[])[];
    }>;
  }>;
  confidence: Readonly<{
    definition: string;
    threshold: number;
    thresholdOrigin: string;
    below: Readonly<{ count: number; correct: number; incorrect: number }>;
    atOrAbove: Readonly<{ count: number; correct: number; incorrect: number }>;
    bins: readonly ConfidenceBin[];
  }>;
  similarity: Readonly<{
    status: string;
    method: string;
    referencePartition: string;
    referenceRecords: number;
    featureCount: number;
    coversAllRawRecords: false;
    containsNarratives: false;
    separateFromPredictionConfidence: true;
  }>;
  limitations: readonly string[];
}>;

export class ModelEvaluationSchemaError extends Error {}

function record(value: unknown, path: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new ModelEvaluationSchemaError(`${path} must be an object`);
  }
  return value as Record<string, unknown>;
}

function required(parent: Record<string, unknown>, key: string, path: string): unknown {
  if (!(key in parent)) throw new ModelEvaluationSchemaError(`${path}.${key} is required`);
  return parent[key];
}

function text(value: unknown, path: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new ModelEvaluationSchemaError(`${path} must be a non-empty string`);
  }
  return value;
}

function finite(value: unknown, path: string, min = 0, max = Number.MAX_VALUE): number {
  if (typeof value !== "number" || !Number.isFinite(value) || value < min || value > max) {
    throw new ModelEvaluationSchemaError(`${path} must be finite and between ${min} and ${max}`);
  }
  return value;
}

function integer(value: unknown, path: string, min = 0): number {
  const result = finite(value, path, min);
  if (!Number.isInteger(result)) throw new ModelEvaluationSchemaError(`${path} must be an integer`);
  return result;
}

function exactBoolean(value: unknown, expected: boolean, path: string): boolean {
  if (value !== expected) throw new ModelEvaluationSchemaError(`${path} must be ${expected}`);
  return expected;
}

function metricSet(value: unknown, path: string): MetricSet {
  const item = record(value, path);
  return Object.freeze({
    precision: finite(required(item, "precision", path), `${path}.precision`, 0, 1),
    recall: finite(required(item, "recall", path), `${path}.recall`, 0, 1),
    f1: finite(required(item, "f1", path), `${path}.f1`, 0, 1),
  });
}

function labelCounts(value: unknown, path: string): LabelCounts {
  const item = record(value, path);
  const keys = Object.keys(item);
  if (keys.length !== departmentIds.length || departmentIds.some((id) => !keys.includes(id))) {
    throw new ModelEvaluationSchemaError(`${path} must contain exactly the six departments`);
  }
  return Object.freeze(
    Object.fromEntries(departmentIds.map((id) => [id, integer(item[id], `${path}.${id}`)])),
  ) as LabelCounts;
}

function sumCounts(value: LabelCounts): number {
  return departmentIds.reduce((total, id) => total + value[id], 0);
}

export function parseModelEvaluation(value: unknown): ModelEvaluation {
  const root = record(value, "evaluation");
  if (required(root, "schema_version", "evaluation") !== 1) {
    throw new ModelEvaluationSchemaError("evaluation.schema_version must be 1");
  }
  if (required(root, "status", "evaluation") !== "completed") {
    throw new ModelEvaluationSchemaError("evaluation.status must be completed");
  }

  const metadata = record(required(root, "metadata", "evaluation"), "metadata");
  const pipeline = record(required(root, "dataset_pipeline", "evaluation"), "dataset_pipeline");
  const partitions = record(required(root, "partitions", "evaluation"), "partitions");
  const natural = record(required(partitions, "natural_training", "partitions"), "partitions.natural_training");
  const fitted = record(required(partitions, "training_used_for_fit", "partitions"), "partitions.training_used_for_fit");
  const validation = record(required(partitions, "validation", "partitions"), "partitions.validation");
  const testPartition = record(required(partitions, "test", "partitions"), "partitions.test");

  const rawRecords = integer(required(pipeline, "raw_records", "dataset_pipeline"), "dataset_pipeline.raw_records", 1);
  const recordsWithNarratives = integer(required(pipeline, "raw_records_with_non_null_narrative", "dataset_pipeline"), "dataset_pipeline.raw_records_with_non_null_narrative", 1);
  const usableNarrativeRecords = integer(required(pipeline, "usable_narrative_records", "dataset_pipeline"), "dataset_pipeline.usable_narrative_records", 1);
  const mappedRecords = integer(required(pipeline, "successfully_mapped_records", "dataset_pipeline"), "dataset_pipeline.successfully_mapped_records", 1);
  const selectedModelingRecords = integer(required(pipeline, "selected_modeling_records", "dataset_pipeline"), "dataset_pipeline.selected_modeling_records", 1);
  const naturalTraining = integer(required(natural, "rows", "partitions.natural_training"), "partitions.natural_training.rows", 1);
  const trainingUsedForFit = integer(required(fitted, "rows", "partitions.training_used_for_fit"), "partitions.training_used_for_fit.rows", 1);
  const validationRows = integer(required(validation, "rows", "partitions.validation"), "partitions.validation.rows", 1);
  const testRows = integer(required(testPartition, "rows", "partitions.test"), "partitions.test.rows", 1);

  if (!(rawRecords >= recordsWithNarratives && recordsWithNarratives >= usableNarrativeRecords && usableNarrativeRecords === mappedRecords && mappedRecords >= selectedModelingRecords)) {
    throw new ModelEvaluationSchemaError("dataset pipeline counts do not reconcile");
  }
  if (naturalTraining + validationRows + testRows !== selectedModelingRecords || trainingUsedForFit > naturalTraining) {
    throw new ModelEvaluationSchemaError("model partitions do not reconcile");
  }

  const distributions = record(required(root, "class_distribution", "evaluation"), "class_distribution");
  const mappedCorpus = labelCounts(required(distributions, "mapped_corpus", "class_distribution"), "class_distribution.mapped_corpus");
  const heldOutTestTrue = labelCounts(required(distributions, "held_out_test_true", "class_distribution"), "class_distribution.held_out_test_true");
  const heldOutTestPredicted = labelCounts(required(distributions, "held_out_test_predicted", "class_distribution"), "class_distribution.held_out_test_predicted");
  if (sumCounts(mappedCorpus) !== mappedRecords || sumCounts(heldOutTestTrue) !== testRows || sumCounts(heldOutTestPredicted) !== testRows) {
    throw new ModelEvaluationSchemaError("class distributions do not reconcile");
  }

  const metrics = record(required(root, "metrics", "evaluation"), "metrics");
  const perClass = record(required(metrics, "per_department", "metrics"), "metrics.per_department");
  if (Object.keys(perClass).length !== 6 || departmentIds.some((id) => !(id in perClass))) {
    throw new ModelEvaluationSchemaError("metrics.per_department must contain exactly the six departments");
  }
  const perDepartment = Object.freeze(
    Object.fromEntries(departmentIds.map((id) => {
      const item = record(perClass[id], `metrics.per_department.${id}`);
      return [id, Object.freeze({ ...metricSet(item, `metrics.per_department.${id}`), support: integer(required(item, "support", `metrics.per_department.${id}`), `metrics.per_department.${id}.support`, 1) })];
    })),
  ) as Readonly<Record<DepartmentId, DepartmentMetric>>;
  if (departmentIds.reduce((total, id) => total + perDepartment[id].support, 0) !== testRows || departmentIds.some((id) => perDepartment[id].support !== heldOutTestTrue[id])) {
    throw new ModelEvaluationSchemaError("department supports do not reconcile with the held-out test set");
  }

  const matrix = record(required(metrics, "confusion_matrix", "metrics"), "metrics.confusion_matrix");
  const order = required(matrix, "label_order", "metrics.confusion_matrix");
  if (!Array.isArray(order) || order.length !== 6 || departmentIds.some((id, index) => order[index] !== id)) {
    throw new ModelEvaluationSchemaError("confusion matrix label ordering is invalid");
  }
  const rawValues = required(matrix, "values", "metrics.confusion_matrix");
  if (!Array.isArray(rawValues) || rawValues.length !== 6) throw new ModelEvaluationSchemaError("confusion matrix must be 6x6");
  const matrixValues = rawValues.map((row, rowIndex) => {
    if (!Array.isArray(row) || row.length !== 6) throw new ModelEvaluationSchemaError("confusion matrix must be 6x6");
    const checked = row.map((cell, columnIndex) => integer(cell, `confusion_matrix.values.${rowIndex}.${columnIndex}`));
    if (checked.reduce((total, cell) => total + cell, 0) !== perDepartment[departmentIds[rowIndex]].support) {
      throw new ModelEvaluationSchemaError("confusion matrix rows must reconcile with support");
    }
    return Object.freeze(checked);
  });

  const confidence = record(required(root, "confidence_analysis", "evaluation"), "confidence_analysis");
  const below = record(required(confidence, "below_operational_threshold", "confidence_analysis"), "confidence_analysis.below_operational_threshold");
  const above = record(required(confidence, "at_or_above_operational_threshold", "confidence_analysis"), "confidence_analysis.at_or_above_operational_threshold");
  const checkGroup = (item: Record<string, unknown>, path: string) => {
    const count = integer(required(item, "count", path), `${path}.count`);
    const correct = integer(required(item, "correct", path), `${path}.correct`);
    const incorrect = integer(required(item, "incorrect", path), `${path}.incorrect`);
    if (correct + incorrect !== count) throw new ModelEvaluationSchemaError(`${path} does not reconcile`);
    return Object.freeze({ count, correct, incorrect });
  };
  const belowGroup = checkGroup(below, "confidence_analysis.below_operational_threshold");
  const aboveGroup = checkGroup(above, "confidence_analysis.at_or_above_operational_threshold");
  if (belowGroup.count + aboveGroup.count !== testRows) throw new ModelEvaluationSchemaError("confidence threshold groups do not reconcile");
  const rawBins = required(confidence, "bins", "confidence_analysis");
  if (!Array.isArray(rawBins) || rawBins.length === 0) throw new ModelEvaluationSchemaError("confidence bins are required");
  const bins = rawBins.map((value, index) => {
    const item = record(value, `confidence_analysis.bins.${index}`);
    const count = integer(required(item, "count", `confidence_analysis.bins.${index}`), `confidence_analysis.bins.${index}.count`);
    const correct = integer(required(item, "correct", `confidence_analysis.bins.${index}`), `confidence_analysis.bins.${index}.correct`);
    const incorrect = integer(required(item, "incorrect", `confidence_analysis.bins.${index}`), `confidence_analysis.bins.${index}.incorrect`);
    if (correct + incorrect !== count) throw new ModelEvaluationSchemaError("confidence bin counts do not reconcile");
    const empirical = required(item, "empirical_accuracy", `confidence_analysis.bins.${index}`);
    return Object.freeze({
      lowerInclusive: finite(required(item, "lower_inclusive", `confidence_analysis.bins.${index}`), `confidence_analysis.bins.${index}.lower_inclusive`, 0, 1),
      upper: finite(required(item, "upper", `confidence_analysis.bins.${index}`), `confidence_analysis.bins.${index}.upper`, 0, 1),
      upperInclusive: typeof item.upper_inclusive === "boolean" ? item.upper_inclusive : (() => { throw new ModelEvaluationSchemaError("confidence bin inclusion flag is required"); })(),
      count,
      correct,
      incorrect,
      empiricalAccuracy: empirical === null ? null : finite(empirical, `confidence_analysis.bins.${index}.empirical_accuracy`, 0, 1),
    });
  });
  if (bins.reduce((total, bin) => total + bin.count, 0) !== testRows) throw new ModelEvaluationSchemaError("confidence bins do not reconcile with test rows");

  const privacy = record(required(root, "privacy", "evaluation"), "privacy");
  exactBoolean(required(privacy, "contains_narratives", "privacy"), false, "privacy.contains_narratives");
  exactBoolean(required(privacy, "contains_complaint_ids", "privacy"), false, "privacy.contains_complaint_ids");
  const similarity = record(required(root, "historical_similarity", "evaluation"), "historical_similarity");
  const similarityRecords = integer(required(similarity, "reference_records", "historical_similarity"), "historical_similarity.reference_records", 1);
  if (similarityRecords !== testRows) throw new ModelEvaluationSchemaError("similarity coverage must reconcile with held-out test rows");
  exactBoolean(required(similarity, "covers_all_raw_records", "historical_similarity"), false, "historical_similarity.covers_all_raw_records");
  exactBoolean(required(similarity, "contains_narratives", "historical_similarity"), false, "historical_similarity.contains_narratives");
  exactBoolean(required(similarity, "separate_from_prediction_confidence", "historical_similarity"), true, "historical_similarity.separate_from_prediction_confidence");

  const rawLimitations = required(root, "limitations", "evaluation");
  if (!Array.isArray(rawLimitations) || rawLimitations.length === 0 || rawLimitations.some((item) => typeof item !== "string" || !item.trim())) {
    throw new ModelEvaluationSchemaError("evaluation limitations are required");
  }

  return Object.freeze({
    schemaVersion: 1,
    metadata: Object.freeze({
      createdAtUtc: text(required(metadata, "created_at_utc", "metadata"), "metadata.created_at_utc"),
      modelVersion: text(required(metadata, "model_version", "metadata"), "metadata.model_version"),
      datasetVersion: text(required(metadata, "dataset_version", "metadata"), "metadata.dataset_version"),
      mappingVersion: text(required(metadata, "mapping_version", "metadata"), "metadata.mapping_version"),
      randomSeed: integer(required(metadata, "random_seed", "metadata"), "metadata.random_seed", 1),
      evaluationPartition: text(required(metadata, "evaluation_partition", "metadata"), "metadata.evaluation_partition"),
      modelRetrained: exactBoolean(required(metadata, "model_retrained", "metadata"), false, "metadata.model_retrained") as false,
      lockedMetricsReconciled: exactBoolean(required(metadata, "locked_metrics_reconciled", "metadata"), true, "metadata.locked_metrics_reconciled") as true,
    }),
    datasetPipeline: Object.freeze({ rawRecords, recordsWithNarratives, usableNarrativeRecords, mappedRecords, selectedModelingRecords }),
    partitions: Object.freeze({ naturalTraining, trainingUsedForFit, validation: validationRows, test: testRows, splitMethod: text(required(partitions, "split_method", "partitions"), "partitions.split_method"), exactDuplicatesCrossPartitions: exactBoolean(required(partitions, "exact_normalized_duplicates_cross_partitions", "partitions"), false, "partitions.exact_normalized_duplicates_cross_partitions") as false }),
    classDistribution: Object.freeze({ mappedCorpus, heldOutTestTrue, heldOutTestPredicted }),
    metrics: Object.freeze({
      accuracy: finite(required(metrics, "accuracy", "metrics"), "metrics.accuracy", 0, 1),
      balancedAccuracy: finite(required(metrics, "balanced_accuracy", "metrics"), "metrics.balanced_accuracy", 0, 1),
      macro: metricSet(required(metrics, "macro", "metrics"), "metrics.macro"),
      weighted: metricSet(required(metrics, "weighted", "metrics"), "metrics.weighted"),
      perDepartment,
      confusionMatrix: Object.freeze({ labelOrder: Object.freeze([...departmentIds]), values: Object.freeze(matrixValues) }),
    }),
    confidence: Object.freeze({ definition: text(required(confidence, "definition", "confidence_analysis"), "confidence_analysis.definition"), threshold: finite(required(confidence, "operational_analysis_threshold", "confidence_analysis"), "confidence_analysis.operational_analysis_threshold", 0, 1), thresholdOrigin: text(required(confidence, "threshold_origin", "confidence_analysis"), "confidence_analysis.threshold_origin"), below: belowGroup, atOrAbove: aboveGroup, bins: Object.freeze(bins) }),
    similarity: Object.freeze({ status: text(required(similarity, "status", "historical_similarity"), "historical_similarity.status"), method: text(required(similarity, "method", "historical_similarity"), "historical_similarity.method"), referencePartition: text(required(similarity, "reference_partition", "historical_similarity"), "historical_similarity.reference_partition"), referenceRecords: similarityRecords, featureCount: integer(required(similarity, "feature_count", "historical_similarity"), "historical_similarity.feature_count", 1), coversAllRawRecords: false, containsNarratives: false, separateFromPredictionConfidence: true }),
    limitations: Object.freeze([...rawLimitations] as string[]),
  });
}

export const modelEvaluation = parseModelEvaluation(rawEvaluation);

export function formatMetric(value: number, locale: "en" | "my" = "en"): string {
  return new Intl.NumberFormat(locale === "my" ? "my-MM" : "en-US", {
    style: "percent",
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatCount(value: number, locale: "en" | "my" = "en"): string {
  return new Intl.NumberFormat(locale === "my" ? "my-MM" : "en-US").format(value);
}

export function confidenceBandLabel(bin: ConfidenceBin): string {
  const lower = Math.round(bin.lowerInclusive * 100);
  const upper = Math.round(bin.upper * 100);
  return `${lower}–${upper}${bin.upperInclusive ? "%" : "%"}`;
}
