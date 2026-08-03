import { describe, expect, it, vi } from "vitest";

import {
  ManagerWorkflowError,
  fetchLowConfidenceTickets,
  fetchManagerAnalytics,
  overrideTicketDepartment,
} from "./manager-workflow";

describe("manager-workflow API client", () => {
  it("fetches manager analytics successfully", async () => {
    const mockData = {
      totalTickets: 10,
      activeTickets: 6,
      resolvedTickets: 4,
      lowConfidenceCount: 2,
      avgResolutionHours: 12.5,
      departmentMetrics: [],
    };
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockData,
    });

    const data = await fetchManagerAnalytics("valid-token", mockFetcher);
    expect(data.totalTickets).toBe(10);
    expect(mockFetcher).toHaveBeenCalledWith(
      "http://localhost:8000/manager/analytics",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer valid-token",
        }),
      }),
    );
  });

  it("fetches low-confidence tickets list", async () => {
    const mockList = [
      {
        id: "ticket_01",
        customerId: "cust_1",
        complaintText: "Unknown charge",
        inputLocale: "en",
        predictedDepartmentId: "account_support",
        predictionConfidence: 0.45,
        assignedDepartmentId: "account_support",
        status: "triaged",
        priority: "normal",
        routingSource: "manual_review",
        createdAt: "2026-08-03T10:00:00Z",
      },
    ];
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockList,
    });

    const tickets = await fetchLowConfidenceTickets("valid-token", mockFetcher);
    expect(tickets).toHaveLength(1);
    expect(tickets[0].id).toBe("ticket_01");
  });

  it("posts department override successfully", async () => {
    const mockResponse = {
      ticketId: "ticket_01",
      assignedDepartmentId: "fraud_security",
      routingSource: "manager_override",
      updatedAt: "2026-08-03T12:00:00Z",
    };
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });

    const result = await overrideTicketDepartment(
      "valid-token",
      "ticket_01",
      "fraud_security",
      "Manual review override",
      mockFetcher,
    );
    expect(result.assignedDepartmentId).toBe("fraud_security");
    expect(result.routingSource).toBe("manager_override");
  });

  it("handles 403 permission error", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
    });

    await expect(fetchManagerAnalytics("customer-token", mockFetcher)).rejects.toThrow(
      ManagerWorkflowError,
    );
  });
});
