"use client";

import type { AdminDirectoryRow } from "@/lib/admin-directory";
import { useApp } from "@/components/app-provider";

export type AdminOverviewSnapshot =
  | { state: "loading" | "error" | "empty"; rows: AdminDirectoryRow[] }
  | { state: "ready"; rows: AdminDirectoryRow[] };

function countRows(rows: AdminDirectoryRow[]) {
  return {
    total: rows.length,
    customer: rows.filter((row) => row.role === "customer").length,
    staff: rows.filter((row) => row.role === "staff").length,
    manager: rows.filter((row) => row.role === "manager").length,
    admin: rows.filter((row) => row.role === "admin").length,
    active: rows.filter((row) => row.active).length,
    pending: rows.filter((row) => row.accountState === "pending_setup").length,
    disabled: rows.filter((row) => row.accountState === "disabled").length,
    inactiveUnavailable: rows.filter((row) => row.accountState === "inactive_unverified").length,
  };
}

export function AdminOverview({ snapshot }: { snapshot: AdminOverviewSnapshot }) {
  const { t } = useApp();
  const counts = countRows(snapshot.rows);
  return (
    <section className="admin-overview-card" aria-labelledby="admin-overview-title">
      <div className="admin-section-heading">
        <div>
          <p className="admin-section-eyebrow">{t("adminOverviewEyebrow")}</p>
          <h2 id="admin-overview-title">{t("adminOverviewTitle")}</h2>
          <p>{t("adminOverviewLead")}</p>
        </div>
        <span className="admin-scope-note">{t("adminDirectoryVisibleCounts")}</span>
      </div>
      {snapshot.state === "loading" ? <p className="admin-inline-status" role="status">{t("adminOverviewLoading")}</p> : null}
      {snapshot.state === "error" ? <p className="admin-inline-status admin-inline-error" role="alert">{t("adminOverviewError")}</p> : null}
      {snapshot.state === "empty" ? <p className="admin-inline-status">{t("adminOverviewEmpty")}</p> : null}
      {snapshot.state === "ready" && snapshot.rows.length > 0 ? (
        <div className="admin-metric-grid" aria-label={t("adminOverviewTitle")}>
          <div className="admin-metric-card"><span>{t("adminOverviewTotal")}</span><strong>{counts.total}</strong></div>
          <div className="admin-metric-card"><span>{t("adminOverviewCustomer")}</span><strong>{counts.customer}</strong></div>
          <div className="admin-metric-card"><span>{t("adminOverviewStaff")}</span><strong>{counts.staff}</strong></div>
          <div className="admin-metric-card"><span>{t("adminOverviewManager")}</span><strong>{counts.manager}</strong></div>
          <div className="admin-metric-card"><span>{t("adminOverviewAdmin")}</span><strong>{counts.admin}</strong></div>
          <div className="admin-metric-card"><span>{t("adminOverviewActive")}</span><strong>{counts.active}</strong></div>
          <div className="admin-metric-card"><span>{t("adminOverviewPending")}</span><strong>{counts.pending}</strong></div>
          <div className="admin-metric-card"><span>{t("adminOverviewDisabled")}</span><strong>{counts.disabled}</strong></div>
          <div className="admin-metric-card"><span>{t("adminOverviewInactiveUnavailable")}</span><strong>{counts.inactiveUnavailable}</strong></div>
        </div>
      ) : null}
    </section>
  );
}
