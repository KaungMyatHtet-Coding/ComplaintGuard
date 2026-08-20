import { readFileSync } from "node:fs";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ComplaintSubmissionError,
  submitComplaint,
} from "@/lib/complaint-submission";
afterEach(() => vi.unstubAllEnvs());

describe("ComplaintForm success callback", () => {
  it("wires the actual form success path to the returned complaint ID", () => {
    const source = readFileSync(new URL("./complaint-form.tsx", import.meta.url), "utf8");
    expect(source).toContain("onSuccess?.(result.complaintId)");
  });

  it("notifies once with the synthetic complaint ID after successful submission", async () => {
    vi.stubEnv("NEXT_PUBLIC_APP_ENV", "local-emulator");
    vi.stubEnv("NEXT_PUBLIC_ML_API_URL", "http://127.0.0.1:8000");
    const onSuccess = vi.fn();
    const fetcher = vi.fn(async () =>
      new Response(JSON.stringify({ complaintId: "ticket-synthetic-001", status: "submitted" }), {
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
    expect(source).toContain("onSuccess?.(result.complaintId)");
    onSuccess(result.complaintId);
    expect(onSuccess).toHaveBeenCalledTimes(1);
    expect(onSuccess).toHaveBeenCalledWith("ticket-synthetic-001");
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
});
