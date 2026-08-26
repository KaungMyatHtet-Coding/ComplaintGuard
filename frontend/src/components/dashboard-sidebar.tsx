"use client";

import type { AppRole } from "@/lib/auth-policy";
import type { MessageKey } from "@/lib/i18n";
import { useApp } from "@/components/app-provider";
import { useEffect, useState } from "react";

export type DashboardNavItem = {
  href: string;
  labelKey: MessageKey;
};

export function getDashboardNavigation(role: AppRole): readonly DashboardNavItem[] {
  const commonNotifications = { href: "#notification-center", labelKey: "dashboardNavNotifications" as MessageKey };
  if (role === "customer") {
    return [
      { href: "#overview", labelKey: "dashboardNavOverview" },
      { href: "#new-complaint", labelKey: "dashboardNavNewComplaint" },
      { href: "#complaint-history", labelKey: "dashboardNavHistory" },
      commonNotifications,
    ];
  }
  if (role === "staff") {
    return [
      { href: "#staff-queue", labelKey: "dashboardNavQueue" },
      { href: "#notification-center", labelKey: "dashboardNavNotifications" },
    ];
  }
  if (role === "manager") {
    return [
      { href: "#manager-operations", labelKey: "dashboardNavOperations" },
      { href: "#manager-review", labelKey: "dashboardNavReview" },
      { href: "#manager-analytics", labelKey: "dashboardNavAnalytics" },
      { href: "#manager-model-evidence", labelKey: "dashboardNavModelEvidence" },
      { href: "#notification-center", labelKey: "dashboardNavNotifications" },
    ];
  }
  return [
    { href: "#overview", labelKey: "dashboardNavOverview" },
    { href: "#admin-provisioning", labelKey: "dashboardNavCreateAccount" },
    { href: "#admin-directory", labelKey: "dashboardNavAccounts" },
    commonNotifications,
  ];
}

type DashboardSidebarProps = {
  role: AppRole;
  expanded: boolean;
  mobileOpen: boolean;
  onToggle: () => void;
  onCloseMobile: () => void;
};

export function DashboardSidebar({ role, expanded, mobileOpen, onToggle, onCloseMobile }: DashboardSidebarProps) {
  const { t } = useApp();
  const items = getDashboardNavigation(role);
  const [activeHref, setActiveHref] = useState("#overview");

  useEffect(() => {
    const updateActiveHref = () => setActiveHref(window.location.hash || "#overview");
    updateActiveHref();
    window.addEventListener("hashchange", updateActiveHref);
    return () => window.removeEventListener("hashchange", updateActiveHref);
  }, []);
  return (
    <aside id="dashboard-sidebar" className={`dashboard-sidebar${expanded ? " is-expanded" : " is-collapsed"}${mobileOpen ? " is-mobile-open" : ""}`} aria-label={t("dashboardNavigationLabel")}>
      <div className="dashboard-sidebar-heading">
        <span className="dashboard-sidebar-mark" aria-hidden="true">CG</span>
        <span className="dashboard-sidebar-title">ComplaintGuard</span>
        <button type="button" className="dashboard-sidebar-toggle" onClick={onToggle} aria-label={expanded ? t("collapseNavigation") : t("expandNavigation")} aria-expanded={expanded}>
          <span aria-hidden="true">{expanded ? "‹" : "›"}</span>
        </button>
      </div>
      <nav aria-label="Dashboard sections">
        {items.map((item, index) => (
          <a key={item.href + item.labelKey} href={item.href} aria-current={item.href === activeHref ? "page" : undefined} title={expanded ? undefined : t(item.labelKey)} onClick={onCloseMobile}>
            <span className="dashboard-nav-icon" aria-hidden="true">{index === 0 ? "◈" : index === items.length - 1 ? "•" : "○"}</span>
            <span className="dashboard-nav-label">{t(item.labelKey)}</span>
          </a>
        ))}
      </nav>
    </aside>
  );
}
