"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppHeader } from "@/components/app-header";
import { useApp } from "@/components/app-provider";
import { CustomerDashboardWorkflow } from "@/components/customer-dashboard-workflow";
import { StaffTicketQueue } from "@/components/staff-ticket-queue";

const shellKeys = {
  customer: "customerShell",
  staff: "staffShell",
  manager: "managerShell",
  admin: "adminShell",
} as const;

export function ProtectedDashboard() {
  const router = useRouter();
  const { profile, status, t } = useApp();

  useEffect(() => {
    if (status === "unauthenticated" || status === "configuration_missing" || status === "error") {
      router.replace("/login");
    }
  }, [router, status]);

  if (status !== "authenticated" || !profile) {
    return (
      <main className="centered-state" aria-live="polite">
        <div className="spinner" />
        <p>{t("loading")}</p>
      </main>
    );
  }

  return (
    <>
      <AppHeader />
      <main className="dashboard-shell">
        <aside className="dashboard-nav">
          <p className="eyebrow">{profile.role}</p>
          <strong>{profile.displayName}</strong>
          {profile.departmentId ? <span>{profile.departmentId}</span> : null}
          <a href="#overview" aria-current="page">
            {t("dashboard")}
          </a>
        </aside>
        <section id="overview" className="dashboard-content">
          <p className="eyebrow">Day 15 workflow</p>
          <h1>{t(shellKeys[profile.role])}</h1>
          <div className="security-note mb-6">{t("securityBoundary")}</div>
          {profile.role === "customer" ? <CustomerDashboardWorkflow /> : null}
          {profile.role === "staff" ? <StaffTicketQueue /> : null}
        </section>
      </main>
    </>
  );
}

