import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppProvider } from "./app-provider";
import { ModelAnalyticsDashboard } from "./model-analytics-dashboard";
import { formatCount, formatMetric, modelEvaluation } from "@/lib/model-evaluation";

const markup = renderToStaticMarkup(
  <AppProvider>
    <ModelAnalyticsDashboard />
  </AppProvider>,
);

describe("ModelAnalyticsDashboard", () => {
  it("renders artifact-derived metrics and dataset counts", () => {
    expect(markup).toContain(formatMetric(modelEvaluation.metrics.accuracy));
    expect(markup).toContain(formatMetric(modelEvaluation.metrics.balancedAccuracy));
    expect(markup).toContain(formatMetric(modelEvaluation.metrics.macro.f1));
    expect(markup).toContain(formatCount(modelEvaluation.datasetPipeline.rawRecords));
    expect(markup).toContain(formatCount(modelEvaluation.datasetPipeline.mappedRecords));
    expect(markup).toContain(formatCount(modelEvaluation.partitions.test));
  });

  it("renders accessible responsive performance and confusion tables", () => {
    expect(markup).toContain("Held-out precision, recall, F1 and support");
    expect(markup).toContain("Held-out confusion matrix");
    expect(markup).toContain("responsive-table");
    expect(markup).toContain("True ↓ / Predicted →");
  });

  it("shows local-only similarity metadata without invented results", () => {
    expect(markup).toContain(
      `${formatCount(modelEvaluation.similarity.referenceRecords)} held-out records`,
    );
    expect(markup).toContain(formatCount(modelEvaluation.similarity.featureCount));
    expect(markup).toContain("Not deployed");
    expect(markup).not.toMatch(/nearest complaint|Consumer complaint narrative|Complaint ID|similarity score: [0-9]/u);
  });
});
