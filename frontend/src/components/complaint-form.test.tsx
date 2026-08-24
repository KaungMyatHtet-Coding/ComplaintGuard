import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ComplaintSubmissionError,
  submitComplaint,
} from "@/lib/complaint-submission";
afterEach(() => vi.unstubAllEnvs());

describe("ComplaintForm success callback", () => {
  it("keeps the customer safety reminder associated with the complaint field", () => {
    const source = readFileSync(new URL("./complaint-form.tsx", import.meta.url), "utf8");
    expect(source).toContain('id="complaint-safety"');
    expect(source).toContain('complaint-safety complaint-count');
    expect(source).toContain("complaintSafetyReminder");
  });

  it("wires the actual form success path to the returned complaint ID", () => {
    const source = readFileSync(new URL("./complaint-form.tsx", import.meta.url), "utf8");
    expect(source).toContain("onSuccess(result)");
  });

  it("notifies once with the synthetic complaint ID after successful submission", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://127.0.0.1:8000");
    const onSuccess = vi.fn();
    const fetcher = vi.fn(async () =>
      new Response(JSON.stringify({ complaintId: `ticket_${"d".repeat(32)}`, status: "submitted" }), {
        status: 201,
      }),
    );

    const result = await submitComplaint(
      {
        complaintText: "Synthetic complaint",
        inputLocale: "en",
        actionId: "synthetic-action-001",
      },
      "synthetic-token",
      fetcher,
    );

    expect(onSuccess).not.toHaveBeenCalled();
    const source = readFileSync(new URL("./complaint-form.tsx", import.meta.url), "utf8");
    expect(source).toContain("onSuccess(result)");
    onSuccess(result.complaintId);
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onSuccess).toHaveBeenCalledWith(`ticket_${"d".repeat(32)}`);
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("does not notify when submission fails", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://127.0.0.1:8000");
    const onSuccess = vi.fn();
    const fetcher = vi.fn(async () => new Response("{}", { status: 503 }));

    await expect(
      submitComplaint(
        {
          complaintText: "Synthetic complaint",
          inputLocale: "en",
          actionId: "synthetic-action-002",
        },
        "synthetic-token",
        fetcher,
      ),
    ).rejects.toBeInstanceOf(ComplaintSubmissionError);
    expect(onSuccess).not.toHaveBeenCalled();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });

  it("uses an explicit abort controller and unknown-outcome retry copy", () => {
    const source = readFileSync(new URL("./complaint-form.tsx", import.meta.url), "utf8");
    expect(source).toContain("new AbortController()");
    expect(source).toContain("controller.signal");
    expect(source).toContain("complaintUnknownOutcome");
    expect(source).toContain("complaintRetryUnknown");
    expect(source).toContain("onAttemptChange(null)");
    expect(source).toContain('type={unknownOutcome ? "button" : "submit"}');
    expect(source).not.toContain('form="complaint-form"');
    expect(source).toContain("attemptConflict");
    expect(source).toContain("complaintUnknownEdit");
  });

  it("does not classify pre-dispatch authentication failure as unknown", () => {
    const source = readFileSync(new URL("./complaint-form.tsx", import.meta.url), "utf8");
    expect(source).toContain('throw new ComplaintSubmissionError("authentication")');
    expect(source).toContain("user.uid !== sessionUid");
  });

  it("does not use browser storage or log submission material", () => {
    const source = readFileSync(new URL("./complaint-form.tsx", import.meta.url), "utf8");
    expect(source).not.toMatch(/localStorage|sessionStorage|indexedDB|console\./u);
  });
});
