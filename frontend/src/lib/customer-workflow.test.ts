import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchCustomerTickets,
  fetchCustomerTicketDetail,
  sendCustomerMessage,
  submitCustomerFeedback,
  CustomerWorkflowError,
} from "./customer-workflow";

describe("Customer Workflow Client Library", () => {
  const originalEnv = process.env.NEXT_PUBLIC_ML_API_URL;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_ML_API_URL = "http://localhost:8000";
  });

  afterEach(() => {
    process.env.NEXT_PUBLIC_ML_API_URL = originalEnv;
  });

  it("fetches customer tickets list successfully", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        tickets: [
          {
            id: "t1",
            status: "submitted",
            createdAt: "2026-08-01",
            updatedAt: "2026-08-01",
            summaryText: "Transfer issue",
          },
        ],
      }),
    });

    const tickets = await fetchCustomerTickets("test_token", mockFetcher as unknown as typeof fetch);
    expect(tickets).toHaveLength(1);
    expect(tickets[0].id).toBe("t1");
  });

  it("handles auth error when fetching tickets", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({}),
    });

    await expect(
      fetchCustomerTickets("invalid_token", mockFetcher as unknown as typeof fetch)
    ).rejects.toThrow(CustomerWorkflowError);
  });

  it("fetches ticket detail and timeline", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "t1",
        customerId: "c1",
        status: "in_progress",
        complaintText: "Card swallowed at ATM",
        inputLocale: "en",
        priority: "high",
        createdAt: "2026-08-01",
        updatedAt: "2026-08-01",
        messages: [],
      }),
    });

    const detail = await fetchCustomerTicketDetail("t1", "test_token", mockFetcher as unknown as typeof fetch);
    expect(detail.id).toBe("t1");
    expect(detail.status).toBe("in_progress");
  });

  it("sends customer message successfully", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "m1",
        senderId: "c1",
        senderRole: "customer",
        text: "Please follow up",
        createdAt: "2026-08-01",
      }),
    });

    const msg = await sendCustomerMessage("t1", "Please follow up", "test_token", mockFetcher as unknown as typeof fetch);
    expect(msg.text).toBe("Please follow up");
  });

  it("submits customer feedback for resolved ticket", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        ticketId: "t1",
        feedbackId: "fb_t1",
        status: "feedback_submitted",
      }),
    });

    const res = await submitCustomerFeedback("t1", 5, "Great job", "test_token", mockFetcher as unknown as typeof fetch);
    expect(res.feedbackId).toBe("fb_t1");
  });
});
