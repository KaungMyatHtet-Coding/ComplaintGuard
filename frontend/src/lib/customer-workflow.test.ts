import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  fetchCustomerTickets,
  fetchCustomerTicketDetail,
  normalizeCustomerMessageText,
  parseCustomerMessageItem,
  parseCustomerTicketDetail,
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

  it("propagates AbortSignal and strictly parses detail references", async () => {
    const ticketId = "ticket_" + "b".repeat(32);
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        id: ticketId,
        status: "in_progress",
        complaintText: "Card swallowed at ATM",
        inputLocale: "en",
        departmentId: "card_atm",
        timeline: [],
        createdAt: "2026-08-01T00:00:00Z",
        updatedAt: "2026-08-01T00:00:00Z",
        resolvedAt: null,
        messages: [],
        feedback: null,
      }),
    });

    const controller = new AbortController();
    const detail = await fetchCustomerTicketDetail(ticketId, "test_token", mockFetcher as unknown as typeof fetch, controller.signal);
    expect(detail.id).toBe(ticketId);
    expect(detail.status).toBe("in_progress");
    expect(mockFetcher).toHaveBeenCalledWith(
      `http://localhost:8000/customer/tickets/${ticketId}`,
      expect.objectContaining({ signal: controller.signal }),
    );
  });

  it("rejects priority, extra fields, and contradictory detail state", () => {
    const valid = {
      id: "ticket_" + "a".repeat(32),
      status: "submitted",
      complaintText: "Safe complaint",
      inputLocale: "en",
      departmentId: null,
      createdAt: "2026-08-01T00:00:00Z",
      updatedAt: "2026-08-01T00:00:00Z",
      resolvedAt: null,
      messages: [],
      timeline: [],
      feedback: null,
    };
    expect(() => parseCustomerTicketDetail({ ...valid, priority: "high" })).toThrow();
    expect(() => parseCustomerTicketDetail({ ...valid, privateField: "x" })).toThrow();
    expect(() => parseCustomerTicketDetail({ ...valid, status: "closed", resolvedAt: null })).toThrow();
  });

  it("rejects noncanonical and calendar-overflow timestamps", () => {
    const valid = {
      id: "ticket_" + "d".repeat(32),
      status: "submitted",
      complaintText: "Safe complaint",
      inputLocale: "en",
      departmentId: null,
      createdAt: "2026-02-30T00:00:00Z",
      updatedAt: "2026-02-30T00:00:00Z",
      resolvedAt: null,
      messages: [],
      timeline: [],
      feedback: null,
    };
    expect(() => parseCustomerTicketDetail(valid)).toThrow();
    expect(() => parseCustomerTicketDetail({
      ...valid,
      createdAt: "2026-02-28T00:00:00Z",
      updatedAt: "2026-02-28T00:00:00Z",
    })).not.toThrow();
    expect(() => parseCustomerTicketDetail({
      ...valid,
      createdAt: "2026-02-28T00:00:00.1Z",
      updatedAt: "2026-02-28T00:00:00.1Z",
    })).toThrow();
    expect(() => parseCustomerTicketDetail({
      ...valid,
      createdAt: "2026-02-28T00:00:00.000000Z",
      updatedAt: "2026-02-28T00:00:00.000000Z",
    })).toThrow();
  });

  it("strictly parses nested detail records and rejects hostile objects", () => {
    const valid = {
      id: "ticket_" + "c".repeat(32),
      status: "submitted",
      complaintText: "Safe complaint",
      inputLocale: "my",
      departmentId: null,
      createdAt: "2026-08-01T00:00:00Z",
      updatedAt: "2026-08-01T00:00:00Z",
      resolvedAt: null,
      messages: [{ senderRole: "support_team", body: "Reply", createdAt: "2026-08-01T00:01:00Z" }],
      timeline: [{ type: "complaint_received", occurredAt: "2026-08-01T00:00:00Z", departmentId: null }],
      feedback: null,
    };
    expect(parseCustomerTicketDetail(valid).messages[0].senderRole).toBe("support_team");
    const inherited = Object.create({ complaintText: "private" }) as Record<string, unknown>;
    Object.assign(inherited, valid);
    expect(() => parseCustomerTicketDetail(inherited)).toThrow();
    const accessor = { ...valid };
    Object.defineProperty(accessor, "messages", { enumerable: true, get: () => valid.messages });
    expect(() => parseCustomerTicketDetail(accessor)).toThrow();
    expect(() => parseCustomerTicketDetail({ ...valid, timeline: [{ ...valid.timeline[0], type: "internal_note" }] })).toThrow();
  });

  it("sends customer message successfully", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        senderRole: "customer",
        body: "Please follow up",
        createdAt: "2026-08-01T00:00:00Z",
      }),
    });

    const msg = await sendCustomerMessage("t1", "Please follow up", "test_token", mockFetcher as unknown as typeof fetch);
    expect(msg.body).toBe("Please follow up");
  });

  it("strictly parses the minimal customer message response", () => {
    const valid = {
      senderRole: "customer",
      body: "Safe reply",
      createdAt: "2026-08-01T00:00:00Z",
    };
    expect(parseCustomerMessageItem(valid)).toEqual(valid);
    expect(() => parseCustomerMessageItem({ ...valid, privateField: "x" })).toThrow();
    expect(() => parseCustomerMessageItem({ ...valid, senderRole: "support_team" })).toThrow();
    const accessor = { ...valid };
    Object.defineProperty(accessor, "body", { enumerable: true, get: () => "Safe reply" });
    expect(() => parseCustomerMessageItem(accessor)).toThrow();
    const inherited = Object.create({ body: "Safe reply" });
    Object.assign(inherited, { senderRole: "customer", createdAt: valid.createdAt });
    expect(() => parseCustomerMessageItem(inherited)).toThrow();
  });

  it("sends the exact body, fresh action, and AbortSignal", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        senderRole: "customer",
        body: "Safe reply",
        createdAt: "2026-08-01T00:00:00Z",
      }),
    });
    const controller = new AbortController();
    await sendCustomerMessage(
      "ticket_" + "a".repeat(32),
      "  Safe reply  ",
      "test_token",
      mockFetcher as unknown as typeof fetch,
      "message-action-001",
      controller.signal,
    );
    expect(mockFetcher).toHaveBeenCalledWith(
      "http://localhost:8000/customer/tickets/ticket_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/messages",
      expect.objectContaining({
        signal: controller.signal,
        body: JSON.stringify({ messageText: "Safe reply", actionId: "message-action-001" }),
      }),
    );
  });

  it("uses the backend-compatible normalized text and encoded ticket path", async () => {
    const mockFetcher = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        senderRole: "customer",
        body: "Safe reply",
        createdAt: "2026-08-01T00:00:00Z",
      }),
    });

    expect(normalizeCustomerMessageText("  Safe\t\nreply  ")).toBe("Safe reply");
    await sendCustomerMessage(
      "ticket/unsafe",
      "  Safe\t\nreply  ",
      "test_token",
      mockFetcher as unknown as typeof fetch,
      "message-action-004",
    );
    expect(mockFetcher).toHaveBeenCalledWith(
      "http://localhost:8000/customer/tickets/ticket%2Funsafe/messages",
      expect.objectContaining({
        body: JSON.stringify({ messageText: "Safe reply", actionId: "message-action-004" }),
      }),
    );
  });

  it("treats an abort after dispatch as an unknown outcome", async () => {
    const controller = new AbortController();
    const mockFetcher = vi.fn().mockImplementation(async () => {
      controller.abort();
      return {
        ok: true,
        status: 200,
        json: async () => ({
          senderRole: "customer",
          body: "Safe reply",
          createdAt: "2026-08-01T00:00:00Z",
        }),
      };
    });

    await expect(
      sendCustomerMessage(
        "t1",
        "Safe reply",
        "test_token",
        mockFetcher as unknown as typeof fetch,
        "message-action-005",
        controller.signal,
      ),
    ).rejects.toMatchObject({ code: "unknown" });
  });

  it("classifies lost responses as unknown and maps safe 409 conflicts", async () => {
    const unknownFetcher = vi.fn().mockRejectedValue(new Error("connection lost"));
    await expect(
      sendCustomerMessage("t1", "Safe reply", "token", unknownFetcher as unknown as typeof fetch, "message-action-002"),
    ).rejects.toMatchObject({ code: "unknown" });

    const conflictFetcher = vi.fn().mockResolvedValue({
      ok: false,
      status: 409,
      json: async () => ({ error: { code: "idempotency_conflict" } }),
    });
    await expect(
      sendCustomerMessage("t1", "Safe reply", "token", conflictFetcher as unknown as typeof fetch, "message-action-003"),
    ).rejects.toMatchObject({ code: "idempotency_conflict" });
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
