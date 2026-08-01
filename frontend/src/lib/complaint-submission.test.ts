import { afterEach, describe, expect, it, vi } from "vitest";

import { createSubmissionGuard, submitComplaint, validateComplaintText } from "./complaint-submission";

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
  it("sends only allowed input and returns the reference ID", async () => {
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000/");
    const fetcher = vi.fn(async (_url: string | URL | Request, init?: RequestInit) => {
      expect(init?.headers).toEqual({ Authorization: "Bearer synthetic-token", "Content-Type": "application/json" });
      expect(JSON.parse(String(init?.body))).toEqual({ complaintText: "Synthetic complaint", inputLocale: "en" });
      return new Response(JSON.stringify({ complaintId: "ticket-001", status: "submitted" }), { status: 201 });
    });
    await expect(submitComplaint({ complaintText: "Synthetic complaint", inputLocale: "en" }, "synthetic-token", fetcher)).resolves.toEqual({ complaintId: "ticket-001", status: "submitted" });
  });

  it.each([[401, "authentication"], [403, "permission"], [503, "backend"]] as const)("maps HTTP %s to %s", async (status, code) => {
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://localhost:8000");
    const fetcher = vi.fn(async () => new Response("{}", { status }));
    await expect(submitComplaint({ complaintText: "Synthetic complaint", inputLocale: "my" }, "token", fetcher)).rejects.toMatchObject({ code });
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
});
