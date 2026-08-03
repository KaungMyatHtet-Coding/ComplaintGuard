import { describe, expect, it, vi } from "vitest";

import {
  CustomerWorkflowError,
  fetchCustomerTicketDetail,
  fetchCustomerTickets,
  postCustomerMessage,
  submitCustomerFeedback,
} from "./customer-workflow";

describe("customer-workflow API client", () => {
  it("fetches customer tickets list", async () => {
    const mockTickets = [
      {
        id: "cg_ticket_001",
        status: "in_progress",
        complaintText: "Money transfer issue",
        createdAt: "2026-08-02T10:00:00Z",
        updatedAt: "2026-08-03T11:00:00Z",
      },
    ];
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockTickets,
    });

    const list = await fetchCustomerTickets("valid-token", mockFetcher);
    expect(list).toHaveLength(1);
    expect(list[0].id).toBe("cg_ticket_001");
  });

  it("fetches ticket detail", async () => {
    const mockDetail = {
      id: "cg_ticket_001",
      status: "in_progress",
      complaintText: "Money transfer issue",
      createdAt: "2026-08-02T10:00:00Z",
      updatedAt: "2026-08-03T11:00:00Z",
      messages: [],
    };
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockDetail,
    });

    const detail = await fetchCustomerTicketDetail("valid-token", "cg_ticket_001", mockFetcher);
    expect(detail.id).toBe("cg_ticket_001");
  });

  it("posts customer message", async () => {
    const mockMsg = {
      messageId: "msg_01",
      senderId: "cust_01",
      senderRole: "customer",
      text: "Hello",
      createdAt: "2026-08-03T12:00:00Z",
    };
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockMsg,
    });

    const msg = await postCustomerMessage("valid-token", "cg_ticket_001", "Hello", mockFetcher);
    expect(msg.messageId).toBe("msg_01");
  });

  it("submits customer feedback rating", async () => {
    const mockRes = {
      ticketId: "cg_ticket_002",
      rating: 5,
      submittedAt: "2026-08-03T12:00:00Z",
    };
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockRes,
    });

    const res = await submitCustomerFeedback("valid-token", "cg_ticket_002", 5, "Great", mockFetcher);
    expect(res.rating).toBe(5);
  });

  it("handles 401 auth error", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
    });

    await expect(fetchCustomerTickets("invalid-token", mockFetcher)).rejects.toThrow(
      CustomerWorkflowError,
    );
  });
});
