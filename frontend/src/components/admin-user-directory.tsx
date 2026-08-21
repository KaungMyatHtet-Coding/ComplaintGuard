"use client";

import { useEffect, useRef, useState } from "react";

import { useApp } from "@/components/app-provider";
import { departmentIds, getDepartmentLabel, type DepartmentId } from "@/lib/department-labels";
import {
  loadAdminDirectory,
  type AdminDirectoryErrorCode,
  type AdminDirectoryFilters,
  type AdminDirectoryResponse,
} from "@/lib/admin-directory";

export function shouldApplyDirectoryResponse(requestId: number, latestRequestId: number): boolean {
  return requestId === latestRequestId;
}

const errorMessages: Record<AdminDirectoryErrorCode, "adminDirectoryAuthentication" | "adminDirectoryPermission" | "adminDirectoryValidation" | "adminDirectoryUnavailable" | "adminDirectoryUnexpected"> = {
  authentication: "adminDirectoryAuthentication",
  permission: "adminDirectoryPermission",
  validation: "adminDirectoryValidation",
  unavailable: "adminDirectoryUnavailable",
  unexpected: "adminDirectoryUnexpected",
};

export function AdminUserDirectory({ refreshKey = 0 }: { refreshKey?: number }) {
  const { locale, profile, t } = useApp();
  const [role, setRole] = useState<"" | "staff" | "manager">("");
  const [departmentId, setDepartmentId] = useState<DepartmentId | "">("");
  const [active, setActive] = useState<"" | "true" | "false">("");
  const [search, setSearch] = useState("");
  const [cursor, setCursor] = useState<string | undefined>();
  const [history, setHistory] = useState<string[]>([]);
  const [result, setResult] = useState<AdminDirectoryResponse | null>(null);
  const [errorCode, setErrorCode] = useState<AdminDirectoryErrorCode | null>(null);
  const [loading, setLoading] = useState(false);
  const [retryNonce, setRetryNonce] = useState(0);
  const requestIdRef = useRef(0);

  const isAdmin = profile?.role === "admin" && profile.active === true && profile.departmentId === null;

  useEffect(() => {
    if (!isAdmin) return;
    const requestId = ++requestIdRef.current;
    const filters: AdminDirectoryFilters = {
      ...(role ? { role } : {}),
      ...(departmentId ? { departmentId } : {}),
      ...(active ? { active: active === "true" } : {}),
      ...(search.trim() ? { search: search.trim() } : {}),
      pageSize: 10,
      ...(cursor ? { cursor } : {}),
    };
    void (async () => {
      await Promise.resolve();
      if (!shouldApplyDirectoryResponse(requestId, requestIdRef.current)) return;
      setLoading(true);
      setErrorCode(null);
      try {
        const nextResult = await loadAdminDirectory(filters);
        if (shouldApplyDirectoryResponse(requestId, requestIdRef.current)) setResult(nextResult);
      } catch (error: unknown) {
        if (!shouldApplyDirectoryResponse(requestId, requestIdRef.current)) return;
        setErrorCode(error && typeof error === "object" && "code" in error ? (error as { code: AdminDirectoryErrorCode }).code : "unexpected");
      } finally {
        if (shouldApplyDirectoryResponse(requestId, requestIdRef.current)) setLoading(false);
      }
    })();
  }, [active, cursor, departmentId, isAdmin, refreshKey, retryNonce, role, search]);

  if (!isAdmin) return null;

  function resetPaging() {
    setCursor(undefined);
    setHistory([]);
  }

  function changeRole(value: "" | "staff" | "manager") {
    setRole(value);
    if (value === "manager") setDepartmentId("");
    resetPaging();
  }

  function nextPage() {
    if (!result?.nextCursor) return;
    setHistory((current) => [...current, cursor ?? ""]);
    setCursor(result.nextCursor);
  }

  function previousPage() {
    const previous = history.at(-1);
    if (previous === undefined) return;
    setHistory((current) => current.slice(0, -1));
    setCursor(previous || undefined);
  }

  const displayError = errorCode ? t(errorMessages[errorCode]) : null;

  return (
    <section className="mt-8 w-full max-w-5xl rounded-2xl border border-gray-200 bg-white p-5 shadow-sm sm:p-8" aria-labelledby="admin-directory-title">
      <h2 id="admin-directory-title" className="text-xl font-semibold text-gray-950">{t("adminDirectoryTitle")}</h2>
      <p className="mt-2 text-sm leading-6 text-gray-600">{t("adminDirectoryLead")}</p>
      <div className="mt-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div><label className="field-label" htmlFor="admin-directory-role">{t("adminDirectoryRoleFilter")}</label><select id="admin-directory-role" className="field-input" value={role} onChange={(event) => changeRole(event.target.value as typeof role)}><option value="">{t("adminDirectoryAll")}</option><option value="staff">{t("adminStaff")}</option><option value="manager">{t("adminManager")}</option></select></div>
        <div><label className="field-label" htmlFor="admin-directory-department">{t("adminDirectoryDepartmentFilter")}</label><select id="admin-directory-department" className="field-input" value={departmentId} disabled={role === "manager"} onChange={(event) => { setDepartmentId(event.target.value as DepartmentId | ""); resetPaging(); }}><option value="">{t("adminDirectoryAll")}</option>{departmentIds.map((id) => <option key={id} value={id}>{getDepartmentLabel(id, locale)}</option>)}</select></div>
        <div><label className="field-label" htmlFor="admin-directory-status">{t("adminDirectoryStatusFilter")}</label><select id="admin-directory-status" className="field-input" value={active} onChange={(event) => { setActive(event.target.value as typeof active); resetPaging(); }}><option value="">{t("adminDirectoryAll")}</option><option value="true">{t("adminDirectoryActive")}</option><option value="false">{t("adminDirectoryPending")}</option></select></div>
        <div><label className="field-label" htmlFor="admin-directory-search">{t("adminDirectorySearch")}</label><input id="admin-directory-search" className="field-input" type="search" value={search} maxLength={80} onChange={(event) => { setSearch(event.target.value); resetPaging(); }} /></div>
      </div>
      <div className="mt-5" aria-live="polite">{loading ? <p className="text-sm text-gray-600">{t("adminDirectoryLoading")}</p> : null}{displayError ? <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800"><p>{displayError}</p><button className="secondary-button mt-3" type="button" onClick={() => setRetryNonce((value) => value + 1)}>{t("adminDirectoryRetry")}</button></div> : null}</div>
      {!loading && !displayError && result && result.rows.length === 0 ? <p className="mt-5 rounded-xl bg-gray-50 p-4 text-sm text-gray-700">{t("adminDirectoryEmpty")}</p> : null}
      {result && result.rows.length > 0 ? <div className="mt-5 overflow-x-auto"><table className="min-w-full text-left text-sm"><thead><tr className="border-b border-gray-200"><th className="px-3 py-3 font-semibold">{t("adminDirectoryName")}</th><th className="px-3 py-3 font-semibold">{t("adminEmail")}</th><th className="px-3 py-3 font-semibold">{t("adminRole")}</th><th className="px-3 py-3 font-semibold">{t("adminDepartment")}</th><th className="px-3 py-3 font-semibold">{t("adminDirectoryLanguage")}</th><th className="px-3 py-3 font-semibold">{t("adminDirectoryStatus")}</th></tr></thead><tbody>{result.rows.map((row) => <tr className="border-b border-gray-100" key={`${row.email}-${row.role}`}><td className="px-3 py-3">{row.displayName}</td><td className="px-3 py-3 break-words">{row.email}</td><td className="px-3 py-3">{row.role === "staff" ? t("adminStaff") : t("adminManager")}</td><td className="px-3 py-3">{row.departmentId ? getDepartmentLabel(row.departmentId, locale) : t("adminNotApplicable")}</td><td className="px-3 py-3">{row.locale === "en" ? t("english") : t("myanmar")}</td><td className="px-3 py-3">{row.active ? t("adminDirectoryActive") : <span>{t("adminDirectoryPending")}<span className="block text-xs text-gray-600">{t("adminDirectoryOwnerNotice")}</span></span>}</td></tr>)}</tbody></table></div> : null}
      <div className="mt-5 flex flex-wrap gap-3"><button className="secondary-button" type="button" onClick={previousPage} disabled={history.length === 0}>{t("adminDirectoryPrevious")}</button><button className="secondary-button" type="button" onClick={nextPage} disabled={!result?.hasMore}>{t("adminDirectoryNext")}</button></div>
    </section>
  );

}
