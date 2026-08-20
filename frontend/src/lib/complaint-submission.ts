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

export type ComplaintErrorCode =
  | "required"
  | "too_long"
  | "authentication"
  | "permission"
  | "backend"
  | "unexpected";

export class ComplaintSubmissionError extends Error {
  constructor(public readonly code: ComplaintErrorCode) {
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

type Fetcher = typeof fetch;

export async function submitComplaint(
  input: ComplaintInput,
  idToken: string,
  fetcher: Fetcher = fetch,
): Promise<ComplaintSuccess> {
  let apiUrl: string;
  try {
    apiUrl = resolveLocalMlApiBaseUrl();
  } catch {
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
    });
  } catch {
    throw new ComplaintSubmissionError("backend");
  }

  if (response.status === 401) {
    throw new ComplaintSubmissionError("authentication");
  }
  if (response.status === 403) {
    throw new ComplaintSubmissionError("permission");
  }
  if (!response.ok) throw new ComplaintSubmissionError("backend");

  const value: unknown = await response.json();
  if (
    !value ||
    typeof value !== "object" ||
    typeof (value as Record<string, unknown>).complaintId !== "string" ||
    (value as Record<string, unknown>).status !== "submitted"
  ) {
    throw new ComplaintSubmissionError("unexpected");
  }
  return value as ComplaintSuccess;
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
