import type { Locale } from "./i18n";

export type RegistrationInput = {
  email: string;
  displayName: string;
  password: string;
  confirmPassword: string;
  locale: Locale;
  termsAccepted: boolean;
};

export type RegistrationField =
  | "email"
  | "displayName"
  | "password"
  | "confirmPassword"
  | "locale"
  | "termsAccepted";

export type RegistrationValidationError = {
  field: RegistrationField;
  code:
    | "invalid_email"
    | "display_name_required"
    | "display_name_too_long"
    | "password_weak"
    | "password_mismatch"
    | "terms_required"
    | "invalid_locale";
};

export class RegistrationInputError extends Error {
  constructor(public readonly errors: readonly RegistrationValidationError[]) {
    super("invalid_registration_input");
  }
}

export type RegistrationAuthErrorCode =
  | "duplicate_email"
  | "invalid_email"
  | "weak_password"
  | "unavailable"
  | "unexpected";

export type ProfileCompletionInput = {
  displayName: string;
  locale: Locale;
  termsAccepted: boolean;
};

export function validateRegistrationInput(value: unknown): RegistrationInput {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new RegistrationInputError([
      { field: "email", code: "invalid_email" },
    ]);
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set([
    "email",
    "displayName",
    "password",
    "confirmPassword",
    "locale",
    "termsAccepted",
  ]);
  if (Object.keys(record).some((key) => !allowed.has(key))) {
    throw new RegistrationInputError([
      { field: "email", code: "invalid_email" },
    ]);
  }

  const errors: RegistrationValidationError[] = [];
  const email = typeof record.email === "string" ? record.email.trim() : "";
  const displayName =
    typeof record.displayName === "string"
      ? record.displayName.trim().replace(/\s+/gu, " ")
      : "";
  const password = typeof record.password === "string" ? record.password : "";
  const confirmPassword =
    typeof record.confirmPassword === "string" ? record.confirmPassword : "";

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/u.test(email)) {
    errors.push({ field: "email", code: "invalid_email" });
  }
  if (!displayName) {
    errors.push({ field: "displayName", code: "display_name_required" });
  } else if (displayName.length > 100) {
    errors.push({ field: "displayName", code: "display_name_too_long" });
  }
  if (
    password.length < 8 ||
    !/[A-Za-z]/u.test(password) ||
    !/[0-9]/u.test(password)
  ) {
    errors.push({ field: "password", code: "password_weak" });
  }
  if (password !== confirmPassword) {
    errors.push({ field: "confirmPassword", code: "password_mismatch" });
  }
  if (record.locale !== "en" && record.locale !== "my") {
    errors.push({ field: "locale", code: "invalid_locale" });
  }
  if (record.termsAccepted !== true) {
    errors.push({ field: "termsAccepted", code: "terms_required" });
  }
  if (errors.length) throw new RegistrationInputError(errors);

  return {
    email,
    displayName,
    password,
    confirmPassword,
    locale: record.locale as Locale,
    termsAccepted: true,
  };
}

export function mapRegistrationAuthError(error: unknown): RegistrationAuthErrorCode {
  const code =
    typeof error === "object" && error !== null && "code" in error
      ? String((error as { code?: unknown }).code)
      : "";
  if (code === "auth/email-already-in-use") return "duplicate_email";
  if (code === "auth/invalid-email") return "invalid_email";
  if (code === "auth/weak-password") return "weak_password";
  if (
    code === "auth/network-request-failed" ||
    code === "auth/too-many-requests"
  ) {
    return "unavailable";
  }
  return "unexpected";
}

export function validateProfileCompletionInput(value: unknown): ProfileCompletionInput {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new RegistrationInputError([
      { field: "displayName", code: "display_name_required" },
    ]);
  }
  const record = value as Record<string, unknown>;
  const allowed = new Set(["displayName", "locale", "termsAccepted"]);
  if (Object.keys(record).some((key) => !allowed.has(key))) {
    throw new RegistrationInputError([
      { field: "displayName", code: "display_name_required" },
    ]);
  }
  const displayName =
    typeof record.displayName === "string"
      ? record.displayName.trim().replace(/\s+/gu, " ")
      : "";
  const errors: RegistrationValidationError[] = [];
  if (!displayName) {
    errors.push({ field: "displayName", code: "display_name_required" });
  } else if (displayName.length > 100) {
    errors.push({ field: "displayName", code: "display_name_too_long" });
  }
  if (record.locale !== "en" && record.locale !== "my") {
    errors.push({ field: "locale", code: "invalid_locale" });
  }
  if (record.termsAccepted !== true) {
    errors.push({ field: "termsAccepted", code: "terms_required" });
  }
  if (errors.length) throw new RegistrationInputError(errors);
  return {
    displayName,
    locale: record.locale as Locale,
    termsAccepted: true,
  };
}
