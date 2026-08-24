"use client";

import { createPortal } from "react-dom";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { useApp } from "@/components/app-provider";
import { getDepartmentLabel } from "@/lib/department-labels";
import {
  continueAdminDisable,
  continueAdminReactivate,
  disableAdminAccount,
  generateAdminLifecycleIdempotencyKey,
  loadAdminLifecycleRecoveryStatus,
  reactivateAdminAccount,
  type AdminDisableResult,
  type AdminReactivateResult,
  type AdminLifecycleRequestError,
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

const accountStateLabelKeys: Record<AdminDirectoryRow["accountState"], MessageKey> = {
  active: "adminDirectoryState_active",
  pending_setup: "adminDirectoryState_pending_setup",
  disabled: "adminDirectoryState_disabled",
  inactive_unverified: "adminDirectoryState_inactive_unverified",
};

type AdminAccountDetailProps = {
  row: AdminDirectoryRow;
  openerRef: React.MutableRefObject<HTMLButtonElement | null>;
  fallbackRef: React.RefObject<HTMLElement | null>;
  canRestoreFocus: () => boolean;
  onClose: () => void;
  onLifecycleSuccess?: (accountRef: string, operation?: "disable" | "reactivate") => void;
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

type DisableMutationState = "idle" | "confirming" | "submitting" | "unknown" | "retryable" | "recoverable" | "success" | "operator_required" | "error";
type ReactivateMutationState = DisableMutationState;

export function isFreshDisableTarget(row: AdminDirectoryRow): boolean {
  return row.active && row.accountState === "active" && (row.role === "customer" || row.role === "staff" || row.role === "manager");
}

export function isFreshReactivateTarget(row: AdminDirectoryRow): boolean {
  return !row.active && row.accountState === "disabled" && (row.role === "customer" || row.role === "staff" || row.role === "manager");
}

export function isFreshReactivateEligible(
  row: AdminDirectoryRow,
  eligibility: AdminLifecycleEligibility,
): boolean {
  return isFreshReactivateTarget(row) && eligibility.profileState === "inactive" && eligibility.operations.reactivate.eligible;
}

export function isFreshReactivateRecoveryCompatible(recovery: AdminLifecycleRecoveryStatus): boolean {
  return recovery.recoveryState === "none" || (
    recovery.recoveryState === "completed" &&
    recovery.operation === "disable" &&
    recovery.departmentId === null
  );
}

function operationLabel(t: (key: MessageKey) => string, operation: AdminLifecycleRecoveryOperation): string {
  if (operation === "disable") return t("adminLifecycleOperationDisable");
  if (operation === "reactivate") return t("adminLifecycleOperationReactivate");
  return t("adminLifecycleOperationReassign");
}

export function AdminAccountDetail({ row, openerRef, fallbackRef, canRestoreFocus, onClose, onLifecycleSuccess }: AdminAccountDetailProps) {
  const { locale, profile, t } = useApp();
  const dialogRef = useRef<HTMLDivElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const disableButtonRef = useRef<HTMLButtonElement>(null);
  const reactivateButtonRef = useRef<HTMLButtonElement>(null);
  const confirmationDialogRef = useRef<HTMLDivElement>(null);
  const confirmationCancelRef = useRef<HTMLButtonElement>(null);
  const confirmationContinueRef = useRef(false);
  const disableKeyRef = useRef<string | null>(null);
  const disableAttemptControllerRef = useRef<AbortController | null>(null);
  const disableRequestIdRef = useRef(0);
  const reactivateKeyRef = useRef<string | null>(null);
  const reactivateAttemptControllerRef = useRef<AbortController | null>(null);
  const reactivateRequestIdRef = useRef(0);
  const unknownOutcomeRef = useRef(false);
  const resolvedUnknownRef = useRef(false);
  const reactivateUnknownOutcomeRef = useRef(false);
  const reactivateResolvedUnknownRef = useRef(false);
  const recoveryStatusInFlightRef = useRef(false);
  const confirmationOpenRef = useRef(false);
  const confirmationOperationRef = useRef<"disable" | "reactivate">("disable");
  const [lifecycleState, setLifecycleState] = useState<LifecycleDetailState>({ status: "loading" });
  const [lifecycleRetryNonce, setLifecycleRetryNonce] = useState(0);
  const [disableMutationState, setDisableMutationState] = useState<DisableMutationState>("idle");
  const [disableConfirmationOpen, setDisableConfirmationOpen] = useState(false);
  const [disableMessage, setDisableMessage] = useState<"success" | "unknown" | "error" | null>(null);
  const [reactivateMutationState, setReactivateMutationState] = useState<ReactivateMutationState>("idle");
  const [reactivateMessage, setReactivateMessage] = useState<"success" | "unknown" | "error" | null>(null);
  const [confirmationOperation, setConfirmationOperation] = useState<"disable" | "reactivate">("disable");
  const lifecycleRequestIdRef = useRef(0);
  useEffect(() => {
    confirmationOpenRef.current = disableConfirmationOpen;
  }, [disableConfirmationOpen]);
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
  const accountStateLabel = t(accountStateLabelKeys[row.accountState]);
  const accountStateExplanation = row.accountState === "active"
    ? t("adminDetailStateActive")
    : row.accountState === "pending_setup"
      ? t("adminDetailStatePending")
      : row.accountState === "disabled"
        ? t("adminDetailStateDisabled")
        : t("adminDetailStateUnavailable");
  const title = row.displayName || t("adminDirectorySafeFallbackName");

  const clearDisableAttempt = () => {
    disableKeyRef.current = null;
    unknownOutcomeRef.current = false;
    resolvedUnknownRef.current = false;
  };

  const clearReactivateAttempt = () => {
    reactivateKeyRef.current = null;
    reactivateUnknownOutcomeRef.current = false;
    reactivateResolvedUnknownRef.current = false;
  };

  const finishDisable = useCallback((result: AdminDisableResult) => {
    if (result.accountRef !== row.accountRef) {
      setDisableMutationState("error");
      setDisableMessage("error");
      clearDisableAttempt();
      return;
    }
    disableAttemptControllerRef.current = null;
    clearDisableAttempt();
    setDisableMutationState("success");
    setDisableMessage("success");
    setDisableConfirmationOpen(false);
    onLifecycleSuccess?.(row.accountRef, "disable");
    setLifecycleRetryNonce((value) => value + 1);
  }, [onLifecycleSuccess, row.accountRef]);

  const finishReactivate = useCallback((result: AdminReactivateResult) => {
    if (result.accountRef !== row.accountRef) {
      setReactivateMutationState("error");
      setReactivateMessage("error");
      clearReactivateAttempt();
      return;
    }
    reactivateAttemptControllerRef.current = null;
    clearReactivateAttempt();
    setReactivateMutationState("success");
    setReactivateMessage("success");
    setDisableConfirmationOpen(false);
    onLifecycleSuccess?.(row.accountRef, "reactivate");
    setLifecycleRetryNonce((value) => value + 1);
  }, [onLifecycleSuccess, row.accountRef]);

  const handleDisableFailure = (error: unknown) => {
    disableAttemptControllerRef.current = null;
    const requestError = error as Partial<AdminLifecycleRequestError>;
    if (requestError.outcome === "unknown") {
      unknownOutcomeRef.current = true;
      setDisableMutationState("unknown");
      setDisableMessage("unknown");
      setLifecycleRetryNonce((value) => value + 1);
      return;
    }
    const status = requestError.httpStatus;
    if (status === 409 || status === 503) {
      unknownOutcomeRef.current = true;
      setDisableMutationState("unknown");
      setDisableMessage("error");
      setLifecycleRetryNonce((value) => value + 1);
      return;
    }
    clearDisableAttempt();
    setDisableMutationState("error");
    setDisableMessage("error");
  };

  const submitDisable = (continueExisting: boolean) => {
    if (disableMutationState === "submitting" || disableAttemptControllerRef.current) return;
    let key = disableKeyRef.current;
    if (!continueExisting && !key) {
      try {
        key = generateAdminLifecycleIdempotencyKey();
        disableKeyRef.current = key;
      } catch {
        setDisableMutationState("error");
        setDisableMessage("error");
        return;
      }
    }
    if (!continueExisting && !key) return;
    const controller = new AbortController();
    const requestId = ++disableRequestIdRef.current;
    disableAttemptControllerRef.current = controller;
    setDisableMutationState("submitting");
    setDisableMessage(null);
    const request = continueExisting
      ? continueAdminDisable(row.accountRef, fetch, controller.signal)
      : disableAdminAccount(row.accountRef, key as string, fetch, controller.signal);
    const timeoutId = setTimeout(() => controller.abort(), 30_000);
    void request
      .then((result) => {
        if (requestId === disableRequestIdRef.current) finishDisable(result);
      })
      .catch((error: unknown) => {
        if (requestId === disableRequestIdRef.current) handleDisableFailure(error);
      })
      .finally(() => clearTimeout(timeoutId));
  };

  const handleReactivateFailure = (error: unknown) => {
    reactivateAttemptControllerRef.current = null;
    const requestError = error as Partial<AdminLifecycleRequestError>;
    if (requestError.outcome === "unknown" || requestError.httpStatus === 409 || requestError.httpStatus === 503) {
      reactivateUnknownOutcomeRef.current = true;
      setReactivateMutationState("unknown");
      setReactivateMessage(requestError.outcome === "unknown" ? "unknown" : "error");
      setLifecycleRetryNonce((value) => value + 1);
      return;
    }
    clearReactivateAttempt();
    setReactivateMutationState("error");
    setReactivateMessage("error");
  };

  const submitReactivate = (continueExisting: boolean) => {
    if (reactivateMutationState === "submitting" || reactivateAttemptControllerRef.current) return;
    let key = reactivateKeyRef.current;
    if (!continueExisting && !key) {
      try {
        key = generateAdminLifecycleIdempotencyKey();
        reactivateKeyRef.current = key;
      } catch {
        setReactivateMutationState("error");
        setReactivateMessage("error");
        return;
      }
    }
    if (!continueExisting && !key) return;
    const controller = new AbortController();
    const requestId = ++reactivateRequestIdRef.current;
    reactivateAttemptControllerRef.current = controller;
    setReactivateMutationState("submitting");
    setReactivateMessage(null);
    const request = continueExisting
      ? continueAdminReactivate(row.accountRef, fetch, controller.signal)
      : reactivateAdminAccount(row.accountRef, key as string, fetch, controller.signal);
    const timeoutId = setTimeout(() => controller.abort(), 30_000);
    void request
      .then((result) => {
        if (requestId === reactivateRequestIdRef.current) finishReactivate(result);
      })
      .catch((error: unknown) => {
        if (requestId === reactivateRequestIdRef.current) handleReactivateFailure(error);
      })
      .finally(() => clearTimeout(timeoutId));
  };

  const reconcileUnknownOutcome = useCallback((recovery: AdminLifecycleRecoveryStatus) => {
    if (!unknownOutcomeRef.current || resolvedUnknownRef.current) return;
    resolvedUnknownRef.current = true;
    unknownOutcomeRef.current = false;
    if (recovery.recoveryState === "recoverable" && recovery.operation === "disable") {
      setDisableMutationState("recoverable");
      setDisableMessage(null);
    } else if (recovery.recoveryState === "completed" && recovery.operation === "disable") {
      finishDisable({ accountRef: row.accountRef, operation: "disable", status: "completed", profileState: "inactive" });
    } else if (recovery.recoveryState === "none") {
      setDisableMutationState("retryable");
      setDisableMessage("unknown");
    } else if (recovery.recoveryState === "operator_required") {
      setDisableMutationState("operator_required");
      setDisableMessage(null);
      clearDisableAttempt();
    } else {
      setDisableMutationState("error");
      setDisableMessage("error");
      clearDisableAttempt();
    }
  }, [finishDisable, row.accountRef]);

  const reconcileReactivateUnknownOutcome = useCallback((recovery: AdminLifecycleRecoveryStatus) => {
    if (!reactivateUnknownOutcomeRef.current || reactivateResolvedUnknownRef.current) return;
    reactivateResolvedUnknownRef.current = true;
    reactivateUnknownOutcomeRef.current = false;
    if (recovery.recoveryState === "recoverable" && recovery.operation === "reactivate") {
      setReactivateMutationState("recoverable");
      setReactivateMessage(null);
    } else if (recovery.recoveryState === "completed" && recovery.operation === "reactivate") {
      finishReactivate({ accountRef: row.accountRef, operation: "reactivate", status: "completed", profileState: "active" });
    } else if (recovery.recoveryState === "none") {
      setReactivateMutationState("retryable");
      setReactivateMessage("unknown");
    } else if (recovery.recoveryState === "operator_required") {
      setReactivateMutationState("operator_required");
      setReactivateMessage(null);
      clearReactivateAttempt();
    } else {
      setReactivateMutationState("error");
      setReactivateMessage("error");
      clearReactivateAttempt();
    }
  }, [finishReactivate, row.accountRef]);

  useEffect(() => {
    const requestId = ++lifecycleRequestIdRef.current;
    const controller = new AbortController();
    recoveryStatusInFlightRef.current = true;
    void (async () => {
      await Promise.resolve();
      if (!profile || profile.role !== "admin" || profile.active !== true) {
        if (!controller.signal.aborted && requestId === lifecycleRequestIdRef.current) {
          setLifecycleState({ status: "error", accountRef: row.accountRef, profileUid: profile?.uid ?? "", code: "authentication" });
        }
        if (requestId === lifecycleRequestIdRef.current) recoveryStatusInFlightRef.current = false;
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
          reconcileUnknownOutcome(recovery);
          reconcileReactivateUnknownOutcome(recovery);
        }
      } catch (error: unknown) {
        if (controller.signal.aborted || requestId !== lifecycleRequestIdRef.current) return;
        const candidate = error && typeof error === "object" && "code" in error
          ? (error as { code: AdminDirectoryErrorCode }).code
          : "unexpected";
        const code = candidate in lifecycleErrorMessages ? candidate as AdminDirectoryErrorCode : "unexpected";
        setLifecycleState({ status: "error", accountRef: row.accountRef, profileUid: profile?.uid ?? "", code });
      } finally {
        if (requestId === lifecycleRequestIdRef.current) recoveryStatusInFlightRef.current = false;
      }
    })();
    return () => controller.abort();
  }, [lifecycleRetryNonce, profile, reconcileReactivateUnknownOutcome, reconcileUnknownOutcome, row.accountRef, row.active, row.accountState, row.departmentId, row.role]);

  useEffect(() => () => {
    disableRequestIdRef.current += 1;
    disableAttemptControllerRef.current?.abort();
    disableAttemptControllerRef.current = null;
    clearDisableAttempt();
    reactivateRequestIdRef.current += 1;
    reactivateAttemptControllerRef.current?.abort();
    reactivateAttemptControllerRef.current = null;
    clearReactivateAttempt();
  }, [profile?.uid, row.accountRef]);

  const lifecycleStateForRow = lifecycleState.status === "loading" || (
    lifecycleState.accountRef === row.accountRef && lifecycleState.profileUid === profile?.uid
  ) ? lifecycleState : { status: "loading" as const };

  const lifecycleReady = lifecycleStateForRow.status === "ready";
  const disableEligible = lifecycleReady && lifecycleStateForRow.eligibility.operations.disable.eligible;
  const reactivateEligible = lifecycleReady && lifecycleStateForRow.eligibility.operations.reactivate.eligible;
  const supportedRole = row.role === "customer" || row.role === "staff" || row.role === "manager";
  const freshDisableTarget = isFreshDisableTarget(row);
  const operatorRequired = lifecycleReady && lifecycleStateForRow.recovery.recoveryState === "operator_required";
  const recoveryBlocksFreshDisable = lifecycleReady && lifecycleStateForRow.recovery.recoveryState === "recoverable";
  const showFreshDisable = lifecycleReady && freshDisableTarget && disableEligible && !operatorRequired && !recoveryBlocksFreshDisable && disableMutationState !== "submitting" && disableMutationState !== "unknown" && disableMutationState !== "recoverable" && disableMutationState !== "success";
  const showContinueDisable = lifecycleReady && supportedRole && lifecycleStateForRow.recovery.recoveryState === "recoverable" && lifecycleStateForRow.recovery.operation === "disable" && disableMutationState !== "submitting";
  const showFreshReactivate = lifecycleReady && isFreshReactivateEligible(row, lifecycleStateForRow.eligibility) && supportedRole && reactivateEligible && isFreshReactivateRecoveryCompatible(lifecycleStateForRow.recovery) && reactivateMutationState !== "submitting" && reactivateMutationState !== "unknown" && reactivateMutationState !== "success";
  const showContinueReactivate = lifecycleReady && isFreshReactivateTarget(row) && supportedRole && lifecycleStateForRow.recovery.recoveryState === "recoverable" && lifecycleStateForRow.recovery.operation === "reactivate" && reactivateMutationState !== "submitting";
  const openDisableConfirmation = () => {
    if (!showFreshDisable) return;
    confirmationContinueRef.current = false;
    confirmationOperationRef.current = "disable";
    setConfirmationOperation("disable");
    setDisableConfirmationOpen(true);
    setDisableMutationState(disableMutationState === "retryable" ? "retryable" : "confirming");
  };
  const openContinueConfirmation = () => {
    if (!showContinueDisable) return;
    confirmationContinueRef.current = true;
    confirmationOperationRef.current = "disable";
    setConfirmationOperation("disable");
    setDisableConfirmationOpen(true);
    setDisableMutationState("recoverable");
  };
  const openReactivateConfirmation = () => {
    if (!showFreshReactivate) return;
    confirmationContinueRef.current = false;
    confirmationOperationRef.current = "reactivate";
    setConfirmationOperation("reactivate");
    setDisableConfirmationOpen(true);
    setReactivateMutationState(reactivateMutationState === "retryable" ? "retryable" : "confirming");
  };
  const openContinueReactivateConfirmation = () => {
    if (!showContinueReactivate) return;
    confirmationContinueRef.current = true;
    confirmationOperationRef.current = "reactivate";
    setConfirmationOperation("reactivate");
    setDisableConfirmationOpen(true);
    setReactivateMutationState("recoverable");
  };
  const checkRecoveryStatus = (operation: "disable" | "reactivate" = "disable") => {
    if (recoveryStatusInFlightRef.current) return;
    recoveryStatusInFlightRef.current = true;
    if (operation === "disable") {
      unknownOutcomeRef.current = true;
      resolvedUnknownRef.current = false;
    } else {
      reactivateUnknownOutcomeRef.current = true;
      reactivateResolvedUnknownRef.current = false;
    }
    setLifecycleRetryNonce((value) => value + 1);
  };

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
        if (confirmationOpenRef.current) {
          confirmationContinueRef.current = false;
          setDisableConfirmationOpen(false);
          setConfirmationOperation("disable");
          queueMicrotask(() => (confirmationOperationRef.current === "reactivate" ? reactivateButtonRef : disableButtonRef).current?.focus());
        } else {
          onClose();
        }
        return;
      }
      if (event.key !== "Tab") return;
      const trapContainer = confirmationOpenRef.current && confirmationDialogRef.current
        ? confirmationDialogRef.current
        : dialog;
      const focusable = focusableElements(trapContainer);
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

  useEffect(() => {
    if (!disableConfirmationOpen) return;
    confirmationCancelRef.current?.focus();
  }, [disableConfirmationOpen]);

  const confirmationIsReactivate = confirmationOperation === "reactivate";

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
            <div><dt>{t("adminDirectoryStatus")}</dt><dd><span className={`admin-status-chip ${row.accountState === "active" ? "is-active" : row.accountState === "disabled" ? "is-disabled" : row.accountState === "inactive_unverified" ? "is-unverified" : "is-pending"}`}>{accountStateLabel}</span></dd></div>
          </dl>
          <section className="admin-account-detail-explanation" aria-labelledby="admin-account-detail-explanation-title">
            <h3 id="admin-account-detail-explanation-title">{t("adminAccountDetailStatusTitle")}</h3>
            <p>{explanation}</p>
            {row.accountState === "pending_setup" && (row.role === "staff" || row.role === "manager") ? <p>{t("adminDirectoryOwnerNotice")}</p> : null}
            <p>{accountStateExplanation}</p>
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
              {showFreshDisable ? <button ref={disableButtonRef} className="admin-danger-button" type="button" onClick={openDisableConfirmation}>{disableMutationState === "retryable" ? t("adminDisableRetry") : t("adminDisableAccount")}</button> : null}
              {showContinueDisable ? <button ref={disableButtonRef} className="admin-secondary-button" type="button" onClick={openContinueConfirmation}>{t("adminContinueDisable")}</button> : null}
              {showFreshReactivate ? <button ref={reactivateButtonRef} className="admin-secondary-button" type="button" onClick={openReactivateConfirmation}>{reactivateMutationState === "retryable" ? t("adminReactivateRetry") : t("adminReactivateAccount")}</button> : null}
              {showContinueReactivate ? <button ref={reactivateButtonRef} className="admin-secondary-button" type="button" onClick={openContinueReactivateConfirmation}>{t("adminContinueReactivate")}</button> : null}
              {lifecycleStateForRow.recovery.recoveryState === "recoverable" ? <section className="admin-lifecycle-recovery" aria-labelledby="admin-lifecycle-recovery-title"><h4 id="admin-lifecycle-recovery-title">{t("adminLifecycleRecoveryTitle")}</h4><p>{t("adminLifecycleRecoverableMessage")}</p><p>{operationLabel(t, lifecycleStateForRow.recovery.operation as AdminLifecycleRecoveryOperation)}{lifecycleStateForRow.recovery.operation === "reassign_department" && lifecycleStateForRow.recovery.departmentId ? `: ${getDepartmentLabel(lifecycleStateForRow.recovery.departmentId, locale)}` : ""}</p></section> : null}
              {lifecycleStateForRow.recovery.recoveryState === "completed" ? <section className="admin-lifecycle-recovery" aria-labelledby="admin-lifecycle-recovery-title"><h4 id="admin-lifecycle-recovery-title">{t("adminLifecycleRecoveryTitle")}</h4><p>{t("adminLifecycleCompletedMessage")}</p><p>{operationLabel(t, lifecycleStateForRow.recovery.operation as AdminLifecycleRecoveryOperation)}{lifecycleStateForRow.recovery.operation === "reassign_department" && lifecycleStateForRow.recovery.departmentId ? `: ${getDepartmentLabel(lifecycleStateForRow.recovery.departmentId, locale)}` : ""}</p></section> : null}
              {lifecycleStateForRow.recovery.recoveryState === "operator_required" ? <section className="admin-lifecycle-recovery" aria-labelledby="admin-lifecycle-recovery-title"><h4 id="admin-lifecycle-recovery-title">{t("adminLifecycleRecoveryTitle")}</h4><p>{t("adminLifecycleOperatorRequired")}</p></section> : null}
            </> : null}
            {disableMessage === "success" ? <p className="admin-lifecycle-status admin-lifecycle-success" role="status">{t("adminDisableSuccess")}</p> : null}
            {disableMutationState === "submitting" ? <p className="admin-lifecycle-status" role="status" aria-live="polite">{t("adminDisableSubmitting")}</p> : null}
            {disableMessage === "unknown" ? <div className="admin-lifecycle-status" role="alert"><p>{t("adminDisableUnknownOutcome")}</p><button className="admin-secondary-button" type="button" onClick={() => checkRecoveryStatus("disable")}>{t("adminDisableCheckStatus")}</button></div> : null}
            {disableMessage === "error" ? <p className="admin-lifecycle-status" role="alert">{t("adminDisableSafeError")}</p> : null}
            {reactivateMessage === "success" ? <p className="admin-lifecycle-status admin-lifecycle-success" role="status">{t("adminReactivateSuccess")}</p> : null}
            {reactivateMutationState === "submitting" ? <p className="admin-lifecycle-status" role="status" aria-live="polite">{t("adminReactivateSubmitting")}</p> : null}
            {reactivateMessage === "unknown" ? <div className="admin-lifecycle-status" role="alert"><p>{t("adminReactivateUnknownOutcome")}</p><button className="admin-secondary-button" type="button" onClick={() => checkRecoveryStatus("reactivate")}>{t("adminReactivateCheckStatus")}</button></div> : null}
            {reactivateMessage === "error" ? <p className="admin-lifecycle-status" role="alert">{t("adminReactivateSafeError")}</p> : null}
          </section>
        </div>
        {disableConfirmationOpen ? <div className="admin-disable-confirmation-layer">
          <button className="admin-disable-confirmation-backdrop" type="button" aria-label={t(confirmationIsReactivate ? "adminReactivateCancel" : "adminDisableCancel")} onClick={() => { const operation = confirmationOperationRef.current; confirmationContinueRef.current = false; setDisableConfirmationOpen(false); setConfirmationOperation("disable"); (operation === "reactivate" ? reactivateButtonRef : disableButtonRef).current?.focus(); }} />
          <div ref={confirmationDialogRef} className="admin-disable-confirmation" role="alertdialog" aria-modal="true" aria-labelledby="admin-disable-confirmation-title" aria-describedby="admin-disable-confirmation-body" tabIndex={-1}>
            <h3 id="admin-disable-confirmation-title">{t(confirmationIsReactivate ? "adminReactivateConfirmationTitle" : "adminDisableConfirmationTitle")}</h3>
            <p id="admin-disable-confirmation-body">{t(confirmationIsReactivate ? "adminReactivateConfirmationBody" : "adminDisableConfirmationBody")}</p>
            <div className="admin-dialog-actions">
              <button ref={confirmationCancelRef} className="admin-secondary-button" type="button" onClick={() => { const operation = confirmationOperationRef.current; confirmationContinueRef.current = false; setDisableConfirmationOpen(false); setConfirmationOperation("disable"); (operation === "reactivate" ? reactivateButtonRef : disableButtonRef).current?.focus(); }}>{t(confirmationIsReactivate ? "adminReactivateCancel" : "adminDisableCancel")}</button>
              <button className={confirmationIsReactivate ? "admin-secondary-button" : "admin-danger-button"} type="button" onClick={() => { const operation = confirmationOperationRef.current; const continueExisting = confirmationContinueRef.current; confirmationContinueRef.current = false; setDisableConfirmationOpen(false); setConfirmationOperation("disable"); if (operation === "reactivate") submitReactivate(continueExisting); else submitDisable(continueExisting); }}>{t(confirmationIsReactivate ? "adminReactivateConfirm" : "adminDisableConfirm")}</button>
            </div>
          </div>
        </div> : null}
      </div>
    </div>
  );

  return typeof document === "undefined" ? content : createPortal(content, document.body);
}
