"use client";

import { useApp } from "@/components/app-provider";
import {
  departmentIds,
  formatCount,
  formatMetric,
  modelEvaluation,
  type DepartmentId,
} from "@/lib/model-evaluation";

const departmentKeys: Record<DepartmentId, Parameters<ReturnType<typeof useApp>["t"]>[0]> = {
  transfer_payment: "departmentTransferPayment",
  account_support: "departmentAccountSupport",
  card_atm: "departmentCardAtm",
  fraud_security: "departmentFraudSecurity",
  loan_credit: "departmentLoanCredit",
  general_support: "departmentGeneralSupport",
};

export function ModelAnalyticsDashboard() {
  const { locale, t } = useApp();
  const evaluation = modelEvaluation;
  const count = (value: number) => formatCount(value, locale);
  const cards = [
    ["modelAccuracy", evaluation.metrics.accuracy],
    ["modelMacroPrecision", evaluation.metrics.macro.precision],
    ["modelMacroRecall", evaluation.metrics.macro.recall],
    ["modelMacroF1", evaluation.metrics.macro.f1],
    ["modelWeightedF1", evaluation.metrics.weighted.f1],
  ] as const;
  const pipeline = [
    ["pipelineRaw", evaluation.datasetPipeline.rawRecords],
    ["pipelineNarratives", evaluation.datasetPipeline.recordsWithNarratives],
    ["pipelineMapped", evaluation.datasetPipeline.mappedRecords],
    ["pipelineSelected", evaluation.datasetPipeline.selectedModelingRecords],
    ["pipelineFitted", evaluation.partitions.trainingUsedForFit],
    ["pipelineValidation", evaluation.partitions.validation],
    ["pipelineTest", evaluation.partitions.test],
  ] as const;
  const maxDistribution = Math.max(...departmentIds.map((id) => evaluation.classDistribution.heldOutTestTrue[id]));
  const maxMatrix = Math.max(...evaluation.metrics.confusionMatrix.values.flat());

  return (
    <section id="model-analytics" className="model-analytics" aria-labelledby="model-analytics-title">
      <header className="analytics-hero">
        <div>
          <p className="eyebrow">{t("modelAnalyticsEyebrow")}</p>
          <h2 id="model-analytics-title">{t("modelAnalyticsTitle")}</h2>
          <p>{t("modelAnalyticsLead")}</p>
        </div>
        <div className="held-out-badge">
          <span>{t("modelHeldOutTest")}</span>
          <strong>{count(evaluation.partitions.test)}</strong>
          <small>{t("modelHeldOutRecords")}</small>
        </div>
      </header>

      <div className="model-kpi-grid" aria-label={t("modelPerformanceSummary")}>
        {cards.map(([key, value]) => (
          <article className="model-kpi-card" key={key}>
            <span>{t(key)}</span>
            <strong>{formatMetric(value, locale)}</strong>
          </article>
        ))}
        <article className="model-kpi-card accent">
          <span>{t("modelTestSamples")}</span>
          <strong>{count(evaluation.partitions.test)}</strong>
        </article>
      </div>

      <section className="analytics-card" aria-labelledby="pipeline-title">
        <div className="section-heading">
          <div><p className="eyebrow">{t("datasetFoundation")}</p><h3 id="pipeline-title">{t("datasetPipelineTitle")}</h3></div>
          <p>{t("datasetPipelineLead")}</p>
        </div>
        <ol className="pipeline-flow">
          {pipeline.map(([key, value], index) => (
            <li key={key}>
              <span className="pipeline-index">{index + 1}</span>
              <span>{t(key)}</span>
              <strong>{count(value)}</strong>
            </li>
          ))}
        </ol>
      </section>

      <section className="analytics-card" aria-labelledby="department-performance-title">
        <div className="section-heading">
          <div><p className="eyebrow">{t("sixDepartments")}</p><h3 id="department-performance-title">{t("departmentPerformanceTitle")}</h3></div>
          <p>{t("departmentPerformanceLead")}</p>
        </div>
        <div className="responsive-table" tabIndex={0}>
          <table className="analytics-table department-table">
            <caption>{t("departmentPerformanceCaption")}</caption>
            <thead><tr><th scope="col">{t("department")}</th><th scope="col">{t("metricPrecision")}</th><th scope="col">{t("metricRecall")}</th><th scope="col">{t("metricF1")}</th><th scope="col">{t("metricSupport")}</th></tr></thead>
            <tbody>
              {departmentIds.map((id) => {
                const metric = evaluation.metrics.perDepartment[id];
                return <tr key={id}>
                  <th scope="row">{t(departmentKeys[id])}</th>
                  {[metric.precision, metric.recall, metric.f1].map((value, index) => <td key={index}><div className="metric-bar"><span style={{ width: `${value * 100}%` }} /><strong>{formatMetric(value, locale)}</strong></div></td>)}
                  <td>{count(metric.support)}</td>
                </tr>;
              })}
            </tbody>
          </table>
        </div>
      </section>

      <div className="analytics-split">
        <section className="analytics-card" aria-labelledby="distribution-title">
          <div className="section-heading"><div><p className="eyebrow">{t("heldOutEvidence")}</p><h3 id="distribution-title">{t("classDistributionTitle")}</h3></div></div>
          <div className="distribution-list">
            {departmentIds.map((id) => {
              const value = evaluation.classDistribution.heldOutTestTrue[id];
              return <div key={id}><div><span>{t(departmentKeys[id])}</span><strong>{count(value)}</strong></div><div className="distribution-track"><span style={{ width: `${(value / maxDistribution) * 100}%` }} /></div></div>;
            })}
          </div>
        </section>

        <section className="analytics-card" aria-labelledby="confidence-title">
          <div className="section-heading"><div><p className="eyebrow">{t("predictionEvidence")}</p><h3 id="confidence-title">{t("confidenceAnalysisTitle")}</h3></div><p>{t("confidenceNotAccuracy")}</p></div>
          <div className="threshold-grid">
            {[{ key: "confidenceBelow", group: evaluation.confidence.below }, { key: "confidenceAtOrAbove", group: evaluation.confidence.atOrAbove }].map(({ key, group }) => <article key={key}><span>{t(key as "confidenceBelow")}</span><strong>{count(group.count)}</strong><small>{count(group.correct)} {t("correctLabel")} · {count(group.incorrect)} {t("incorrectLabel")}</small></article>)}
          </div>
          <div className="confidence-bins" aria-label={t("confidenceDistribution") }>
            {evaluation.confidence.bins.map((bin) => <div key={`${bin.lowerInclusive}-${bin.upper}`} className="confidence-bin"><span>{Math.round(bin.lowerInclusive * 100)}–{Math.round(bin.upper * 100)}%</span><div className="stacked-bar" aria-label={`${count(bin.correct)} ${t("correctLabel")}, ${count(bin.incorrect)} ${t("incorrectLabel")}`}><span className="correct" style={{ width: `${bin.count ? (bin.correct / bin.count) * 100 : 0}%` }} /><span className="incorrect" style={{ width: `${bin.count ? (bin.incorrect / bin.count) * 100 : 0}%` }} /></div><strong>{count(bin.count)}</strong></div>)}
          </div>
          <div className="chart-legend"><span><i className="legend-correct" />{t("correctLabel")}</span><span><i className="legend-incorrect" />{t("incorrectLabel")}</span></div>
        </section>
      </div>

      <section className="analytics-card" aria-labelledby="matrix-title">
        <div className="section-heading"><div><p className="eyebrow">{t("errorAnalysis")}</p><h3 id="matrix-title">{t("confusionMatrixTitle")}</h3></div><p>{t("confusionMatrixExplanation")}</p></div>
        <div className="responsive-table matrix-scroll" tabIndex={0}>
          <table className="analytics-table matrix-table">
            <caption>{t("confusionMatrixCaption")}</caption>
            <thead><tr><th scope="col">{t("truePredicted")}</th>{departmentIds.map((id) => <th scope="col" key={id}>{t(departmentKeys[id])}</th>)}</tr></thead>
            <tbody>{departmentIds.map((trueId, rowIndex) => <tr key={trueId}><th scope="row">{t(departmentKeys[trueId])}</th>{evaluation.metrics.confusionMatrix.values[rowIndex].map((value, columnIndex) => <td key={departmentIds[columnIndex]} style={{ backgroundColor: `rgb(21 94 239 / ${0.05 + (value / maxMatrix) * 0.72})` }}><span>{count(value)}</span></td>)}</tr>)}</tbody>
          </table>
        </div>
      </section>

      <div className="analytics-split">
        <section className="analytics-card metadata-card" aria-labelledby="metadata-title">
          <h3 id="metadata-title">{t("evaluationMetadataTitle")}</h3>
          <dl>
            <div><dt>{t("modelVersion")}</dt><dd>{evaluation.metadata.modelVersion}</dd></div>
            <div><dt>{t("evaluationTimestamp")}</dt><dd>{new Intl.DateTimeFormat(locale === "my" ? "my-MM" : "en-US", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(evaluation.metadata.createdAtUtc))} UTC</dd></div>
            <div><dt>{t("randomSeed")}</dt><dd>{count(evaluation.metadata.randomSeed)}</dd></div>
            <div><dt>{t("evaluationPartition")}</dt><dd>{evaluation.metadata.evaluationPartition}</dd></div>
            <div><dt>{t("retrainedStatus")}</dt><dd>{t("notRetrained")}</dd></div>
            <div><dt>{t("duplicateSafety")}</dt><dd>{t("exactDuplicatesSeparated")}</dd></div>
          </dl>
        </section>
        <section className="analytics-card similarity-card" aria-labelledby="similarity-title">
          <p className="eyebrow">{t("localOnly")}</p><h3 id="similarity-title">{t("similarityTitle")}</h3>
          <p>{t("similarityMethod")}: {evaluation.similarity.method}</p>
          <dl><div><dt>{t("similarityCoverage")}</dt><dd>{count(evaluation.similarity.referenceRecords)} {t("heldOutRecords")}</dd></div><div><dt>{t("similarityFeatures")}</dt><dd>{count(evaluation.similarity.featureCount)}</dd></div><div><dt>{t("deploymentStatus")}</dt><dd>{t("notDeployed")}</dd></div></dl>
          <div className="unavailable-note">{t("similarityUnavailableExplanation")}</div>
        </section>
      </div>

      <section className="analytics-card limitations-card" aria-labelledby="limitations-title"><h3 id="limitations-title">{t("limitationsTitle")}</h3><ul>{evaluation.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></section>
    </section>
  );
}
