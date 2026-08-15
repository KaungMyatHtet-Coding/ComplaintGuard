"use client";

import { useApp } from "@/components/app-provider";
import type { ManagerAnalytics } from "@/lib/manager-workflow";

type ManagerAnalyticsOverviewProps = {
  analytics: ManagerAnalytics;
};

export function ManagerAnalyticsOverview({ analytics }: ManagerAnalyticsOverviewProps) {
  const { t } = useApp();

  return (
    <div className="cust-layout" style={{ gap: '2rem' }}>
      <header>
        <p className="eyebrow">
          {t("managerExecutiveOperations")}
        </p>
        <h2 style={{ fontSize: '1.5rem', fontWeight: 700, margin: '0.25rem 0 0 0' }}>{t("managerAnalyticsTitle")}</h2>
      </header>

      {/* KPI Cards Grid */}
      <div className="mng-kpi-grid">
        <div className="mng-kpi-card">
          <p className="mng-kpi-label">{t("managerTotalTickets")}</p>
          <p className="mng-kpi-val">{analytics.totalTickets}</p>
        </div>

        <div className="mng-kpi-card">
          <p className="mng-kpi-label">{t("managerActiveTickets")}</p>
          <p className="mng-kpi-val">{analytics.activeTickets}</p>
        </div>

        <div className="mng-kpi-card">
          <p className="mng-kpi-label">{t("managerResolvedTickets")}</p>
          <p className="mng-kpi-val">{analytics.resolvedTickets}</p>
        </div>

        <div className="mng-kpi-card accent">
          <p className="mng-kpi-label">{t("managerLowConfidenceCount")}</p>
          <p className="mng-kpi-val">{analytics.lowConfidenceCount}</p>
        </div>

        <div className="mng-kpi-card">
          <p className="mng-kpi-label">{t("managerAvgSla")}</p>
          <p className="mng-kpi-val">
            {analytics.avgResolutionHours} {t("managerHoursShort")}
          </p>
        </div>
      </div>

      {/* Department Workload Breakdown */}
      <section className="mng-card" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <h3 style={{ fontSize: '1.125rem', fontWeight: 700, margin: 0 }}>{t("managerDepartmentLoad")}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {analytics.departmentMetrics.map((dept) => (
            <div key={dept.departmentId} style={{ padding: '1rem', background: 'var(--canvas)', borderRadius: '0.75rem', border: '1px solid var(--line)', display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontWeight: 600, fontSize: '0.875rem' }}>{dept.label}</span>
                <span className="cust-status-pill is-triaged">
                  {dept.total} {t("managerTotalShort")}
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', fontSize: '0.75rem', color: 'var(--muted)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{t("managerInProgress")}:</span>
                  <span style={{ fontWeight: 600, color: 'var(--ink)' }}>{dept.inProgress}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{t("managerResolvedShort")}:</span>
                  <span style={{ fontWeight: 600, color: 'var(--ink)' }}>{dept.resolved}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span>{t("managerAvgSlaShort")}:</span>
                  <span style={{ fontWeight: 600, color: 'var(--ink)' }}>
                    {dept.avgResolutionHours} {t("managerHoursShort")}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
