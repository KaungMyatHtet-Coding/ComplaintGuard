import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { translate } from "@/lib/i18n";

const locale = vi.hoisted(() => ({ value: "en" as "en" | "my" }));

vi.mock("@/components/app-provider", () => ({
  useApp: () => ({
    locale: locale.value,
    t: (key: Parameters<typeof translate>[1]) => translate(locale.value, key),
  }),
}));

import { ModelEquations } from "./model-equations";

describe("ModelEquations", () => {
  it("renders the configured equations and disclosures in English", () => {
    locale.value = "en";
    const markup = renderToStaticMarkup(<ModelEquations />);
    expect(markup).toContain("tf(t,d) = 1 + log(count(t,d))");
    expect(markup).toContain("idf(t) = log((1+n)/(1+df(t))) + 1");
    expect(markup).toContain("alpha=0.5");
    expect(markup).toContain("min_df=3");
    expect(markup).toContain("max_df=0.98");
    expect(markup).toContain("100,000");
    expect(markup).toContain("0.60");
    expect(markup).toContain("0.0");
    expect(markup).toContain("not calibrated probability");
    expect(markup).toContain("0.692345");
    expect(markup).toContain("0.827934 / 82.7934%");
    expect(markup).toContain("0.707515");
    expect(markup).toContain("0.736204");
    expect(markup).toContain("0.837764");
    expect(markup).toContain("0.70 project target");
    expect(markup).toContain("Product/Issue mapping proxies");
  });

  it("renders readable Myanmar explanations and mapping labels", () => {
    locale.value = "my";
    const markup = renderToStaticMarkup(<ModelEquations />);
    expect(markup).toMatch(/[\u1000-\u109f]/u);
    expect(markup).toContain("မြန်မာရှင်းလင်းချက်");
    expect(markup).toContain("မြန်မာ implementation ဆက်စပ်ချက်");
    expect(markup).toContain("TF-IDF");
  });

  it("uses progressive disclosure and mobile-safe formula containment", () => {
    locale.value = "en";
    const markup = renderToStaticMarkup(<ModelEquations />);
    expect((markup.match(/<details/g) ?? []).length).toBe(15);
    expect(markup).toContain("overflow-x-auto");
    expect(markup).toContain("min-w-max");
  });

  it("does not introduce narratives, complaint IDs, or operational counts", () => {
    const markup = renderToStaticMarkup(<ModelEquations />);
    expect(markup).toContain("No raw complaint narratives or Complaint IDs are shown");
    expect(markup).not.toMatch(/complaintText|ticket count|manager override/iu);
  });
});
