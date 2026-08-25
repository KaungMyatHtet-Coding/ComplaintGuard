import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchCustomerTickets,
  fetchCustomerTicketDetail,
  parseCustomerTicketHistoryPage,
  sendCustomerMessage,
  submitCustomerFeedback,
  CustomerWorkflowError,
} from "./customer-workflow";

describe("Customer Workflow Client Library", () => {
  const originalEnv = process.env.NEXT_PUBLIC_ML_API_URL;

  beforeEach(() => {
    process.env.NEXT_PUBLIC_APP_ENV = "local-emulator";
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
            complaintId: "ticket_" + "a".repeat(32),
            status: "submitted",
            departmentId: null,
            createdAt: "2026-08-01T00:00:00Z",
            updatedAt: "2026-08-01T00:00:00Z",
            resolvedAt: null,
          },
        ],
        nextCursor: null,
        hasMore: false,
      }),
    });

    const page = await fetchCustomerTickets("test_token", { fetcher: mockFetcher as unknown as typeof fetch });
    expect(page.tickets).toHaveLength(1);
    expect(page.tickets[0].complaintId).toBe("ticket_" + "a".repeat(32));
    expect(mockFetcher).toHaveBeenCalledWith(
      "http://localhost:8000/customer/tickets?pageSize=25",
      expect.objectContaining({ signal: undefined }),
    );
  });

  it("handles auth error when fetching tickets", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      json: async () => ({}),
    });

    await expect(
      fetchCustomerTickets("invalid_token", { fetcher: mockFetcher as unknown as typeof fetch })
    ).rejects.toThrow(CustomerWorkflowError);
  });

  it("serializes only selected exact filters and omits All values", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ tickets: [], nextCursor: null, hasMore: false }),
    });
    await fetchCustomerTickets("test_token", {
      status: "resolved",
      departmentId: "card_atm",
      fetcher: mockFetcher as unknown as typeof fetch,
    });
    expect(mockFetcher.mock.calls[0][0]).toBe(
      "http://localhost:8000/customer/tickets?pageSize=25&status=resolved&departmentId=card_atm",
    );

    mockFetcher.mockClear();
    await fetchCustomerTickets("test_token", {
      status: null,
      departmentId: null,
      fetcher: mockFetcher as unknown as typeof fetch,
    });
    expect(mockFetcher.mock.calls[0][0]).toBe("http://localhost:8000/customer/tickets?pageSize=25");
  });

  it("rejects invalid filters before token/network use", async () => {
    const fetcher = vi.fn();
    await expect(fetchCustomerTickets("test_token", {
      status: " RESOLVED" as never,
      fetcher: fetcher as unknown as typeof fetch,
    })).rejects.toMatchObject({ code: "validation" });
    await expect(fetchCustomerTickets("test_token", {
      departmentId: "card-atm" as never,
      fetcher: fetcher as unknown as typeof fetch,
    })).rejects.toMatchObject({ code: "validation" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("does not fetch when the application environment is staging", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "cloud-staging");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "https://api.example.test");
    const fetcher = vi.fn();
    await expect(fetchCustomerTickets("token", { fetcher: fetcher as unknown as typeof fetch })).rejects.toMatchObject({ code: "backend" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("parses hostile history rows strictly", () => {
    const valid = {
      complaintId: "ticket_" + "a".repeat(32),
      status: "submitted",
      departmentId: null,
      createdAt: "2026-08-01T00:00:00Z",
      updatedAt: "2026-08-01T00:00:00Z",
      resolvedAt: null,
    };
    expect(() => parseCustomerTicketHistoryPage({ tickets: [valid], nextCursor: null, hasMore: false, privateField: "x" })).toThrow();
    const inherited = Object.create({ tickets: [valid] }) as Record<string, unknown>;
    inherited.nextCursor = null;
    inherited.hasMore = false;
    expect(() => parseCustomerTicketHistoryPage(inherited)).toThrow();
    const accessor = { tickets: [valid], nextCursor: null, hasMore: false };
    Object.defineProperty(accessor, "tickets", { enumerable: true, get: () => [valid] });
    expect(() => parseCustomerTicketHistoryPage(accessor)).toThrow();
  });

  it("rejects a cursor timestamp that the backend would not re-encode canonically", () => {
    const payload = JSON.stringify({
      v: 1,
      customerBinding: "a".repeat(64),
      contract: "b".repeat(64),
      createdAt: "2026-08-01T00:00:00+00:00",
      complaintId: "ticket_" + "a".repeat(32),
    });
    const cursor = btoa(payload).replace(/\+/gu, "-").replace(/\//gu, "_").replace(/=+$/u, "");
    expect(() => parseCustomerTicketHistoryPage({
      tickets: [],
      nextCursor: cursor,
      hasMore: true,
    })).toThrow();
  });

  it("propagates AbortSignal and encodes detail references", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: "t1",
        status: "in_progress",
        complaintText: "Card swallowed at ATM",
        inputLocale: "en",
        priority: "high",
        timeline: [],
        createdAt: "2026-08-01",
        updatedAt: "2026-08-01",
        messages: [],
      }),
    });

    const controller = new AbortController();
    const detail = await fetchCustomerTicketDetail("t1/x", "test_token", mockFetcher as unknown as typeof fetch, controller.signal);
    expect(detail.id).toBe("t1");
    expect(detail.status).toBe("in_progress");
    expect(mockFetcher).toHaveBeenCalledWith(
      "http://localhost:8000/customer/tickets/t1%2Fx",
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it("sends customer message successfully", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        senderRole: "customer",
        body: "Please follow up",
        createdAt: "2026-08-01",
      }),
    });

    const msg = await sendCustomerMessage("t1", "Please follow up", "test_token", mockFetcher as unknown as typeof fetch);
    expect(msg.body).toBe("Please follow up");
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

  it("maps duplicate-feedback conflict without returning success", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ error: { code: "feedback_already_submitted" } }),
    });

    await expect(
      submitCustomerFeedback(
        "t1",
        5,
        "Must not overwrite",
        "test_token",
        mockFetcher as unknown as typeof fetch,
      ),
    ).rejects.toMatchObject({ code: "conflict" });
  });
});
