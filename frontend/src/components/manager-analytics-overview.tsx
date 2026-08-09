"use client";

import { useApp } from "@/components/app-provider";
import type { ManagerAnalytics } from "@/lib/manager-workflow";

type ManagerAnalyticsOverviewProps = {
  analytics: ManagerAnalytics;
};

export function ManagerAnalyticsOverview({ analytics }: ManagerAnalyticsOverviewProps) {
  const { t } = useApp();

  return (
    <div className="space-y-6">
      <header>
        <p className="text-xs font-semibold tracking-wider text-blue-600 uppercase">
          {t("managerExecutiveOperations")}
        </p>
        <h2 className="text-2xl font-bold text-gray-900">{t("managerAnalyticsTitle")}</h2>
      </header>

      {/* KPI Cards Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
          <p className="text-xs font-medium text-gray-500">{t("managerTotalTickets")}</p>
          <p className="mt-2 text-3xl font-extrabold text-gray-900">{analytics.totalTickets}</p>
        </div>

        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
          <p className="text-xs font-medium text-gray-500">{t("managerActiveTickets")}</p>
          <p className="mt-2 text-3xl font-extrabold text-blue-600">{analytics.activeTickets}</p>
        </div>

        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
          <p className="text-xs font-medium text-gray-500">{t("managerResolvedTickets")}</p>
          <p className="mt-2 text-3xl font-extrabold text-emerald-600">{analytics.resolvedTickets}</p>
        </div>

        <div className="p-4 bg-white rounded-xl border border-amber-200 bg-amber-50/30 shadow-sm">
          <p className="text-xs font-medium text-amber-700">{t("managerLowConfidenceCount")}</p>
          <p className="mt-2 text-3xl font-extrabold text-amber-600">{analytics.lowConfidenceCount}</p>
        </div>

        <div className="p-4 bg-white rounded-xl border border-gray-200 shadow-sm">
          <p className="text-xs font-medium text-gray-500">{t("managerAvgSla")}</p>
          <p className="mt-2 text-3xl font-extrabold text-purple-600">
            {analytics.avgResolutionHours} {t("managerHoursShort")}
          </p>
        </div>
      </div>

      {/* Department Workload Breakdown */}
      <section className="p-5 bg-white rounded-xl border border-gray-200 shadow-sm space-y-4">
        <h3 className="text-lg font-bold text-gray-900">{t("managerDepartmentLoad")}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {analytics.departmentMetrics.map((dept) => (
            <div key={dept.departmentId} className="p-4 bg-gray-50 rounded-lg border border-gray-100 space-y-2">
              <div className="flex justify-between items-center">
                <span className="font-semibold text-gray-900 text-sm">{dept.label}</span>
                <span className="px-2 py-0.5 text-xs font-bold bg-blue-100 text-blue-800 rounded-full">
                  {dept.total} {t("managerTotalShort")}
                </span>
              </div>

              <div className="space-y-1 text-xs text-gray-600">
                <div className="flex justify-between">
                  <span>{t("managerInProgress")}:</span>
                  <span className="font-semibold text-blue-700">{dept.inProgress}</span>
                </div>
                <div className="flex justify-between">
                  <span>{t("managerResolvedShort")}:</span>
                  <span className="font-semibold text-emerald-700">{dept.resolved}</span>
                </div>
                <div className="flex justify-between">
                  <span>{t("managerAvgSlaShort")}:</span>
                  <span className="font-semibold text-purple-700">
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
