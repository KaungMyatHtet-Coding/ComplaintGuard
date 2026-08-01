import { afterEach, describe, expect, it, vi } from "vitest";

import { createSubmissionGuard } from "./complaint-submission";
import {
  loadStaffTicket,
  loadStaffTickets,
  replyToTicket,
  requestStaffAction,
  transitionTicket,
} from "./staff-workflow";

afterEach(() => vi.unstubAllEnvs());

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status });
}

describe("staff workflow API client", () => {
  it("serializes filters without adding a department selector", async () => {
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000");
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      const value = String(url);
      expect(value).toContain("status=triaged");
      expect(value).toContain("priority=normal");
      expect(value).not.toContain("department");
      expect(init?.headers).toEqual({ Authorization: "Bearer staff-token" });
      return response({ tickets: [] });
    });
    await expect(
      loadStaffTickets(
        "staff-token",
        { status: "triaged", priority: "normal", createdFrom: "2026-08-02T00:00:00Z" },
        fetcher,
      ),
    ).resolves.toEqual([]);
  });

  it("loads an encoded ticket detail", async () => {
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000");
    const fetcher = vi.fn(async (url: string | URL | Request) => {
      expect(String(url)).toContain("ticket%2Fsynthetic");
      return response({ ticketId: "ticket/synthetic" });
    });
    await expect(loadStaffTicket("token", "ticket/synthetic", fetcher)).resolves.toMatchObject({ ticketId: "ticket/synthetic" });
  });

  it("sends only reply text and idempotency action ID", async () => {
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000");
    const fetcher = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      expect(JSON.parse(String(init?.body))).toEqual({ body: "Synthetic reply", actionId: "reply_action_001" });
      return response({ ticketId: "ticket-1", actionId: "reply_action_001", status: "triaged", duplicate: false });
    });
    await replyToTicket("token", "ticket-1", "Synthetic reply", "reply_action_001", fetcher);
  });

  it("keeps transition and request bodies free of protected fields", async () => {
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000");
    const bodies: unknown[] = [];
    const fetcher = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      bodies.push(JSON.parse(String(init?.body)));
      return response({ ticketId: "ticket-1", actionId: "action", status: "in_progress", duplicate: false });
    });
    await transitionTicket("token", "ticket-1", "in_progress", "transition_001", undefined, fetcher);
    await requestStaffAction("token", "ticket-1", "request_escalation", "Synthetic review", "request_001", fetcher);
    expect(bodies).toEqual([
      { status: "in_progress", actionId: "transition_001" },
      { type: "request_escalation", reason: "Synthetic review", actionId: "request_001" },
    ]);
    expect(JSON.stringify(bodies)).not.toMatch(/departmentId|assignedStaffId|priority|escalated/u);
  });

  it.each([[401, "authentication"], [403, "permission"], [404, "not_found"], [409, "conflict"], [422, "validation"], [503, "backend"]] as const)("maps HTTP %s to %s", async (status, code) => {
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000");
    await expect(loadStaffTickets("token", {}, vi.fn(async () => response({}, status)))).rejects.toMatchObject({ code });
  });

  it("prevents duplicate mutation calls while pending", async () => {
    const guard = createSubmissionGuard();
    let release!: () => void;
    const pending = new Promise<void>((resolve) => { release = resolve; });
    const action = vi.fn(async () => pending);
    const first = guard(action);
    await expect(guard(action)).resolves.toBeUndefined();
    expect(action).toHaveBeenCalledTimes(1);
    release();
    await first;
  });
});
