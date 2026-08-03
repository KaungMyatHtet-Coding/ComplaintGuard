"use client";

import { useCallback, useEffect, useState } from "react";
import { ManagerAnalyticsOverview } from "@/components/manager-analytics-overview";
import { ManagerLowConfidenceReview } from "@/components/manager-low-confidence-review";
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
  const [analytics, setAnalytics] = useState<ManagerAnalytics | null>(null);
  const [tickets, setTickets] = useState<LowConfidenceTicket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

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
      setError("Failed to load manager dashboard data.");
    } finally {
      setLoading(false);
    }
  }, []);

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
      setSuccessMsg(`Ticket ${ticketId} reassigned to ${newDeptId}.`);
      await loadData();
    } catch {
      setError("Failed to override department assignment.");
    }
  };

  if (loading) {
    return (
      <div className="p-8 text-center space-y-3">
        <div className="spinner mx-auto" />
        <p className="text-sm text-gray-500 font-medium">Loading manager dashboard...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8 max-w-6xl mx-auto p-4 sm:p-6">
      {error && (
        <div className="p-4 bg-red-50 text-red-700 text-sm font-semibold rounded-xl border border-red-200">
          {error}
        </div>
      )}

      {successMsg && (
        <div className="p-4 bg-emerald-50 text-emerald-800 text-sm font-semibold rounded-xl border border-emerald-200">
          {successMsg}
        </div>
      )}

      {analytics && <ManagerAnalyticsOverview analytics={analytics} />}

      <ManagerLowConfidenceReview tickets={tickets} onOverride={handleOverride} />
    </div>
  );
}
