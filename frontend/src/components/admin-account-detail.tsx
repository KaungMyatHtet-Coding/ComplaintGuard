"use client";

import { createPortal } from "react-dom";
import { useEffect, useMemo, useRef, useState } from "react";

import { useApp } from "@/components/app-provider";
import { getDepartmentLabel } from "@/lib/department-labels";
import {
  loadAdminLifecycleRecoveryStatus,
  type AdminLifecycleRecoveryOperation,
  type AdminLifecycleRecoveryStatus,
} from "@/lib/admin-lifecycle";
import {
  loadAdminLifecycleEligibility,
  type AdminDirectoryErrorCode,
  type AdminLifecycleEligibility,
} from "@/lib/admin-directory";
import type { AdminDirectoryResponse } from "@/lib/admin-directory";
import type { MessageKey } from "@/lib/i18n";

type AdminDirectoryRow = AdminDirectoryResponse["rows"][number];

type AdminAccountDetailProps = {
  row: AdminDirectoryRow;
  openerRef: React.MutableRefObject<HTMLButtonElement | null>;
  fallbackRef: React.RefObject<HTMLElement | null>;
  canRestoreFocus: () => boolean;
  onClose: () => void;
};

function focusableElements(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(
    "button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex=\"-1\"])",
  ));
}

type LifecycleDetailState =
  | { status: "loading" }
  | { status: "ready"; accountRef: string; profileUid: string; eligibility: AdminLifecycleEligibility; recovery: AdminLifecycleRecoveryStatus }
  | { status: "error"; accountRef: string; profileUid: string; code: AdminDirectoryErrorCode };

const lifecycleErrorMessages: Record<AdminDirectoryErrorCode, string> = {
  authentication: "adminLifecycleAuthentication",
  permission: "adminLifecyclePermission",
  validation: "adminLifecycleValidation",
  notFound: "adminLifecycleNotFound",
  unavailable: "adminLifecycleUnavailable",
  unexpected: "adminLifecycleUnexpected",
};

const eligibilityReasonMessages: Record<NonNullable<AdminLifecycleEligibility["operations"]["disable"]["reason"]>, string> = {
  already_active: "adminLifecycleReasonAlreadyActive",
  already_inactive: "adminLifecycleReasonAlreadyInactive",
  self_target_forbidden: "adminLifecycleReasonSelfTarget",
  last_active_admin: "adminLifecycleReasonLastActiveAdmin",
  role_not_reassignable: "adminLifecycleReasonRoleNotReassignable",
  assigned_unresolved_work: "adminLifecycleReasonAssignedWork",
  pending_setup_activation_forbidden: "adminLifecycleReasonPendingSetup",
};

function operationLabel(t: (key: MessageKey) => string, operation: AdminLifecycleRecoveryOperation): string {
  if (operation === "disable") return t("adminLifecycleOperationDisable");
  if (operation === "reactivate") return t("adminLifecycleOperationReactivate");
  return t("adminLifecycleOperationReassign");
}

export function AdminAccountDetail({ row, openerRef, fallbackRef, canRestoreFocus, onClose }: AdminAccountDetailProps) {
  const { locale, profile, t } = useApp();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [lifecycleState, setLifecycleState] = useState<LifecycleDetailState>({ status: "loading" });
  const [lifecycleRetryNonce, setLifecycleRetryNonce] = useState(0);
  const lifecycleRequestIdRef = useRef(0);
  const roleLabel = useMemo(() => {
    if (row.role === "customer") return t("adminCustomer");
    if (row.role === "staff") return t("adminStaff");
    if (row.role === "manager") return t("adminManager");
    return t("adminRoleAdmin");
  }, [row.role, t]);
  const explanation = useMemo(() => {
    if (row.role === "customer") return t("adminDetailCustomerExplanation");
    if (row.role === "staff") return t("adminDetailStaffExplanation");
    if (row.role === "manager") return t("adminDetailManagerExplanation");
    return t("adminDetailAdminExplanation");
  }, [row.role, t]);
  const title = row.displayName || t("adminDirectorySafeFallbackName");

  useEffect(() => {
    const requestId = ++lifecycleRequestIdRef.current;
    const controller = new AbortController();
    void (async () => {
      await Promise.resolve();
      if (!profile || profile.role !== "admin" || profile.active !== true) {
        if (!controller.signal.aborted && requestId === lifecycleRequestIdRef.current) {
          setLifecycleState({ status: "error", accountRef: row.accountRef, profileUid: profile?.uid ?? "", code: "authentication" });
        }
        return;
      }
      setLifecycleState({ status: "loading" });
      try {
        const [eligibility, recovery] = await Promise.all([
          loadAdminLifecycleEligibility(row.accountRef, fetch, controller.signal),
          loadAdminLifecycleRecoveryStatus(row.accountRef, fetch, controller.signal),
        ]);
        if (!controller.signal.aborted && requestId === lifecycleRequestIdRef.current) {
          setLifecycleState({ status: "ready", accountRef: row.accountRef, profileUid: profile.uid, eligibility, recovery });
        }
      } catch (error: unknown) {
        if (controller.signal.aborted || requestId !== lifecycleRequestIdRef.current) return;
        const candidate = error && typeof error === "object" && "code" in error
          ? (error as { code: AdminDirectoryErrorCode }).code
          : "unexpected";
        const code = candidate in lifecycleErrorMessages ? candidate as AdminDirectoryErrorCode : "unexpected";
        setLifecycleState({ status: "error", accountRef: row.accountRef, profileUid: profile?.uid ?? "", code });
      }
    })();
    return () => controller.abort();
  }, [lifecycleRetryNonce, profile, row.accountRef]);

  const lifecycleStateForRow = lifecycleState.status === "loading" || (
    lifecycleState.accountRef === row.accountRef && lifecycleState.profileUid === profile?.uid
  ) ? lifecycleState : { status: "loading" as const };

  useEffect(() => {
    const dialog = dialogRef.current;
    const main = document.getElementById("dashboard-main") as HTMLElement | null;
    const header = document.querySelector(".app-header") as HTMLElement | null;
    const sidebar = document.querySelector(".dashboard-sidebar-host") as HTMLElement | null;
    const previousMainInert = main?.inert ?? false;
    const previousMainAriaHidden = main ? main.getAttribute("aria-hidden") : null;
    const previousHeaderInert = header?.inert ?? false;
    const previousHeaderAriaHidden = header ? header.getAttribute("aria-hidden") : null;
    const previousSidebarInert = sidebar?.inert ?? false;
    const previousSidebarAriaHidden = sidebar ? sidebar.getAttribute("aria-hidden") : null;
    const previousOverflow = document.body.style.overflow;
    if (!dialog) return;

    if (main) {
      main.inert = true;
      main.setAttribute("aria-hidden", "true");
    }
    if (header) {
      header.inert = true;
      header.setAttribute("aria-hidden", "true");
    }
    if (sidebar) {
      sidebar.inert = true;
      sidebar.setAttribute("aria-hidden", "true");
    }
    document.body.classList.add("admin-account-detail-open");
    document.body.style.overflow = "hidden";

    const focusCloseButton = () => closeButtonRef.current?.focus();
    const focusFallback = () => {
      const opener = openerRef.current;
      if (opener?.isConnected) opener.focus();
      else if (fallbackRef.current?.isConnected) fallbackRef.current.focus();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = focusableElements(dialog);
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    focusCloseButton();

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.classList.remove("admin-account-detail-open");
      document.body.style.overflow = previousOverflow;
      if (main) {
        main.inert = previousMainInert;
        if (previousMainAriaHidden === null) main.removeAttribute("aria-hidden");
        else main.setAttribute("aria-hidden", previousMainAriaHidden);
      }
      if (header) {
        header.inert = previousHeaderInert;
        if (previousHeaderAriaHidden === null) header.removeAttribute("aria-hidden");
        else header.setAttribute("aria-hidden", previousHeaderAriaHidden);
      }
      if (sidebar) {
        sidebar.inert = previousSidebarInert;
        if (previousSidebarAriaHidden === null) sidebar.removeAttribute("aria-hidden");
        else sidebar.setAttribute("aria-hidden", previousSidebarAriaHidden);
      }
      if (canRestoreFocus()) focusFallback();
    };
  }, [canRestoreFocus, fallbackRef, onClose, openerRef]);

  const content = (
    <div className="admin-account-detail-overlay">
      <button className="admin-account-detail-backdrop" type="button" aria-label={t("adminAccountDetailClose")} onClick={onClose} />
      <div
        ref={dialogRef}
        className="admin-account-detail-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="admin-account-detail-title"
        tabIndex={-1}
      >
        <header className="admin-account-detail-header">
          <div>
            <p className="admin-section-eyebrow">{t("adminAccountDetailEyebrow")}</p>
            <h2 id="admin-account-detail-title">{title}</h2>
          </div>
          <button ref={closeButtonRef} className="admin-secondary-button" type="button" onClick={onClose} aria-label={t("adminAccountDetailClose")}>
            {t("adminAccountDetailClose")}
          </button>
        </header>
        <div className="admin-account-detail-body">
          <p className="admin-account-detail-lead">{t("adminAccountDetailLead")}</p>
          <dl className="admin-account-detail-fields">
            <div><dt>{t("adminDirectoryName")}</dt><dd>{title}</dd></div>
            <div><dt>{t("adminEmail")}</dt><dd className="admin-break-value">{row.email}</dd></div>
            <div><dt>{t("adminRole")}</dt><dd>{roleLabel}</dd></div>
            <div><dt>{t("adminDepartment")}</dt><dd>{row.departmentId ? getDepartmentLabel(row.departmentId, locale) : t("adminNotApplicable")}</dd></div>
            <div><dt>{t("adminDirectoryLanguage")}</dt><dd>{row.locale === "en" ? t("english") : t("myanmar")}</dd></div>
            <div><dt>{t("adminDirectoryStatus")}</dt><dd><span className={`admin-status-chip ${row.active ? "is-active" : "is-pending"}`}>{row.active ? t("adminDirectoryActive") : t("adminDirectoryPending")}</span></dd></div>
          </dl>
          <section className="admin-account-detail-explanation" aria-labelledby="admin-account-detail-explanation-title">
            <h3 id="admin-account-detail-explanation-title">{t("adminAccountDetailStatusTitle")}</h3>
            <p>{explanation}</p>
            {!row.active && (row.role === "staff" || row.role === "manager") ? <p>{t("adminDirectoryOwnerNotice")}</p> : null}
            <p>{t("adminDetailProfileStateNote")}</p>
          </section>
          <section className="admin-account-detail-management" aria-labelledby="admin-account-detail-management-title">
            <h3 id="admin-account-detail-management-title">{t("adminLifecycleManagementTitle")}</h3>
            {lifecycleStateForRow.status === "loading" ? <div className="admin-lifecycle-skeleton" role="status" aria-label={t("adminLifecycleLoading")} aria-busy="true"><span aria-hidden="true" /></div> : null}
            {lifecycleStateForRow.status === "error" ? <div role="alert" className="admin-error-panel"><p>{t(lifecycleErrorMessages[lifecycleStateForRow.code] as MessageKey)}</p><button className="admin-secondary-button" type="button" onClick={() => setLifecycleRetryNonce((value) => value + 1)}>{t("adminLifecycleRetry")}</button></div> : null}
            {lifecycleStateForRow.status === "ready" ? <>
              <section aria-labelledby="admin-lifecycle-eligibility-title">
                <h4 id="admin-lifecycle-eligibility-title">{t("adminLifecycleEligibilityTitle")}</h4>
                <p>{t("adminLifecycleEligibilityLead")}</p>
                <ul className="admin-lifecycle-operation-list">
                  {(["disable", "reactivate", "reassignDepartment"] as const).map((key) => {
                    const operation = lifecycleStateForRow.eligibility.operations[key];
                    const label = key === "disable" ? t("adminLifecycleOperationDisable") : key === "reactivate" ? t("adminLifecycleOperationReactivate") : t("adminLifecycleOperationReassign");
                    const reason = operation.reason ? t(eligibilityReasonMessages[operation.reason] as never) : t("adminLifecycleAvailable");
                    return <li key={key}><span>{label}</span><span>{reason}</span></li>;
                  })}
                </ul>
              </section>
              {lifecycleStateForRow.recovery.recoveryState === "recoverable" ? <section className="admin-lifecycle-recovery" aria-labelledby="admin-lifecycle-recovery-title"><h4 id="admin-lifecycle-recovery-title">{t("adminLifecycleRecoveryTitle")}</h4><p>{t("adminLifecycleRecoverableMessage")}</p><p>{operationLabel(t, lifecycleStateForRow.recovery.operation as AdminLifecycleRecoveryOperation)}{lifecycleStateForRow.recovery.operation === "reassign_department" && lifecycleStateForRow.recovery.departmentId ? `: ${getDepartmentLabel(lifecycleStateForRow.recovery.departmentId, locale)}` : ""}</p></section> : null}
              {lifecycleStateForRow.recovery.recoveryState === "completed" ? <section className="admin-lifecycle-recovery" aria-labelledby="admin-lifecycle-recovery-title"><h4 id="admin-lifecycle-recovery-title">{t("adminLifecycleRecoveryTitle")}</h4><p>{t("adminLifecycleCompletedMessage")}</p><p>{operationLabel(t, lifecycleStateForRow.recovery.operation as AdminLifecycleRecoveryOperation)}{lifecycleStateForRow.recovery.operation === "reassign_department" && lifecycleStateForRow.recovery.departmentId ? `: ${getDepartmentLabel(lifecycleStateForRow.recovery.departmentId, locale)}` : ""}</p></section> : null}
              {lifecycleStateForRow.recovery.recoveryState === "operator_required" ? <section className="admin-lifecycle-recovery" aria-labelledby="admin-lifecycle-recovery-title"><h4 id="admin-lifecycle-recovery-title">{t("adminLifecycleRecoveryTitle")}</h4><p>{t("adminLifecycleOperatorRequired")}</p></section> : null}
            </> : null}
          </section>
        </div>
      </div>
    </div>
  );

  return typeof document === "undefined" ? content : createPortal(content, document.body);
}
