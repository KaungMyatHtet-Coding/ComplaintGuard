import { describe, expect, it } from "vitest";

import {
  RegistrationInputError,
  mapRegistrationAuthError,
  validateProfileCompletionInput,
  validateRegistrationInput,
} from "./registration";

const valid = {
  email: "customer@example.test",
  displayName: "  Synthetic   Customer ",
  password: "StrongPass1",
  confirmPassword: "StrongPass1",
  locale: "my",
  termsAccepted: true,
} as const;

describe("registration validation", () => {
  it("normalizes valid input without changing the password", () => {
    expect(validateRegistrationInput(valid)).toEqual({
      ...valid,
      displayName: "Synthetic Customer",
    });
  });

  it.each([
    ["email", { email: "not-an-email" }],
    ["display name", { displayName: "" }],
    ["weak password", { password: "short", confirmPassword: "short" }],
    ["password confirmation", { confirmPassword: "Different1" }],
    ["terms", { termsAccepted: false }],
    ["locale", { locale: "fr" }],
  ])("rejects invalid %s", (_name, changes) => {
    expect(() => validateRegistrationInput({ ...valid, ...changes })).toThrow(
      RegistrationInputError,
    );
  });

  it("rejects extra authority fields", () => {
    expect(() =>
      validateRegistrationInput({ ...valid, role: "admin", uid: "uid" }),
    ).toThrow(RegistrationInputError);
  });

  it("keeps recovery input limited to profile fields", () => {
    expect(
      validateProfileCompletionInput({
        displayName: "Customer",
        locale: "en",
        termsAccepted: true,
      }),
    ).toEqual({ displayName: "Customer", locale: "en", termsAccepted: true });
    expect(() =>
      validateProfileCompletionInput({
        displayName: "Customer",
        locale: "en",
        termsAccepted: true,
        uid: "injected",
      }),
    ).toThrow(RegistrationInputError);
  });

  it("maps Firebase errors to safe customer-facing categories", () => {
    expect(mapRegistrationAuthError({ code: "auth/email-already-in-use" })).toBe(
      "duplicate_email",
    );
    expect(mapRegistrationAuthError({ code: "auth/weak-password" })).toBe(
      "weak_password",
    );
    expect(mapRegistrationAuthError({ code: "auth/network-request-failed" })).toBe(
      "unavailable",
    );
    expect(mapRegistrationAuthError(new Error("private detail"))).toBe("unexpected");
  });
});
