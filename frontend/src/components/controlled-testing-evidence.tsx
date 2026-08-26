"use client";

import { useApp } from "@/components/app-provider";
import { getDepartmentLabel } from "@/lib/department-labels";
import { controlledTestingEvidence, type ControlledCase } from "@/lib/controlled-testing-evidence";
import { modelEvaluation } from "@/lib/model-evaluation";

function rate(value: number): string {
  return `${value.toFixed(4).replace(/\.0000$/u, "")}%`;
}

function fraction(count: number, total: number, percentage: number): string {
  return `${count}/${total} (${rate(percentage)})`;
}

function exactPercent(value: number): string {
  return `${(value * 100).toFixed(4)}%`;
}

type EvidenceSectionProps = {
  sourceLabel: string;
  title: string;
  shape: string;
  section: typeof controlledTestingEvidence.v1;
  locale: "en" | "my";
  t: ReturnType<typeof useApp>["t"];
};

function EvidenceMetric({ label, value, context }: { label: string; value: string; context?: string }) {
  return (
    <div className="controlled-metric">
      <dt>{label}</dt>
      <dd>{value}</dd>
      {context ? <small>{context}</small> : null}
    </div>
  );
}

function CaseTable({ cases, locale, t }: { cases: readonly ControlledCase[]; locale: "en" | "my"; t: EvidenceSectionProps["t"] }) {
  const label = (id: string | null) => id ? getDepartmentLabel(id, locale) ?? t("evidenceUnavailable") : t("controlledNotSet");
  const reason = (value: string | null) => value === "low_prediction_confidence" ? t("controlledLowConfidence") : value ?? t("controlledNotSet");
  return (
    <div className="responsive-table controlled-table-wrap" tabIndex={0}>
      <table className="analytics-table controlled-case-table">
        <caption>{t("controlledCaseTable")}</caption>
        <thead>
          <tr>
            <th scope="col">{t("controlledCaseId")}</th>
            <th scope="col">{t("controlledExpected")}</th>
            <th scope="col">{t("controlledPredicted")}</th>
            <th scope="col">{t("controlledConfidence")}</th>
            <th scope="col">{t("controlledRouteDecision")}</th>
            <th scope="col">{t("controlledReviewStatus")}</th>
            <th scope="col">{t("controlledFinalRoute")}</th>
            <th scope="col">{t("controlledClassifierMatch")}</th>
            <th scope="col">{t("controlledCorrectAutomatic")}</th>
          </tr>
        </thead>
        <tbody>
          {cases.map((item) => (
            <tr key={item.caseId}>
              <th scope="row"><code>{item.caseId}</code><small>{item.textLengthCategory}</small></th>
              <td>{label(item.expectedDepartmentId)}</td>
              <td>{label(item.predictedDepartmentId)}</td>
              <td>{item.predictionConfidence === null ? t("controlledNotSet") : `${(item.predictionConfidence * 100).toFixed(2)}%`}</td>
              <td>{item.routingSource === "model" ? t("controlledModelRoute") : t("controlledManualRoute")}</td>
              <td>{item.manualReview ? `${t("controlledManualRoute")}: ${reason(item.manualReviewReason)}` : t("controlledNotSet")}</td>
              <td>{label(item.finalRouteDepartmentId)}</td>
              <td><span className="controlled-boolean">{item.classifierPredictionMatches ? t("controlledYes") : t("controlledNo")}</span></td>
              <td><span className="controlled-boolean">{item.correctAutomaticRoute ? t("controlledYes") : t("controlledNo")}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EvidenceSection({ sourceLabel, title, shape, section, locale, t }: EvidenceSectionProps) {
  const { summary } = section;
  const automaticCoverage = summary.automaticRouteCoverage ?? (summary.automaticRouteCount / summary.totalCases) * 100;
  const manualRate = summary.manualReviewRate ?? (summary.manualReviewCount / summary.totalCases) * 100;
  return (
    <details className="analytics-card controlled-section">
      <summary className="controlled-section-summary">
        <span className="controlled-source-badge">{sourceLabel}</span>
        <span><strong>{title}</strong><small>{shape}</small></span>
      </summary>
      <div className="controlled-section-body">
        <dl className="controlled-metrics" aria-label={title}>
          <EvidenceMetric label={t("controlledClassifierMatchRate")} value={fraction(summary.classifierPredictionMatchCount, summary.totalCases, summary.classifierPredictionMatchRate)} />
          <EvidenceMetric label={t("controlledAutomaticCoverage")} value={fraction(summary.automaticRouteCount, summary.totalCases, automaticCoverage)} />
          <EvidenceMetric label={t("controlledAutomaticCorrectness")} value={fraction(summary.correctAutomaticRouteCount, summary.automaticRouteCount, summary.automaticRoutingSuccessRate)} context={t("controlledNotAccuracy")} />
          <EvidenceMetric label={t("controlledManualReviewRate")} value={fraction(summary.manualReviewCount, summary.totalCases, manualRate)} />
          {summary.correctPredictionsSentToManualReview !== undefined ? <EvidenceMetric label={t("controlledCorrectHeldReview")} value={String(summary.correctPredictionsSentToManualReview)} /> : null}
          {summary.incorrectPredictionsSentToManualReview !== undefined ? <EvidenceMetric label={t("controlledIncorrectHeldReview")} value={String(summary.incorrectPredictionsSentToManualReview)} /> : null}
          {summary.confidentlyIncorrectAutomaticRouteCount !== undefined ? <EvidenceMetric label={t("controlledConfidentIncorrect")} value={String(summary.confidentlyIncorrectAutomaticRouteCount)} /> : null}
          <EvidenceMetric label={t("controlledManagerOverrides")} value={String(summary.managerOverrideCount)} />
        </dl>
        <p className="controlled-disclosure" role="note">{t("controlledManualReviewExplanation")}</p>
        <CaseTable cases={section.cases} locale={locale} t={t} />
      </div>
    </details>
  );
}

export function ControlledTestingEvidence() {
  const { locale, t } = useApp();
  return (
    <section className="analytics-card controlled-evidence" aria-labelledby="controlled-evidence-title">
      <div className="section-heading">
        <div><p className="eyebrow">{t("controlledEvidenceEyebrow")}</p><h3 id="controlled-evidence-title">{t("controlledEvidenceTitle")}</h3></div>
        <p>{t("controlledEvidenceLead")}</p>
      </div>
      <p className="controlled-source-note"><span className="controlled-source-badge">{t("controlledSourceFrozen")}</span> {t("controlledOfficialAccuracy")} {exactPercent(modelEvaluation.metrics.accuracy)}. {t("controlledBelowTarget")} {modelEvaluation.metrics.macro.f1.toFixed(6)} {t("controlledBelowTargetSuffix")}</p>
      <div className="controlled-sections">
        <EvidenceSection sourceLabel={t("controlledSourceV1")} title={t("controlledV1Title")} shape={t("controlledV1Shape")} section={controlledTestingEvidence.v1} locale={locale} t={t} />
        <EvidenceSection sourceLabel={t("controlledSourceV2")} title={t("controlledV2Title")} shape={t("controlledV2Shape")} section={controlledTestingEvidence.v2} locale={locale} t={t} />
      </div>
      <p className="controlled-disclosure" role="status">{t("controlledEvidenceDisclosure")} {t("controlledSmallSample")} {t("controlledDeterministicLabels")}</p>
    </section>
  );
}
