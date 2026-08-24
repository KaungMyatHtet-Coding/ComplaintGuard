import type { Locale } from "./i18n";
import { resolveLocalMlApiBaseUrl } from "./runtime-environment";

export const MAX_COMPLAINT_LENGTH = 5_000;

export type ComplaintInput = {
  complaintText: string;
  inputLocale: Locale;
  actionId: string;
};

export type ComplaintSuccess = {
  complaintId: string;
  status: "submitted";
};

export const COMPLAINT_REFERENCE_PATTERN = /^ticket_[a-f0-9]{32}$/u;

export type ComplaintAttemptPhase = "editing" | "submitting" | "unknown";

export type ComplaintAttempt = {
  sessionUid: string;
  complaintText: string;
  inputLocale: Locale;
  actionId: string;
  phase: ComplaintAttemptPhase;
};

export type ComplaintErrorCode =
  | "required"
  | "too_long"
  | "authentication"
  | "permission"
  | "backend"
  | "unexpected";

export type ComplaintErrorOutcome = "confirmed_failure" | "unknown";

export class ComplaintSubmissionError extends Error {
  constructor(
    public readonly code: ComplaintErrorCode,
    public readonly outcome: ComplaintErrorOutcome = "confirmed_failure",
  ) {
    super(code);
  }
}

export function validateComplaintText(text: string):
  | { valid: true; complaintText: string }
  | { valid: false; code: "required" | "too_long" } {
  const complaintText = text.trim().replace(/\s+/gu, " ");
  if (!complaintText) return { valid: false, code: "required" };
  if (text.length > MAX_COMPLAINT_LENGTH) {
    return { valid: false, code: "too_long" };
  }
  return { valid: true, complaintText };
}

export function canReuseComplaintAttempt(attempt: ComplaintAttempt, text: string, locale: Locale): boolean {
  const checked = validateComplaintText(text);
  return checked.valid && attempt.inputLocale === locale && checked.complaintText === attempt.complaintText;
}

type Fetcher = typeof fetch;

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (!value || typeof value !== "object") return false;
  const prototype = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) return false;
  const keys = Reflect.ownKeys(value);
  if (keys.some((key) => typeof key !== "string")) return false;
  return keys.every((key) => {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    return Boolean(descriptor?.enumerable && "value" in descriptor);
  });
}

export function parseComplaintSuccess(value: unknown): ComplaintSuccess {
  try {
    if (!isPlainObject(value) || Object.keys(value).length !== 2) {
      throw new Error("invalid response shape");
    }
    const keys = Object.keys(value);
    if (!keys.includes("complaintId") || !keys.includes("status")) {
      throw new Error("invalid response keys");
    }
    const complaintId = Object.getOwnPropertyDescriptor(value, "complaintId");
    const status = Object.getOwnPropertyDescriptor(value, "status");
    if (
      !complaintId || !status ||
      typeof complaintId.value !== "string" ||
      !COMPLAINT_REFERENCE_PATTERN.test(complaintId.value) ||
      status.value !== "submitted"
    ) {
      throw new Error("invalid response values");
    }
    return { complaintId: complaintId.value, status: "submitted" };
  } catch (error) {
    if (error instanceof ComplaintSubmissionError) throw error;
    throw new ComplaintSubmissionError("unexpected", "unknown");
  }
}

export async function submitComplaint(
  input: ComplaintInput,
  idToken: string,
  fetcher: Fetcher = fetch,
  signal?: AbortSignal,
): Promise<ComplaintSuccess> {
  let apiUrl: string;
  try {
    apiUrl = resolveLocalMlApiBaseUrl();
  } catch {
    throw new ComplaintSubmissionError("backend");
  }

  if (signal?.aborted) {
    throw new ComplaintSubmissionError("backend");
  }

  let response: Response;
  try {
    response = await fetcher(`${apiUrl}/tickets`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${idToken}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        complaintText: input.complaintText,
        inputLocale: input.inputLocale,
        actionId: input.actionId,
      }),
      signal,
    });
  } catch {
    throw new ComplaintSubmissionError("backend", "unknown");
  }

  if (response.status === 401) {
    throw new ComplaintSubmissionError("authentication");
  }
  if (response.status === 403) {
    throw new ComplaintSubmissionError("permission");
  }
  if (!response.ok) {
    throw new ComplaintSubmissionError("backend", response.status >= 500 ? "unknown" : "confirmed_failure");
  }

  let value: unknown;
  try {
    value = await response.json();
  } catch {
    throw new ComplaintSubmissionError("unexpected", "unknown");
  }
  return parseComplaintSuccess(value);
}

export function createSubmissionGuard() {
  let pending = false;
  return async <T>(action: () => Promise<T>): Promise<T | undefined> => {
    if (pending) return undefined;
    pending = true;
    try {
      return await action();
    } finally {
      pending = false;
    }
  };
}
