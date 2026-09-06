"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AdminUserProvisioning } from "@/components/admin-user-provisioning";
import { AdminV2Foundation } from "@/components/admin-v2-foundation";
import { AccessibleSkeleton } from "@/components/accessible-skeleton";
import { useApp } from "@/components/app-provider";
import { CustomerDashboardWorkflow } from "@/components/customer-dashboard-workflow";
import { DashboardShell } from "@/components/dashboard-shell";
import { ManagerDashboardWorkflow } from "@/components/manager-dashboard-workflow";
import { StaffTicketQueue } from "@/components/staff-ticket-queue";
import { canViewManagerAnalytics } from "@/lib/auth-policy";

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
      <main className="centered-state">
        <AccessibleSkeleton label={t("loading")} />
      </main>
    );
  }

  return (
    <DashboardShell>
      <section id="overview" className="dashboard-role-workspace">
        {profile.role === "admin" ? <><AdminUserProvisioning /><AdminV2Foundation /></> : null}
        {profile.role === "customer" ? <CustomerDashboardWorkflow /> : null}
        {profile.role === "staff" ? <StaffTicketQueue /> : null}
        {canViewManagerAnalytics(profile.role) ? <ManagerDashboardWorkflow /> : null}
      </section>
    </DashboardShell>
  );
}

