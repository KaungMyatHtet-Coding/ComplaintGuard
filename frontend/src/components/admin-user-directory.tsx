"use client";

import { useEffect, useRef, useState } from "react";

import { useApp } from "@/components/app-provider";
import type { AdminOverviewSnapshot } from "@/components/admin-overview";
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

export function AdminUserDirectory({ refreshKey = 0, onSummaryChange }: { refreshKey?: number; onSummaryChange?: (snapshot: AdminOverviewSnapshot) => void }) {
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
  const summaryRowsRef = useRef<AdminDirectoryResponse["rows"]>([]);

  const isAdmin = profile?.role === "admin" && profile.active === true && profile.departmentId === null;

  useEffect(() => {
    if (!isAdmin) {
      onSummaryChange?.({ state: "empty", rows: [] });
      return;
    }
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
      if (!cursor) summaryRowsRef.current = [];
      onSummaryChange?.({ state: "loading", rows: summaryRowsRef.current });
      try {
        const nextResult = await loadAdminDirectory(filters);
        if (shouldApplyDirectoryResponse(requestId, requestIdRef.current)) {
          setResult(nextResult);
          const mergedRows = new Map(summaryRowsRef.current.map((row) => [`${row.email}|${row.role}`, row]));
          nextResult.rows.forEach((row) => mergedRows.set(`${row.email}|${row.role}`, row));
          summaryRowsRef.current = Array.from(mergedRows.values());
          onSummaryChange?.({ state: summaryRowsRef.current.length ? "ready" : "empty", rows: summaryRowsRef.current });
        }
      } catch (error: unknown) {
        if (!shouldApplyDirectoryResponse(requestId, requestIdRef.current)) return;
        setErrorCode(error && typeof error === "object" && "code" in error ? (error as { code: AdminDirectoryErrorCode }).code : "unexpected");
        onSummaryChange?.({ state: "error", rows: [] });
      } finally {
        if (shouldApplyDirectoryResponse(requestId, requestIdRef.current)) setLoading(false);
      }
    })();
  }, [active, cursor, departmentId, isAdmin, onSummaryChange, refreshKey, retryNonce, role, search]);

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
    <section className="admin-directory-card" aria-labelledby="admin-directory-title">
      <div className="admin-section-heading">
        <div>
          <p className="admin-section-eyebrow">{t("adminDirectoryEyebrow")}</p>
          <h2 id="admin-directory-title">{t("adminDirectoryTitle")}</h2>
          <p>{t("adminDirectoryLead")}</p>
        </div>
        <button className="admin-secondary-button" type="button" onClick={() => { setRole(""); setDepartmentId(""); setActive(""); setSearch(""); resetPaging(); }}>{t("adminDirectoryReset")}</button>
      </div>
      <div className="admin-filter-toolbar" aria-label={t("adminDirectoryFilterSummary")}>
        <div className="admin-form-field"><label htmlFor="admin-directory-role">{t("adminDirectoryRoleFilter")}</label><select id="admin-directory-role" className="admin-field-input" value={role} onChange={(event) => changeRole(event.target.value as typeof role)}><option value="">{t("adminDirectoryAll")}</option><option value="staff">{t("adminStaff")}</option><option value="manager">{t("adminManager")}</option></select></div>
        <div className="admin-form-field"><label htmlFor="admin-directory-department">{t("adminDirectoryDepartmentFilter")}</label><select id="admin-directory-department" className="admin-field-input" value={departmentId} disabled={role === "manager"} onChange={(event) => { setDepartmentId(event.target.value as DepartmentId | ""); resetPaging(); }}><option value="">{t("adminDirectoryAll")}</option>{departmentIds.map((id) => <option key={id} value={id}>{getDepartmentLabel(id, locale)}</option>)}</select></div>
        <div className="admin-form-field"><label htmlFor="admin-directory-status">{t("adminDirectoryStatusFilter")}</label><select id="admin-directory-status" className="admin-field-input" value={active} onChange={(event) => { setActive(event.target.value as typeof active); resetPaging(); }}><option value="">{t("adminDirectoryAll")}</option><option value="true">{t("adminDirectoryActive")}</option><option value="false">{t("adminDirectoryPending")}</option></select></div>
        <div className="admin-form-field admin-search-field"><label htmlFor="admin-directory-search">{t("adminDirectorySearch")}</label><input id="admin-directory-search" className="admin-field-input" type="search" value={search} maxLength={80} onChange={(event) => { setSearch(event.target.value); resetPaging(); }} /></div>
      </div>
      <div className="admin-directory-status" aria-live="polite">{loading ? <p role="status">{t("adminDirectoryLoading")}</p> : null}{displayError ? <div role="alert" className="admin-error-panel"><p>{displayError}</p><button className="admin-secondary-button" type="button" onClick={() => setRetryNonce((value) => value + 1)}>{t("adminDirectoryRetry")}</button></div> : null}</div>
      {!loading && !displayError && result && result.rows.length === 0 ? <p className="admin-empty-state">{t("adminDirectoryEmpty")}</p> : null}
      {result && result.rows.length > 0 ? <>
        <div className="admin-directory-table-wrap"><table className="admin-directory-table" aria-label={t("adminDirectoryTitle")}><thead><tr><th scope="col">{t("adminDirectoryName")}</th><th scope="col">{t("adminEmail")}</th><th scope="col">{t("adminRole")}</th><th scope="col">{t("adminDepartment")}</th><th scope="col">{t("adminDirectoryLanguage")}</th><th scope="col">{t("adminDirectoryStatus")}</th></tr></thead><tbody>{result.rows.map((row) => <tr key={`${row.email}-${row.role}`}><td data-label={t("adminDirectoryName")}>{row.displayName}</td><td data-label={t("adminEmail")} className="admin-break-value">{row.email}</td><td data-label={t("adminRole")}>{row.role === "staff" ? t("adminStaff") : t("adminManager")}</td><td data-label={t("adminDepartment")}>{row.departmentId ? getDepartmentLabel(row.departmentId, locale) : t("adminNotApplicable")}</td><td data-label={t("adminDirectoryLanguage")}>{row.locale === "en" ? t("english") : t("myanmar")}</td><td data-label={t("adminDirectoryStatus")}><span className={`admin-status-chip ${row.active ? "is-active" : "is-pending"}`}>{row.active ? t("adminDirectoryActive") : t("adminDirectoryPending")}</span>{!row.active ? <span className="admin-status-note">{t("adminDirectoryOwnerNotice")}</span> : null}</td></tr>)}</tbody></table></div>
        <div className="admin-directory-card-list">{result.rows.map((row) => <article className="admin-account-card" key={`${row.email}-${row.role}-card`}><h3>{row.displayName}</h3><dl><div><dt>{t("adminEmail")}</dt><dd>{row.email}</dd></div><div><dt>{t("adminRole")}</dt><dd>{row.role === "staff" ? t("adminStaff") : t("adminManager")}</dd></div><div><dt>{t("adminDepartment")}</dt><dd>{row.departmentId ? getDepartmentLabel(row.departmentId, locale) : t("adminNotApplicable")}</dd></div><div><dt>{t("adminDirectoryLanguage")}</dt><dd>{row.locale === "en" ? t("english") : t("myanmar")}</dd></div><div><dt>{t("adminDirectoryStatus")}</dt><dd><span className={`admin-status-chip ${row.active ? "is-active" : "is-pending"}`}>{row.active ? t("adminDirectoryActive") : t("adminDirectoryPending")}</span></dd></div></dl></article>)}</div>
      </> : null}
      <div className="admin-pagination"><button className="admin-secondary-button" type="button" onClick={previousPage} disabled={history.length === 0}>{t("adminDirectoryPrevious")}</button><button className="admin-secondary-button" type="button" onClick={nextPage} disabled={!result?.hasMore}>{t("adminDirectoryNext")}</button></div>
    </section>
  );

}
