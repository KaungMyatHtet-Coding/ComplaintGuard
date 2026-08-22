"use client";

import { useEffect, useRef, useState } from "react";

import { AppHeader } from "@/components/app-header";
import { useApp } from "@/components/app-provider";
import { DashboardSidebar } from "@/components/dashboard-sidebar";
import { getDepartmentLabel } from "@/lib/department-labels";

function pageHeader(role: "customer" | "staff" | "manager" | "admin", displayName: string, departmentId: string | null, locale: "en" | "my", t: ReturnType<typeof useApp>["t"]) {
  const name = displayName.trim() || t("dashboardFallbackName");
  if (role === "customer") return { title: `${t("dashboardWelcome")}, ${name}`, support: t("dashboardCustomerSupport") };
  if (role === "staff") {
    const department = getDepartmentLabel(departmentId, locale) ?? t("dashboardDepartmentUnavailable");
    return { title: t("dashboardStaffTitle"), support: `${department} · ${t("dashboardStaffSupport")}` };
  }
  if (role === "manager") return { title: t("dashboardManagerTitle"), support: t("dashboardManagerSupport") };
  return { title: t("dashboardAdminTitle"), support: t("dashboardAdminSupport") };
}

export function DashboardShell({ children }: { children: React.ReactNode }) {
  const { locale, profile, t } = useApp();
  const [expanded, setExpanded] = useState(true);
  const [mobileOpen, setMobileOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);
  const drawerWasOpenRef = useRef(false);

  useEffect(() => {
    if (!mobileOpen) return;
    const firstLink = sidebarRef.current?.querySelector<HTMLAnchorElement>("a");
    firstLink?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMobileOpen(false);
    };
    document.addEventListener("keydown", onKeyDown);
    document.body.classList.add("dashboard-drawer-open");
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.classList.remove("dashboard-drawer-open");
    };
  }, [mobileOpen]);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 761px)");
    const closeForDesktop = () => {
      if (media.matches) setMobileOpen(false);
    };
    media.addEventListener?.("change", closeForDesktop);
    return () => media.removeEventListener?.("change", closeForDesktop);
  }, []);

  useEffect(() => {
    if (mobileOpen) {
      drawerWasOpenRef.current = true;
    } else if (drawerWasOpenRef.current) {
      menuButtonRef.current?.focus();
    }
  }, [mobileOpen]);

  if (!profile) return <>{children}</>;
  const header = pageHeader(profile.role, profile.displayName, profile.departmentId, locale ?? "en", t);
  return (
    <div className="dashboard-app-shell">
      <a className="skip-link" href="#dashboard-main">{t("skipToContent")}</a>
      <AppHeader onMenu={() => setMobileOpen(true)} menuButtonRef={menuButtonRef} menuOpen={mobileOpen} />
      <div className="dashboard-shell-body">
        <div ref={sidebarRef} className="dashboard-sidebar-host">
          <DashboardSidebar role={profile.role} expanded={expanded} mobileOpen={mobileOpen} onToggle={() => setExpanded((value) => !value)} onCloseMobile={() => setMobileOpen(false)} />
        </div>
        {mobileOpen ? <button type="button" className="dashboard-drawer-backdrop" aria-label={t("closeNavigation")} onClick={() => setMobileOpen(false)} /> : null}
        <main id="dashboard-main" className="dashboard-main" aria-hidden={mobileOpen || undefined} inert={mobileOpen || undefined}>
          <header className="dashboard-page-header" aria-labelledby="dashboard-page-title">
            <div>
              <p className="dashboard-page-eyebrow">{t("dashboardWorkspaceLabel")}</p>
              <h1 id="dashboard-page-title" className="dashboard-page-title">{header.title}</h1>
              <p className="dashboard-page-support">{header.support}</p>
            </div>
          </header>
          <div className="dashboard-workspace-content">{children}</div>
        </main>
      </div>
    </div>
  );
}
