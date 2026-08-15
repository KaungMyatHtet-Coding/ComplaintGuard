"use client";

import { useCallback, useEffect, useState } from "react";
import { useApp } from "@/components/app-provider";
import { ManagerAnalyticsOverview } from "@/components/manager-analytics-overview";
import { ManagerLowConfidenceReview } from "@/components/manager-low-confidence-review";
import { ModelAnalyticsDashboard } from "@/components/model-analytics-dashboard";
import { getFirebaseServices } from "@/lib/firebase";
import {
  type LowConfidenceTicket,
  type ManagerAnalytics,
  fetchLowConfidenceTickets,
  fetchManagerAnalytics,
  overrideTicketDepartment,
} from "@/lib/manager-workflow";

async function currentToken() {
  const user = getFirebaseServices().auth.currentUser;
  if (!user) return null;
  return user.getIdToken();
}

export function ManagerDashboardWorkflow() {
  const { t } = useApp();
  const [analytics, setAnalytics] = useState<ManagerAnalytics | null>(null);
  const [tickets, setTickets] = useState<LowConfidenceTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"overview" | "review" | "model">("overview");

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const token = await currentToken();
      if (!token) throw new Error("No token");
      const [anData, lcTickets] = await Promise.all([
        fetchManagerAnalytics(token),
        fetchLowConfidenceTickets(token),
      ]);
      setAnalytics(anData);
      setTickets(lcTickets);
    } catch {
      setError(t("managerDashboardLoadError"));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    queueMicrotask(() => {
      void loadData();
    });
  }, [loadData]);

  const handleOverride = async (
    ticketId: string,
    newDeptId: string,
    reason: string,
  ) => {
    setError(null);
    setSuccessMsg(null);
    try {
      const token = await currentToken();
      if (!token) throw new Error("No token");
      await overrideTicketDepartment(token, ticketId, newDeptId, reason);
      setSuccessMsg(t("managerOverrideSuccess"));
      await loadData();
    } catch {
      setError(t("managerOverrideError"));
    }
  };

  if (loading) {
    return (
      <div className="cust-layout" style={{ textAlign: 'center', padding: '3rem' }}>
        <p style={{ color: 'var(--muted)' }}>{t("managerDashboardLoading")}</p>
      </div>
    );
  }

  return (
    <div className="cust-layout" style={{ maxWidth: '1100px', margin: '0 auto', width: '100%' }}>
      {error && (
        <div className="cust-error" role="alert">
          {error}
        </div>
      )}

      {successMsg && (
        <div className="success-panel" role="status">
          {successMsg}
        </div>
      )}

      <div className="cust-tabs">
        <button
          type="button"
          className={`cust-tab ${activeTab === "overview" ? "active" : ""}`}
          onClick={() => setActiveTab("overview")}
        >
          {t("managerExecutiveOperations")}
        </button>
        <button
          type="button"
          className={`cust-tab ${activeTab === "review" ? "active" : ""}`}
          onClick={() => setActiveTab("review")}
        >
          {t("managerLowConfidenceQueue")}
        </button>
        <button
          type="button"
          className={`cust-tab ${activeTab === "model" ? "active" : ""}`}
          onClick={() => setActiveTab("model")}
        >
          {t("modelAnalyticsTitle")}
        </button>
      </div>

      <div className="cust-tab-content">
        {activeTab === "overview" && analytics && <ManagerAnalyticsOverview analytics={analytics} />}
        {activeTab === "review" && <ManagerLowConfidenceReview tickets={tickets} onOverride={handleOverride} />}
        {activeTab === "model" && <ModelAnalyticsDashboard />}
      </div>
    </div>
  );
}
