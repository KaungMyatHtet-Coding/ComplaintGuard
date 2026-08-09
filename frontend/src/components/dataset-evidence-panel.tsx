import { useApp } from "@/components/app-provider";
import {
  formatCount,
  formatMetric,
  modelEvaluation,
  type DepartmentId,
} from "@/lib/model-evaluation";

type DatasetEvidencePanelProps = {
  predictedDepartmentId?: string | null;
  predictionConfidence?: number | null;
  routingSource?: string | null;
  assignedDepartmentId?: string | null;
};

const departmentKeys: Record<DepartmentId, Parameters<ReturnType<typeof useApp>["t"]>[0]> = {
  transfer_payment: "departmentTransferPayment",
  account_support: "departmentAccountSupport",
  card_atm: "departmentCardAtm",
  fraud_security: "departmentFraudSecurity",
  loan_credit: "departmentLoanCredit",
  general_support: "departmentGeneralSupport",
};

export function DatasetEvidencePanel({
  predictedDepartmentId,
  predictionConfidence,
  routingSource,
  assignedDepartmentId,
}: DatasetEvidencePanelProps) {
  const { locale, t } = useApp();
  const threshold = modelEvaluation.confidence.threshold;
  const validDepartment = (value?: string | null): value is DepartmentId =>
    Boolean(value && value in departmentKeys);
  const departmentName = (value?: string | null) =>
    validDepartment(value) ? t(departmentKeys[value]) : t("evidenceUnavailable");
  const confidenceAvailable =
    typeof predictionConfidence === "number" && Number.isFinite(predictionConfidence);
  const manualReview = routingSource === "manual_review";

  return (
    <section className="evidence-panel" aria-labelledby="dataset-evidence-title">
      <div className="evidence-heading">
        <div>
          <p className="eyebrow">{t("evidenceEyebrow")}</p>
          <h3 id="dataset-evidence-title">{t("evidenceTitle")}</h3>
        </div>
        <span className={`evidence-status ${manualReview ? "is-review" : ""}`}>
          {manualReview ? t("evidenceManualReview") : t("evidenceRoutingAutomated")}
        </span>
      </div>

      <dl className="evidence-grid">
        <div>
          <dt>{t("evidencePredictedDepartment")}</dt>
          <dd>{departmentName(predictedDepartmentId)}</dd>
        </div>
        <div>
          <dt>{t("evidenceAssignedDepartment")}</dt>
          <dd>{departmentName(assignedDepartmentId)}</dd>
        </div>
        <div>
          <dt>{t("evidencePredictionConfidence")}</dt>
          <dd>
            {confidenceAvailable
              ? formatMetric(predictionConfidence, locale)
              : t("evidencePending")}
          </dd>
        </div>
        <div>
          <dt>{t("evidenceOperationalThreshold")}</dt>
          <dd>
            {formatMetric(threshold, locale)}
          </dd>
        </div>
      </dl>

      <div className="evidence-explanation">
        <strong>{t("evidenceConfidenceNotAccuracy")}</strong>
        <p>{t("evidenceConfidenceExplanation")}</p>
        {confidenceAvailable ? (
          <p>
            {predictionConfidence < threshold
              ? t("evidenceBelowThreshold")
              : t("evidenceAtOrAboveThreshold")}
          </p>
        ) : null}
      </div>

      <div className="evidence-similarity" role="status">
        <strong>{t("evidenceSimilarityLocalOnly")}</strong>
        <p>
          {t("evidenceSimilarityCoverage")}{" "}
          {formatCount(modelEvaluation.similarity.referenceRecords, locale)}{" "}
          {t("evidenceSimilarityRecords")}. {t("evidenceSimilarityUnavailable")}
        </p>
      </div>
    </section>
  );
}
