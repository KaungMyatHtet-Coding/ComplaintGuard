"use client";

import { useEffect, useRef, useState } from "react";

import { useApp } from "@/components/app-provider";
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
  const errorSummaryRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (errorCode) errorSummaryRef.current?.focus();
  }, [errorCode]);

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
    <section className="w-full max-w-3xl rounded-2xl border border-gray-200 bg-white p-5 shadow-sm sm:p-8" aria-labelledby="admin-provisioning-title">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">{t("adminWorkspaceEyebrow")}</p>
      <h1 id="admin-provisioning-title" className="mt-2 text-2xl font-semibold text-gray-950">{t("adminWorkspaceTitle")}</h1>
      <p className="mt-3 text-sm leading-6 text-gray-600">{t("adminWorkspaceLead")}</p>
      <div className="mt-4 rounded-xl bg-gray-50 p-4 text-sm leading-6 text-gray-700">
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
        <div className="mt-5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-900" role="status" aria-live="polite">
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
        <form className="mt-6 grid gap-5" onSubmit={review} noValidate>
          <div>
            <label className="field-label" htmlFor="admin-role">{t("adminRole")}</label>
            <select id="admin-role" className="field-input" value={form.role} onChange={(event) => updateForm({ role: event.target.value as "staff" | "manager", departmentId: null })}>
              <option value="staff">{t("adminStaff")}</option>
              <option value="manager">{t("adminManager")}</option>
            </select>
            <p className="field-help">{form.role === "staff" ? t("adminStaffDescription") : t("adminManagerDescription")}</p>
          </div>
          <div>
            <label className="field-label" htmlFor="admin-email">{t("adminEmail")}</label>
            <input id="admin-email" className="field-input" type="email" autoComplete="email" value={form.email} onChange={(event) => updateForm({ email: event.target.value })} aria-invalid={Boolean(fieldError(form, "email"))} />
            {fieldError(form, "email") ? <p className="field-error">{t(fieldError(form, "email") as never)}</p> : null}
          </div>
          <div>
            <label className="field-label" htmlFor="admin-display-name">{t("adminDisplayName")}</label>
            <input id="admin-display-name" className="field-input" type="text" autoComplete="name" value={form.displayName} onChange={(event) => updateForm({ displayName: event.target.value })} aria-invalid={Boolean(fieldError(form, "displayName"))} />
            {fieldError(form, "displayName") ? <p className="field-error">{t(fieldError(form, "displayName") as never)}</p> : null}
          </div>
          <div>
            <label className="field-label" htmlFor="admin-locale">{t("adminLocale")}</label>
            <select id="admin-locale" className="field-input" value={form.locale} onChange={(event) => updateForm({ locale: event.target.value as Locale })}>
              <option value="en">{t("english")}</option>
              <option value="my">{t("myanmar")}</option>
            </select>
          </div>
          {form.role === "staff" ? (
            <div>
              <label className="field-label" htmlFor="admin-department">{t("adminDepartment")}</label>
              <select id="admin-department" className="field-input" value={form.departmentId ?? ""} onChange={(event) => updateForm({ departmentId: event.target.value as DepartmentId })} aria-invalid={Boolean(fieldError(form, "departmentId"))}>
                <option value="">{t("adminChooseDepartment")}</option>
                {departmentIds.map((departmentId) => <option key={departmentId} value={departmentId}>{getDepartmentLabel(departmentId, locale)}</option>)}
              </select>
              {fieldError(form, "departmentId") ? <p className="field-error">{t("adminDepartmentRequired")}</p> : null}
            </div>
          ) : null}
          <button className="primary-button w-full sm:w-fit" type="submit">{t("adminReview")}</button>
        </form>
      ) : (
        <div className="mt-6 rounded-xl border border-gray-200 p-5">
          <h2 className="text-lg font-semibold text-gray-950">{t("adminConfirmationTitle")}</h2>
          <p className="mt-2 text-sm text-gray-600">{t("adminConfirmationLead")}</p>
          <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
            <div><dt className="font-medium text-gray-500">{t("adminRole")}</dt><dd>{roleLabel(confirmed.role)}</dd></div>
            <div><dt className="font-medium text-gray-500">{t("adminDepartment")}</dt><dd>{departmentLabel(confirmed.departmentId, confirmed.locale)}</dd></div>
            <div><dt className="font-medium text-gray-500">{t("adminEmail")}</dt><dd className="break-words">{confirmed.email}</dd></div>
            <div><dt className="font-medium text-gray-500">{t("adminDisplayName")}</dt><dd>{confirmed.displayName}</dd></div>
          </dl>
          <p className="mt-4 text-sm text-gray-600">{t("adminConfirmationNotice")}</p>
          <div className="mt-5 flex flex-wrap gap-3">
            <button className="secondary-button" type="button" onClick={() => { setConfirmed(null); setIdempotencyKey(null); }}>{t("adminEdit")}</button>
            <button className="primary-button" type="button" onClick={() => void submitConfirmed()} disabled={submitting} aria-busy={submitting}>
              {submitting ? t("adminSubmitting") : t("adminConfirm")}
            </button>
          </div>
        </div>
      )}
      <AdminUserDirectory refreshKey={directoryRefreshKey} />
    </section>
  );
}
