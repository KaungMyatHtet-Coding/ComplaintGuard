import { afterEach, describe, expect, it, vi } from "vitest";

import {
  COMPLAINT_REFERENCE_PATTERN,
  canReuseComplaintAttempt,
  createSubmissionGuard,
  parseComplaintSuccess,
  submitComplaint,
  validateComplaintText,
} from "./complaint-submission";

afterEach(() => vi.unstubAllEnvs());

describe("complaint validation", () => {
  it("trims and normalizes valid English and Myanmar complaints", () => {
    expect(validateComplaintText("  Synthetic   complaint  ")).toEqual({ valid: true, complaintText: "Synthetic complaint" });
    expect(validateComplaintText("  ငွေလွှဲမှု   မရောက်ပါ  ")).toEqual({ valid: true, complaintText: "ငွေလွှဲမှု မရောက်ပါ" });
  });

  it("rejects empty, whitespace-only, and over-limit complaints", () => {
    expect(validateComplaintText("")).toEqual({ valid: false, code: "required" });
    expect(validateComplaintText(" \t\n ")).toEqual({ valid: false, code: "required" });
    expect(validateComplaintText("x".repeat(5_001))).toEqual({ valid: false, code: "too_long" });
  });
});

describe("trusted complaint API client", () => {
  it("does not dispatch an already-aborted request", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000");
    const controller = new AbortController();
    controller.abort();
    const fetcher = vi.fn();
    await expect(
      submitComplaint({ complaintText: "Synthetic complaint", inputLocale: "en", actionId: "same-action" }, "token", fetcher, controller.signal),
    ).rejects.toMatchObject({ code: "backend", outcome: "confirmed_failure" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("sends only allowed input and returns the reference ID", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000/");
    const signal = new AbortController().signal;
    const fetcher = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      expect(init?.headers).toEqual({ Authorization: "Bearer synthetic-token", "Content-Type": "application/json" });
      expect(JSON.parse(String(init?.body))).toEqual({ complaintText: "Synthetic complaint", inputLocale: "en", actionId: "submission-action-001" });
      expect(init?.signal).toBe(signal);
      return new Response(JSON.stringify({ complaintId: `ticket_${"a".repeat(32)}`, status: "submitted" }), { status: 201 });
    });
    await expect(submitComplaint({ complaintText: "Synthetic complaint", inputLocale: "en", actionId: "submission-action-001" }, "synthetic-token", fetcher, signal)).resolves.toEqual({ complaintId: `ticket_${"a".repeat(32)}`, status: "submitted" });
  });

  it.each([[401, "authentication", "confirmed_failure"], [403, "permission", "confirmed_failure"], [422, "backend", "confirmed_failure"], [503, "backend", "unknown"]] as const)("maps HTTP %s to %s", async (status, code, outcome) => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000");
    const fetcher = vi.fn(async () => new Response("{}", { status }));
    await expect(submitComplaint({ complaintText: "Synthetic complaint", inputLocale: "my", actionId: "submission-action-001" }, "token", fetcher)).rejects.toMatchObject({ code, outcome });
  });

  it("does not fetch when the API URL is missing", async () => {
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", undefined);
    const fetcher = vi.fn();
    await expect(
      submitComplaint({ complaintText: "Synthetic complaint", inputLocale: "en", actionId: "action" }, "secret-token", fetcher),
    ).rejects.toMatchObject({ code: "backend" });
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("prevents duplicate actions while submission is pending", async () => {
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

  it("requires the exact minimal success response and backend ticket reference", () => {
    const valid = { complaintId: `ticket_${"b".repeat(32)}`, status: "submitted" };
    expect(parseComplaintSuccess(valid)).toEqual(valid);
    expect(COMPLAINT_REFERENCE_PATTERN.test(valid.complaintId)).toBe(true);
    for (const value of [
      { ...valid, extra: "private" },
      { complaintId: "ticket-short", status: "submitted" },
      { complaintId: valid.complaintId, status: "created" },
      Object.create({ complaintId: valid.complaintId, status: "submitted" }),
    ]) {
      expect(() => parseComplaintSuccess(value)).toThrow();
    }
  });

  it("rejects accessor, non-enumerable, and symbol response fields", () => {
    const validId = `ticket_${"c".repeat(32)}`;
    const accessor = { complaintId: validId, status: "submitted" } as Record<string, unknown>;
    Object.defineProperty(accessor, "status", { enumerable: true, get: () => "submitted" });
    const hidden = { complaintId: validId, status: "submitted" } as Record<string, unknown>;
    Object.defineProperty(hidden, "private", { enumerable: false, value: "secret" });
    const symbol = { complaintId: validId, status: "submitted", [Symbol("private")]: "secret" };
    for (const value of [accessor, hidden, symbol]) expect(() => parseComplaintSuccess(value)).toThrow();
  });

  it("classifies transport and response-body failures as unknown outcomes", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000");
    await expect(submitComplaint({ complaintText: "Synthetic complaint", inputLocale: "en", actionId: "same-action" }, "token", vi.fn(async () => { throw new Error("network"); }))).rejects.toMatchObject({ code: "backend", outcome: "unknown" });
    await expect(submitComplaint({ complaintText: "Synthetic complaint", inputLocale: "en", actionId: "same-action" }, "token", vi.fn(async () => new Response("not-json", { status: 201 })))).rejects.toMatchObject({ code: "unexpected", outcome: "unknown" });
  });

  it("reuses an attempt only for the same normalized complaint and locale", () => {
    const attempt = {
      sessionUid: "customer-1",
      complaintText: "Synthetic complaint",
      inputLocale: "en" as const,
      actionId: "same-action",
      phase: "unknown" as const,
    };
    expect(canReuseComplaintAttempt(attempt, "  Synthetic   complaint  ", "en")).toBe(true);
    expect(canReuseComplaintAttempt(attempt, "Synthetic changed complaint", "en")).toBe(false);
    expect(canReuseComplaintAttempt(attempt, "Synthetic complaint", "my")).toBe(false);
  });
});
