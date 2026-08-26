import type { User } from "firebase/auth";

import type { Locale } from "./i18n";
import { resolveLocalMlApiBaseUrl } from "./runtime-environment";

export type CustomerProfileCompletionInput = {
  displayName: string;
  locale: Locale;
  termsAccepted?: boolean;
};

export type CustomerProfileCompletion = {
  status: "created" | "existing";
  profile: {
    uid: string;
    email: string;
    displayName: string;
    locale: Locale;
    role: "customer";
    departmentId: null;
    active: true;
  };
};

export type CustomerProfileErrorCode =
  | "not_authenticated"
  | "invalid_input"
  | "environment"
  | "auth"
  | "conflict"
  | "validation"
  | "unavailable"
  | "unexpected";

export class CustomerProfileError extends Error {
  constructor(public readonly code: CustomerProfileErrorCode) {
    super(code);
  }
}

export function validateCustomerProfileInput(
  value: unknown,
): CustomerProfileCompletionInput {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new CustomerProfileError("invalid_input");
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set(["displayName", "locale", "termsAccepted"]);
  if (Object.keys(record).some((key) => !allowed.has(key))) {
    throw new CustomerProfileError("invalid_input");
  }
  if (typeof record.displayName !== "string") {
    throw new CustomerProfileError("invalid_input");
  }
  const displayName = record.displayName.trim().replace(/\s+/gu, " ");
  if (!displayName || displayName.length > 100) {
    throw new CustomerProfileError("invalid_input");
  }
  if (record.locale !== "en" && record.locale !== "my") {
    throw new CustomerProfileError("invalid_input");
  }
  if (
    record.termsAccepted !== undefined &&
    typeof record.termsAccepted !== "boolean"
  ) {
    throw new CustomerProfileError("invalid_input");
  }
  return {
    displayName,
    locale: record.locale,
    ...(record.termsAccepted === undefined
      ? {}
      : { termsAccepted: record.termsAccepted }),
  };
}

function parseCompletionResponse(
  value: unknown,
  user: User,
): CustomerProfileCompletion {
  if (!value || typeof value !== "object") {
    throw new CustomerProfileError("unexpected");
  }
  const record = value as Record<string, unknown>;
  const profile = record.profile;
  if (
    (record.status !== "created" && record.status !== "existing") ||
    !profile ||
    typeof profile !== "object"
  ) {
    throw new CustomerProfileError("unexpected");
  }
  const candidate = profile as Record<string, unknown>;
  if (
    typeof candidate.uid !== "string" ||
    typeof candidate.email !== "string" ||
    typeof candidate.displayName !== "string" ||
    (candidate.locale !== "en" && candidate.locale !== "my") ||
    candidate.role !== "customer" ||
    candidate.departmentId !== null ||
    candidate.active !== true
  ) {
    throw new CustomerProfileError("unexpected");
  }
  const completion: CustomerProfileCompletion = {
    status: record.status,
    profile: {
      uid: candidate.uid,
      email: candidate.email,
      displayName: candidate.displayName,
      locale: candidate.locale,
      role: "customer",
      departmentId: null,
      active: true,
    },
  };
  if (
    completion.profile.uid !== user.uid ||
    completion.profile.email !== user.email
  ) {
    throw new CustomerProfileError("unexpected");
  }
  return completion;
}

export async function completeCustomerProfile(
  user: User | null,
  input: unknown,
  fetcher: typeof fetch = fetch,
): Promise<CustomerProfileCompletion> {
  if (!user) throw new CustomerProfileError("not_authenticated");
  const payload = validateCustomerProfileInput(input);
  let baseUrl: string;
  try {
    baseUrl = resolveLocalMlApiBaseUrl();
  } catch {
    throw new CustomerProfileError("environment");
  }
  let token: string;
  try {
    token = await user.getIdToken(true);
  } catch {
    throw new CustomerProfileError("auth");
  }
  let response: Response;
  try {
    response = await fetcher(`${baseUrl}/auth/customer-profile`, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(payload),
    });
  } catch {
    throw new CustomerProfileError("unavailable");
  }
  if (response.status === 401) throw new CustomerProfileError("auth");
  if (response.status === 409) throw new CustomerProfileError("conflict");
  if (response.status === 422) throw new CustomerProfileError("validation");
  if (response.status === 503) throw new CustomerProfileError("unavailable");
  if (!response.ok) throw new CustomerProfileError("unexpected");
  try {
    return parseCompletionResponse(await response.json(), user);
  } catch (error) {
    if (error instanceof CustomerProfileError) throw error;
    throw new CustomerProfileError("unexpected");
  }
}
