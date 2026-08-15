"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AppHeader } from "@/components/app-header";
import { useApp } from "@/components/app-provider";
import { CustomerDashboardWorkflow } from "@/components/customer-dashboard-workflow";
import { ManagerDashboardWorkflow } from "@/components/manager-dashboard-workflow";
import { StaffTicketQueue } from "@/components/staff-ticket-queue";
import { canViewManagerAnalytics } from "@/lib/auth-policy";
import { getDepartmentLabel } from "@/lib/department-labels";

const shellKeys = {
  customer: "customerShell",
  staff: "staffShell",
  manager: "managerShell",
  admin: "adminShell",
} as const;

export function ProtectedDashboard() {
  const router = useRouter();
  const { locale, profile, status, t } = useApp();

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
      <main className="dashboard-shell-customer">
        <section id="overview" className="dashboard-content" style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '100%', maxWidth: '1200px', margin: '0 auto', padding: '2rem 1.5rem' }}>
          {profile.role !== "customer" && (
            <div className="cust-page-header-row">
              <div className="cust-page-header">
                <h1>Dashboard</h1>
                <span>{profile.role}</span>
              </div>
            </div>
          )}
          {profile.role === "customer" ? <CustomerDashboardWorkflow /> : null}
          {profile.role === "staff" ? <StaffTicketQueue /> : null}
          {canViewManagerAnalytics(profile.role) ? <ManagerDashboardWorkflow /> : null}
        </section>
      </main>
    </>
  );
}

