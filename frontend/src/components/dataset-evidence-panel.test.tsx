import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppProvider } from "./app-provider";
import { DatasetEvidencePanel } from "./dataset-evidence-panel";
import { formatCount, formatMetric, modelEvaluation } from "@/lib/model-evaluation";

function render(confidence: number | null) {
  return renderToStaticMarkup(
    <AppProvider>
      <DatasetEvidencePanel
        predictedDepartmentId="card_atm"
        predictionConfidence={confidence}
        routingSource={confidence === null ? "manual_review" : "model"}
        assignedDepartmentId={confidence === null ? null : "card_atm"}
      />
    </AppProvider>,
  );
}

describe("DatasetEvidencePanel", () => {
  it("uses the artifact threshold and distinguishes confidence from accuracy", () => {
    const markup = render(0.59);
    expect(markup).toContain(formatMetric(0.59));
    expect(markup).toContain(formatMetric(modelEvaluation.confidence.threshold));
    expect(markup).toContain("Confidence is not model accuracy");
    expect(markup).toContain("below the operational routing threshold");
  });

  it("renders null confidence as unavailable rather than zero", () => {
    const markup = render(null);
    expect(markup).toContain("Pending or unavailable");
    expect(markup).not.toContain("Prediction confidence</dt><dd>0%");
    expect(markup).toContain("Manual review");
  });

  it("shows only honest local similarity coverage without neighbors or narratives", () => {
    const markup = render(0.8);
    expect(markup).toContain(formatCount(modelEvaluation.similarity.referenceRecords));
    expect(markup).toContain("local-only and not deployed");
    expect(markup).toContain("No neighbor or similarity result");
    expect(markup).not.toMatch(/Complaint ID|Consumer complaint narrative|cosine_similarity/u);
  });
});
