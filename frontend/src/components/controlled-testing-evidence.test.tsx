import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AppProvider } from "./app-provider";
import { ControlledTestingEvidence } from "./controlled-testing-evidence";
import { translate } from "@/lib/i18n";
import { modelEvaluation } from "@/lib/model-evaluation";

describe("ControlledTestingEvidence", () => {
  it("renders separated source sections, safe metrics, and accessible tables", () => {
    const markup = renderToStaticMarkup(<AppProvider><ControlledTestingEvidence /></AppProvider>);
    expect(markup).toContain("Controlled V1");
    expect(markup).toContain("Controlled V2");
    expect(markup).toContain("2/2 (100%)");
    expect(markup).toContain("2/6 (33.3333%)");
    expect(markup).toContain(`${(modelEvaluation.metrics.accuracy * 100).toFixed(4)}%`);
    expect(markup).toContain(modelEvaluation.metrics.macro.f1.toFixed(6));
    expect(markup).toContain("aria-label=\"V1 — Short-English Challenge\"");
    expect(markup).toContain("<caption>Aggregate-safe case results</caption>");
    expect(markup).toContain("<details");
    expect(markup).not.toContain("synthetic banking account");
    expect(markup).not.toContain("overall model accuracy: 100");
  });

  it("renders Myanmar labels without exposing source complaint text", () => {
    expect(translate("my", "controlledSourceV1")).toContain("ထိန်းချုပ်စမ်းသပ်မှု");
    expect(translate("my", "controlledCaseId")).toContain("ဖြစ်ရပ်");
  });
});
