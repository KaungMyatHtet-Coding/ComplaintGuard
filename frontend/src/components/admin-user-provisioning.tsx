"use client";

import { useEffect, useRef, useState } from "react";

import { useApp } from "@/components/app-provider";
import { AdminOverview, type AdminOverviewSnapshot } from "@/components/admin-overview";
import { AdminUserDirectory } from "@/components/admin-user-directory";
import {
  createIdempotencyKey,
  provisionAdminUser,
  validateAdminProvisioningForm,
  type AdminProvisioningErrorCode,
  type AdminProvisioningFormInput,
  type AdminProvisioningResponse,
} from "@/lib/admin-provisioning";
import { departmentIds, getDepartmentLabel, type DepartmentId } from "@/lib/department-labels";
import type { Locale } from "@/lib/i18n";

const emptyForm: AdminProvisioningFormInput = {
  email: "",
  displayName: "",
  locale: "en",
  role: "staff",
  departmentId: null,
};

function fieldError(form: AdminProvisioningFormInput, field: keyof AdminProvisioningFormInput): string | null {
  if (field === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(form.email.trim())) return "adminInvalidEmail";
  if (field === "displayName" && !form.displayName.trim()) return "adminDisplayNameRequired";
  if (field === "displayName" && form.displayName.trim().length > 100) return "adminDisplayNameTooLong";
  if (field === "departmentId" && form.role === "staff" && !form.departmentId) return "adminDepartmentRequired";
  return null;
}
const errorMessages: Record<AdminProvisioningErrorCode, "adminAuthenticationError" | "adminPermissionError" | "adminEmailExists" | "adminProfileConflict" | "adminIdempotencyConflict" | "adminProvisioningIncomplete" | "adminValidationError" | "adminUnavailable" | "adminUnexpectedError"> = {
  authentication: "adminAuthenticationError",
  permission: "adminPermissionError",
  email_exists: "adminEmailExists",
  profile_conflict: "adminProfileConflict",
  idempotency_conflict: "adminIdempotencyConflict",
  provisioning_incomplete: "adminProvisioningIncomplete",
  validation: "adminValidationError",
  unavailable: "adminUnavailable",
  unexpected: "adminUnexpectedError",
};

export function AdminUserProvisioning() {
  const { locale, t } = useApp();
  const [form, setForm] = useState<AdminProvisioningFormInput>({ ...emptyForm, locale });
  const [confirmed, setConfirmed] = useState<AdminProvisioningFormInput | null>(null);
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<AdminProvisioningErrorCode | null>(null);
  const [success, setSuccess] = useState<AdminProvisioningResponse | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [directoryRefreshKey, setDirectoryRefreshKey] = useState(0);
  const [directorySnapshot, setDirectorySnapshot] = useState<AdminOverviewSnapshot>({ state: "loading", rows: [] });
  const errorSummaryRef = useRef<HTMLDivElement>(null);
  const reviewHeadingRef = useRef<HTMLHeadingElement>(null);
  const formHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (errorCode) errorSummaryRef.current?.focus();
  }, [errorCode]);

  useEffect(() => {
    if (confirmed) reviewHeadingRef.current?.focus();
  }, [confirmed]);

  function updateForm(next: Partial<AdminProvisioningFormInput>) {
    setForm((current) => ({ ...current, ...next }));
    setConfirmed(null);
    setIdempotencyKey(null);
    setErrorCode(null);
    setSuccess(null);
  }

  function review(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const checked = validateAdminProvisioningForm(form);
      setForm(checked);
      setConfirmed(checked);
      setIdempotencyKey(createIdempotencyKey());
      setErrorCode(null);
    } catch {
      setConfirmed(null);
      setIdempotencyKey(null);
      setErrorCode("validation");
    }
  }

  async function submitConfirmed() {
    if (!confirmed || !idempotencyKey || submitting) return;
    setSubmitting(true);
    setErrorCode(null);
    try {
      const result = await provisionAdminUser({ ...confirmed, idempotencyKey });
      setSuccess(result);
      setDirectoryRefreshKey((value) => value + 1);
      setForm({ ...emptyForm, locale: confirmed.locale });
      setConfirmed(null);
      setIdempotencyKey(null);
    } catch (error) {
      setErrorCode(
        error && typeof error === "object" && "code" in error
          ? (error as { code: AdminProvisioningErrorCode }).code
          : "unexpected",
      );
    } finally {
      setSubmitting(false);
    }
  }

  const displayError = errorCode ? t(errorMessages[errorCode]) : null;
  const roleLabel = (role: "staff" | "manager") =>
    role === "staff" ? t("adminStaff") : t("adminManager");
  const departmentLabel = (departmentId: DepartmentId | null, language: Locale) =>
    departmentId ? getDepartmentLabel(departmentId, language) ?? t("adminNotSelected") : t("adminNotApplicable");

  return (
    <div className="admin-workspace-stack">
      <AdminOverview snapshot={directorySnapshot} />
      <section id="admin-provisioning" className="admin-provisioning-card" aria-labelledby="admin-provisioning-title">
      <div className="admin-section-heading">
        <div>
          <p className="admin-section-eyebrow">{t("adminWorkspaceEyebrow")}</p>
          <h2 ref={formHeadingRef} id="admin-provisioning-title" tabIndex={-1}>{t("adminWorkspaceTitle")}</h2>
          <p>{t("adminWorkspaceLead")}</p>
        </div>
      </div>
      <div className="admin-policy-note">
        <p>{t("adminPendingExplanation")}</p>
        <p className="mt-2">{t("adminOwnerActivationNotice")}</p>
      </div>

      {displayError ? (
        <div ref={errorSummaryRef} tabIndex={-1} role="alert" className="mt-5 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p className="font-semibold">{t("adminErrorSummary")}</p>
          <p className="mt-1">{displayError}</p>
        </div>
      ) : null}

      {success ? (
        <div className="admin-success-panel" role="status" aria-live="polite">
          <h2 className="font-semibold">{t("adminPendingSuccess")}</h2>
          <dl className="mt-3 grid gap-2 sm:grid-cols-2">
            <div><dt className="font-medium">{t("adminRole")}</dt><dd>{roleLabel(success.role)}</dd></div>
            <div><dt className="font-medium">{t("adminDepartment")}</dt><dd>{departmentLabel(success.departmentId, success.locale)}</dd></div>
            <div><dt className="font-medium">{t("adminEmail")}</dt><dd className="break-words">{success.email}</dd></div>
            <div><dt className="font-medium">{t("adminDisplayName")}</dt><dd>{success.displayName}</dd></div>
          </dl>
          <p className="mt-3">{t("adminSuccessActivation")}</p>
        </div>
      ) : null}

      {!confirmed ? (
        <form className="admin-form-grid" onSubmit={review} noValidate>
          <div className="admin-form-field">
            <label className="field-label" htmlFor="admin-role">{t("adminRole")}</label>
            <select id="admin-role" className="admin-field-input" value={form.role} onChange={(event) => updateForm({ role: event.target.value as "staff" | "manager", departmentId: null })} aria-describedby="admin-role-help">
              <option value="staff">{t("adminStaff")}</option>
              <option value="manager">{t("adminManager")}</option>
            </select>
            <p id="admin-role-help" className="field-help">{form.role === "staff" ? t("adminStaffDescription") : t("adminManagerDescription")}</p>
          </div>
          <div className="admin-form-field">
            <label className="field-label" htmlFor="admin-email">{t("adminEmail")}</label>
            <input id="admin-email" className="admin-field-input" type="email" autoComplete="email" value={form.email} onChange={(event) => updateForm({ email: event.target.value })} aria-invalid={Boolean(fieldError(form, "email"))} aria-describedby="admin-email-error" required />
            <p id="admin-email-error" className="field-error">{fieldError(form, "email") ? t(fieldError(form, "email") as never) : ""}</p>
          </div>
          <div className="admin-form-field">
            <label className="field-label" htmlFor="admin-display-name">{t("adminDisplayName")}</label>
            <input id="admin-display-name" className="admin-field-input" type="text" autoComplete="name" value={form.displayName} onChange={(event) => updateForm({ displayName: event.target.value })} aria-invalid={Boolean(fieldError(form, "displayName"))} aria-describedby="admin-display-name-error" required />
            <p id="admin-display-name-error" className="field-error">{fieldError(form, "displayName") ? t(fieldError(form, "displayName") as never) : ""}</p>
          </div>
          <div className="admin-form-field">
            <label className="field-label" htmlFor="admin-locale">{t("adminLocale")}</label>
            <select id="admin-locale" className="admin-field-input" value={form.locale} onChange={(event) => updateForm({ locale: event.target.value as Locale })}>
              <option value="en">{t("english")}</option>
              <option value="my">{t("myanmar")}</option>
            </select>
          </div>
          {form.role === "staff" ? (
            <div className="admin-form-field">
              <label className="field-label" htmlFor="admin-department">{t("adminDepartment")}</label>
              <select id="admin-department" className="admin-field-input" value={form.departmentId ?? ""} onChange={(event) => updateForm({ departmentId: event.target.value as DepartmentId })} aria-invalid={Boolean(fieldError(form, "departmentId"))} aria-describedby="admin-department-error" required>
                <option value="">{t("adminChooseDepartment")}</option>
                {departmentIds.map((departmentId) => <option key={departmentId} value={departmentId}>{getDepartmentLabel(departmentId, locale)}</option>)}
              </select>
              <p id="admin-department-error" className="field-error">{fieldError(form, "departmentId") ? t("adminDepartmentRequired") : ""}</p>
            </div>
          ) : null}
          <button className="admin-primary-button" type="submit">{t("adminReview")}</button>
        </form>
      ) : (
        <div className="admin-review-card">
          <h3 ref={reviewHeadingRef} tabIndex={-1}>{t("adminConfirmationTitle")}</h3>
          <p>{t("adminConfirmationLead")}</p>
          <dl className="admin-review-grid">
            <div><dt className="font-medium text-gray-500">{t("adminRole")}</dt><dd>{roleLabel(confirmed.role)}</dd></div>
            <div><dt className="font-medium text-gray-500">{t("adminDepartment")}</dt><dd>{departmentLabel(confirmed.departmentId, confirmed.locale)}</dd></div>
            <div><dt className="font-medium text-gray-500">{t("adminEmail")}</dt><dd className="break-words">{confirmed.email}</dd></div>
            <div><dt className="font-medium text-gray-500">{t("adminDisplayName")}</dt><dd>{confirmed.displayName}</dd></div>
          </dl>
          <p>{t("adminConfirmationNotice")}</p>
          <div className="admin-review-actions">
            <button className="admin-secondary-button" type="button" onClick={() => { setConfirmed(null); setIdempotencyKey(null); requestAnimationFrame(() => formHeadingRef.current?.focus()); }}>{t("adminEdit")}</button>
            <button className="admin-primary-button" type="button" onClick={() => void submitConfirmed()} disabled={submitting} aria-busy={submitting}>
              {submitting ? t("adminSubmitting") : t("adminConfirm")}
            </button>
          </div>
        </div>
      )}
      </section>
      <div id="admin-directory"><AdminUserDirectory refreshKey={directoryRefreshKey} onSummaryChange={setDirectorySnapshot} /></div>
    </div>
  );
}
