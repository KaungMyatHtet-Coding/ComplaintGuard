"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import { useApp } from "@/components/app-provider";
import { AdminAccountDetail } from "@/components/admin-account-detail";
import type { AdminOverviewSnapshot } from "@/components/admin-overview";
import { departmentIds, getDepartmentLabel, type DepartmentId } from "@/lib/department-labels";
import {
  loadAdminDirectory,
  type AdminDirectoryErrorCode,
  type AdminDirectoryFilters,
  type AdminDirectoryRole,
  type AdminDirectoryResponse,
} from "@/lib/admin-directory";

export function shouldApplyDirectoryResponse(requestId: number, latestRequestId: number): boolean {
  return requestId === latestRequestId;
}

export function shouldShowOwnerActivationNotice(row: AdminDirectoryResponse["rows"][number]): boolean {
  return row.accountState === "pending_setup" && (row.role === "staff" || row.role === "manager");
}

const accountStateLabelKeys = {
  active: "adminDirectoryState_active",
  pending_setup: "adminDirectoryState_pending_setup",
  disabled: "adminDirectoryState_disabled",
  inactive_unverified: "adminDirectoryState_inactive_unverified",
} as const;

const errorMessages: Record<AdminDirectoryErrorCode, "adminDirectoryAuthentication" | "adminDirectoryPermission" | "adminDirectoryValidation" | "adminDirectoryUnavailable" | "adminDirectoryUnexpected"> = {
  authentication: "adminDirectoryAuthentication",
  permission: "adminDirectoryPermission",
  validation: "adminDirectoryValidation",
  notFound: "adminDirectoryUnexpected",
  unavailable: "adminDirectoryUnavailable",
  unexpected: "adminDirectoryUnexpected",
};

export function reconciliationMarkerKey(adminUid: string | undefined, accountRef: string): string | null {
  return adminUid ? `${adminUid}:${accountRef}` : null;
}

export function reconcileConfirmedDepartment(
  row: AdminDirectoryResponse["rows"][number],
  accountRef: string,
  departmentId: DepartmentId,
): AdminDirectoryResponse["rows"][number] {
  return row.accountRef === accountRef && row.role === "staff" ? { ...row, departmentId } : row;
}

export function AdminUserDirectory({ refreshKey = 0, onSummaryChange }: { refreshKey?: number; onSummaryChange?: (snapshot: AdminOverviewSnapshot) => void }) {
  const { locale, profile, t } = useApp();
  const [role, setRole] = useState<"" | AdminDirectoryRole>("");
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
  const previousRefreshKeyRef = useRef(refreshKey);
  const previousAdminUidRef = useRef(profile?.uid);
  const detailOpenerRef = useRef<HTMLButtonElement | null>(null);
  const directoryHeadingRef = useRef<HTMLElement | null>(null);
  const focusRestoreAllowedRef = useRef(false);
  const preserveDetailOnRefreshFailureRef = useRef(false);
  const confirmedDisabledAccountRefsRef = useRef(new Set<string>());
  const confirmedActiveAccountRefsRef = useRef(new Set<string>());
  const confirmedDepartmentRefsRef = useRef(new Map<string, DepartmentId>());
  const [selectedOwnerUid, setSelectedOwnerUid] = useState<string | undefined>(profile?.uid);
  const [selectedRow, setSelectedRow] = useState<AdminDirectoryResponse["rows"][number] | null>(null);

  const isAdmin = profile?.role === "admin" && profile.active === true && profile.departmentId === null;

  useLayoutEffect(() => {
    if (previousAdminUidRef.current !== profile?.uid || !isAdmin) {
      focusRestoreAllowedRef.current = false;
      detailOpenerRef.current = null;
    }
  }, [isAdmin, profile?.uid]);

  useEffect(() => {
    if (previousAdminUidRef.current !== profile?.uid || !isAdmin) {
      previousAdminUidRef.current = profile?.uid;
      confirmedDisabledAccountRefsRef.current.clear();
      confirmedActiveAccountRefsRef.current.clear();
      confirmedDepartmentRefsRef.current.clear();
      queueMicrotask(() => {
        setSelectedOwnerUid(undefined);
        setSelectedRow(null);
      });
    }
  }, [isAdmin, profile?.uid]);

  useEffect(() => {
    const requestId = ++requestIdRef.current;
    if (!isAdmin) {
      confirmedDisabledAccountRefsRef.current.clear();
      confirmedActiveAccountRefsRef.current.clear();
      confirmedDepartmentRefsRef.current.clear();
      focusRestoreAllowedRef.current = false;
      onSummaryChange?.({ state: "empty", rows: [] });
      return;
    }
    if (previousRefreshKeyRef.current !== refreshKey) {
      previousRefreshKeyRef.current = refreshKey;
      setCursor(undefined);
      setHistory([]);
      setResult(null);
      focusRestoreAllowedRef.current = true;
      setSelectedRow(null);
      summaryRowsRef.current = [];
      return;
    }
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
          const reconciledRows = nextResult.rows.map((row) => {
            const markerKey = reconciliationMarkerKey(profile?.uid, row.accountRef);
            const confirmedDepartment = markerKey ? confirmedDepartmentRefsRef.current.get(markerKey) : undefined;
            if (confirmedDepartment) {
              if (row.role === "staff" && row.departmentId === confirmedDepartment) {
                confirmedDepartmentRefsRef.current.delete(markerKey as string);
                return row;
              }
              if (row.role === "staff") return { ...row, departmentId: confirmedDepartment };
            }
            if (markerKey && confirmedActiveAccountRefsRef.current.has(markerKey)) {
              if (row.active && row.accountState === "active") {
                confirmedActiveAccountRefsRef.current.delete(markerKey);
                return row;
              }
              return { ...row, active: true, accountState: "active" as const };
            }
            if (!markerKey || !confirmedDisabledAccountRefsRef.current.has(markerKey)) return row;
            if (row.active && row.accountState === "active") {
              confirmedDisabledAccountRefsRef.current.delete(markerKey);
              return row;
            }
            return { ...row, active: false, accountState: "disabled" as const };
          });
          const reconciledResult = { ...nextResult, rows: reconciledRows };
          setResult(reconciledResult);
          preserveDetailOnRefreshFailureRef.current = false;
          setSelectedRow((current) => {
            if (!current) return null;
            const refreshedRow = reconciledRows.find((row) => row.accountRef === current.accountRef);
            if (!refreshedRow) focusRestoreAllowedRef.current = true;
            return refreshedRow ?? null;
          });
          const mergedRows = new Map(summaryRowsRef.current.map((row) => [row.accountRef, row]));
          reconciledRows.forEach((row) => mergedRows.set(row.accountRef, row));
          summaryRowsRef.current = Array.from(mergedRows.values());
          onSummaryChange?.({ state: summaryRowsRef.current.length ? "ready" : "empty", rows: summaryRowsRef.current });
        }
      } catch (error: unknown) {
        if (!shouldApplyDirectoryResponse(requestId, requestIdRef.current)) return;
        focusRestoreAllowedRef.current = true;
        if (!preserveDetailOnRefreshFailureRef.current) setSelectedRow(null);
        preserveDetailOnRefreshFailureRef.current = false;
        setErrorCode(error && typeof error === "object" && "code" in error ? (error as { code: AdminDirectoryErrorCode }).code : "unexpected");
        onSummaryChange?.({ state: "error", rows: [] });
      } finally {
        if (shouldApplyDirectoryResponse(requestId, requestIdRef.current)) setLoading(false);
      }
    })();
  }, [active, cursor, departmentId, isAdmin, onSummaryChange, profile?.uid, refreshKey, retryNonce, role, search]);

  function resetPaging() {
    setCursor(undefined);
    setHistory([]);
    setResult(null);
    summaryRowsRef.current = [];
    focusRestoreAllowedRef.current = true;
    setSelectedRow(null);
  }

  function changeRole(value: "" | AdminDirectoryRole) {
    setRole(value);
    if (value !== "" && value !== "staff") setDepartmentId("");
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

  function openDetails(event: React.MouseEvent<HTMLButtonElement>, row: AdminDirectoryResponse["rows"][number]) {
    detailOpenerRef.current = event.currentTarget;
    focusRestoreAllowedRef.current = true;
    setSelectedOwnerUid(profile?.uid);
    setSelectedRow(row);
  }

  const closeDetails = useCallback(() => {
    setSelectedOwnerUid(undefined);
    setSelectedRow(null);
  }, []);
  const canRestoreDetailFocus = useCallback(() => focusRestoreAllowedRef.current, []);
  const refreshDirectory = useCallback(() => {
    preserveDetailOnRefreshFailureRef.current = true;
    setRetryNonce((value) => value + 1);
  }, []);
  const handleLifecycleSuccess = useCallback((accountRef: string, operation: "disable" | "reactivate" | "reassign_department" = "disable", departmentId?: DepartmentId) => {
    const markerKey = reconciliationMarkerKey(profile?.uid, accountRef);
    if (!markerKey) return;
    if (operation === "reassign_department") {
      if (!departmentId) return;
      confirmedDepartmentRefsRef.current.set(markerKey, departmentId);
      const reconcileDepartment = (row: AdminDirectoryResponse["rows"][number]) => reconcileConfirmedDepartment(row, accountRef, departmentId);
      setResult((current) => current ? { ...current, rows: current.rows.map(reconcileDepartment) } : current);
      summaryRowsRef.current = summaryRowsRef.current.map(reconcileDepartment);
      setSelectedRow((current) => current?.accountRef === accountRef ? reconcileDepartment(current) : current);
      refreshDirectory();
      return;
    }
    const reactivate = operation === "reactivate";
    if (reactivate) {
      confirmedActiveAccountRefsRef.current.add(markerKey);
      confirmedDisabledAccountRefsRef.current.delete(markerKey);
    } else {
      confirmedDisabledAccountRefsRef.current.add(markerKey);
      confirmedActiveAccountRefsRef.current.delete(markerKey);
    }
    const reconcile = (row: AdminDirectoryResponse["rows"][number]) => row.accountRef === accountRef
      ? reactivate ? { ...row, active: true, accountState: "active" as const } : { ...row, active: false, accountState: "disabled" as const }
      : row;
    setResult((current) => current ? { ...current, rows: current.rows.map(reconcile) } : current);
    summaryRowsRef.current = summaryRowsRef.current.map(reconcile);
    setSelectedRow((current) => current?.accountRef === accountRef ? reconcile(current) : current);
    refreshDirectory();
  }, [profile?.uid, refreshDirectory]);

  if (!isAdmin) return null;

  const activeSelectedRow = selectedOwnerUid === profile?.uid ? selectedRow : null;

  const displayError = errorCode ? t(errorMessages[errorCode]) : null;
  const roleLabel = (value: AdminDirectoryRole) => {
    if (value === "customer") return t("adminCustomer");
    if (value === "staff") return t("adminStaff");
    if (value === "manager") return t("adminManager");
    return t("adminRoleAdmin");
  };

  return (
    <section className="admin-directory-card" aria-labelledby="admin-directory-title">
      <div className="admin-section-heading">
        <div>
          <p className="admin-section-eyebrow">{t("adminDirectoryEyebrow")}</p>
          <h2 id="admin-directory-title" tabIndex={-1} ref={(node) => { directoryHeadingRef.current = node; }}>{t("adminDirectoryTitle")}</h2>
          <p>{t("adminDirectoryLead")}</p>
        </div>
        <button className="admin-secondary-button" type="button" onClick={() => { setRole(""); setDepartmentId(""); setActive(""); setSearch(""); resetPaging(); }}>{t("adminDirectoryReset")}</button>
      </div>
      <div className="admin-filter-toolbar" aria-label={t("adminDirectoryFilterSummary")}>
        <div className="admin-form-field"><label htmlFor="admin-directory-role">{t("adminDirectoryRoleFilter")}</label><select id="admin-directory-role" className="admin-field-input" value={role} onChange={(event) => changeRole(event.target.value as typeof role)}><option value="">{t("adminDirectoryAll")}</option><option value="customer">{t("adminCustomer")}</option><option value="staff">{t("adminStaff")}</option><option value="manager">{t("adminManager")}</option><option value="admin">{t("adminRoleAdmin")}</option></select></div>
        <div className="admin-form-field"><label htmlFor="admin-directory-department">{t("adminDirectoryDepartmentFilter")}</label><select id="admin-directory-department" className="admin-field-input" value={departmentId} disabled={role !== "" && role !== "staff"} onChange={(event) => { setDepartmentId(event.target.value as DepartmentId | ""); resetPaging(); }}><option value="">{t("adminDirectoryAll")}</option>{departmentIds.map((id) => <option key={id} value={id}>{getDepartmentLabel(id, locale)}</option>)}</select></div>
        <div className="admin-form-field"><label htmlFor="admin-directory-status">{t("adminDirectoryStatusFilter")}</label><select id="admin-directory-status" className="admin-field-input" value={active} onChange={(event) => { setActive(event.target.value as typeof active); resetPaging(); }}><option value="">{t("adminDirectoryAll")}</option><option value="true">{t("adminDirectoryActive")}</option><option value="false">{t("adminDirectoryInactive")}</option></select></div>
        <div className="admin-form-field admin-search-field"><label htmlFor="admin-directory-search">{t("adminDirectorySearch")}</label><input id="admin-directory-search" className="admin-field-input" type="search" value={search} maxLength={80} onChange={(event) => { setSearch(event.target.value); resetPaging(); }} /></div>
      </div>
      <div className="admin-directory-status" aria-live="polite">{loading ? <p role="status">{t("adminDirectoryLoading")}</p> : null}{displayError ? <div role="alert" className="admin-error-panel"><p>{displayError}</p><button className="admin-secondary-button" type="button" onClick={() => setRetryNonce((value) => value + 1)}>{t("adminDirectoryRetry")}</button></div> : null}</div>
      {!loading && !displayError && result && result.rows.length === 0 ? <p className="admin-empty-state">{t("adminDirectoryEmpty")}</p> : null}
      {result && result.rows.length > 0 ? <>
        <div className="admin-directory-table-wrap"><table className="admin-directory-table" aria-label={t("adminDirectoryTitle")}><thead><tr><th scope="col">{t("adminDirectoryName")}</th><th scope="col">{t("adminEmail")}</th><th scope="col">{t("adminRole")}</th><th scope="col">{t("adminDepartment")}</th><th scope="col">{t("adminDirectoryLanguage")}</th><th scope="col">{t("adminDirectoryStatus")}</th><th scope="col">{t("adminDirectoryActions")}</th></tr></thead><tbody>{result.rows.map((row) => <tr key={row.accountRef}><td data-label={t("adminDirectoryName")}>{row.displayName}</td><td data-label={t("adminEmail")} className="admin-break-value">{row.email}</td><td data-label={t("adminRole")}>{roleLabel(row.role)}</td><td data-label={t("adminDepartment")}>{row.departmentId ? getDepartmentLabel(row.departmentId, locale) : t("adminNotApplicable")}</td><td data-label={t("adminDirectoryLanguage")}>{row.locale === "en" ? t("english") : t("myanmar")}</td><td data-label={t("adminDirectoryStatus")}><span className={`admin-status-chip ${row.accountState === "active" ? "is-active" : row.accountState === "disabled" ? "is-disabled" : row.accountState === "inactive_unverified" ? "is-unverified" : "is-pending"}`}>{t(accountStateLabelKeys[row.accountState])}</span>{shouldShowOwnerActivationNotice(row) ? <span className="admin-status-note">{t("adminDirectoryOwnerNotice")}</span> : null}</td><td data-label={t("adminDirectoryActions")}><button className="admin-secondary-button admin-directory-view-button" type="button" onClick={(event) => openDetails(event, row)}>{t("adminDirectoryViewDetails")}</button></td></tr>)}</tbody></table></div>
        <div className="admin-directory-card-list">{result.rows.map((row) => <article className="admin-account-card" key={`${row.accountRef}-card`}><h3>{row.displayName}</h3><dl><div><dt>{t("adminEmail")}</dt><dd>{row.email}</dd></div><div><dt>{t("adminRole")}</dt><dd>{roleLabel(row.role)}</dd></div><div><dt>{t("adminDepartment")}</dt><dd>{row.departmentId ? getDepartmentLabel(row.departmentId, locale) : t("adminNotApplicable")}</dd></div><div><dt>{t("adminDirectoryLanguage")}</dt><dd>{row.locale === "en" ? t("english") : t("myanmar")}</dd></div><div><dt>{t("adminDirectoryStatus")}</dt><dd><span className={`admin-status-chip ${row.accountState === "active" ? "is-active" : row.accountState === "disabled" ? "is-disabled" : row.accountState === "inactive_unverified" ? "is-unverified" : "is-pending"}`}>{t(accountStateLabelKeys[row.accountState])}</span></dd></div></dl><button className="admin-secondary-button admin-directory-view-button" type="button" onClick={(event) => openDetails(event, row)}>{t("adminDirectoryViewDetails")}</button></article>)}</div>
      </> : null}
      <div className="admin-pagination"><button className="admin-secondary-button" type="button" onClick={previousPage} disabled={history.length === 0}>{t("adminDirectoryPrevious")}</button><button className="admin-secondary-button" type="button" onClick={nextPage} disabled={!result?.hasMore}>{t("adminDirectoryNext")}</button></div>
       {activeSelectedRow ? <AdminAccountDetail key={`${activeSelectedRow.accountRef}:${profile?.uid ?? ""}`} row={activeSelectedRow} openerRef={detailOpenerRef} fallbackRef={directoryHeadingRef} canRestoreFocus={canRestoreDetailFocus} onClose={closeDetails} onLifecycleSuccess={handleLifecycleSuccess} /> : null}
    </section>
  );

}
