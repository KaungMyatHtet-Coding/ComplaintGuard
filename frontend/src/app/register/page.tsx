"use client";

import { createUserWithEmailAndPassword } from "firebase/auth";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { AppHeader } from "@/components/app-header";
import { useApp } from "@/components/app-provider";
import { getFirebaseServices, hasFirebaseConfig } from "@/lib/firebase";
import {
  RegistrationInputError,
  mapRegistrationAuthError,
  validateProfileCompletionInput,
  validateRegistrationInput,
  type RegistrationField,
  type RegistrationInput,
} from "@/lib/registration";

type FieldErrors = Partial<Record<RegistrationField, string>>;

const emptyInput: RegistrationInput = {
  email: "",
  displayName: "",
  password: "",
  confirmPassword: "",
  locale: "en",
  termsAccepted: false,
};

export default function RegisterPage() {
  const router = useRouter();
  const {
    completeCustomerProfile,
    errorCode,
    locale,
    profile,
    profileCompletionPending,
    setLocale,
    status,
    t,
  } = useApp();
  const [input, setInput] = useState<RegistrationInput>(() => ({
    ...emptyInput,
    locale,
  }));
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [accountCreated, setAccountCreated] = useState(false);
  const [completionInput, setCompletionInput] = useState<{
    displayName: string;
    locale: "en" | "my";
    termsAccepted: boolean;
  } | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const errorSummaryRef = useRef<HTMLDivElement>(null);
  const completionStartedRef = useRef(false);

  const recovery = status === "profile_incomplete" && !accountCreated;
  const setupFailure =
    accountCreated &&
    (status === "profile_incomplete" ||
      (status === "profile_unavailable" &&
        errorCode === "profile_completion_unavailable"));
  const supportRequired =
    status === "profile_inactive" || status === "profile_malformed";

  useEffect(() => {
    if (profile && status === "authenticated") router.replace("/dashboard");
  }, [profile, router, status]);

  useEffect(() => {
    if (!accountCreated || !completionInput || completionStartedRef.current) return;
    if (status !== "profile_incomplete") return;
    completionStartedRef.current = true;
    void completeCustomerProfile(completionInput);
  }, [accountCreated, completeCustomerProfile, completionInput, status]);

  function focusErrors(errors: FieldErrors, message?: string) {
    setFieldErrors(errors);
    setFormError(message ?? null);
    window.requestAnimationFrame(() => errorSummaryRef.current?.focus());
  }

  function errorMessage(code: string): string {
    const messages: Record<string, string> = {
      invalid_email: t("invalidEmail"),
      display_name_required: t("displayNameRequired"),
      display_name_too_long: t("displayNameTooLong"),
      password_weak: t("weakPassword"),
      password_mismatch: t("passwordMismatch"),
      terms_required: t("termsRequired"),
      invalid_locale: t("invalidLocale"),
    };
    return messages[code] ?? t("registrationUnexpected");
  }

  function toFieldErrors(error: RegistrationInputError): FieldErrors {
    return Object.fromEntries(
      error.errors.map((item) => [item.field, errorMessage(item.code)]),
    );
  }

  function updateField<K extends keyof RegistrationInput>(
    key: K,
    value: RegistrationInput[K],
  ) {
    setInput((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => ({ ...current, [key]: undefined }));
    setFormError(null);
  }

  async function submitRegistration(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || profileCompletionPending) return;
    let checked: RegistrationInput;
    try {
      checked = validateRegistrationInput(input);
    } catch (error) {
      if (error instanceof RegistrationInputError) {
        focusErrors(toFieldErrors(error), t("registrationErrorSummary"));
      } else {
        focusErrors({}, t("registrationUnexpected"));
      }
      return;
    }
    if (!hasFirebaseConfig()) {
      focusErrors({}, t("configMissing"));
      return;
    }
    setSubmitting(true);
    setFieldErrors({});
    setFormError(null);
    try {
      const { auth } = getFirebaseServices();
      await createUserWithEmailAndPassword(auth, checked.email, checked.password);
      setLocale(checked.locale);
      setCompletionInput({
        displayName: checked.displayName,
        locale: checked.locale,
        termsAccepted: checked.termsAccepted,
      });
      setAccountCreated(true);
      setInput((current) => ({
        ...current,
        password: "",
        confirmPassword: "",
      }));
    } catch (error) {
      const mapped = mapRegistrationAuthError(error);
      const message =
        mapped === "duplicate_email"
          ? t("duplicateAccount")
          : mapped === "invalid_email"
            ? t("invalidEmail")
            : mapped === "weak_password"
              ? t("weakPassword")
              : mapped === "unavailable"
                ? t("registrationUnavailable")
                : t("registrationUnexpected");
      focusErrors(
        mapped === "invalid_email" ? { email: message } : {},
        message,
      );
    } finally {
      setSubmitting(false);
    }
  }

  async function submitRecovery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting || profileCompletionPending) return;
    let checked: { displayName: string; locale: "en" | "my"; termsAccepted: boolean };
    try {
      checked = validateProfileCompletionInput({
        displayName: input.displayName,
        locale: input.locale,
        termsAccepted: input.termsAccepted,
      });
    } catch (error) {
      if (error instanceof RegistrationInputError) {
        focusErrors(toFieldErrors(error), t("registrationErrorSummary"));
      }
      return;
    }
    setSubmitting(true);
    completionStartedRef.current = true;
    await completeCustomerProfile({
      displayName: checked.displayName,
      locale: checked.locale,
      termsAccepted: checked.termsAccepted,
    });
    setSubmitting(false);
  }

  async function retrySetup() {
    if (!completionInput || isBusy) return;
    setSubmitting(true);
    await completeCustomerProfile(completionInput);
    setSubmitting(false);
  }

  const isBusy = submitting || profileCompletionPending || status === "loading";
  const showForm =
    !supportRequired &&
    status !== "configuration_missing" &&
    (recovery || (!accountCreated && status === "unauthenticated"));
  const title = recovery ? t("finishSetupTitle") : t("registerTitle");
  const lead = recovery ? t("finishSetupLead") : t("registerLead");

  return (
    <>
      <AppHeader />
      <main className="auth-page min-h-[calc(100vh-4.5rem)] px-4 py-10 sm:px-6 lg:px-8">
        <div className="mx-auto w-full max-w-xl">
          <div className="mb-8 text-center">
            <h1 className="text-3xl font-extrabold tracking-tight text-gray-900">{title}</h1>
            <p className="mt-3 text-gray-600">{lead}</p>
          </div>

          {formError || supportRequired || status === "configuration_missing" ? (
            <div
              ref={errorSummaryRef}
              className="auth-error-summary mb-6 rounded-xl border p-4 text-sm"
              role="alert"
              tabIndex={-1}
            >
              <strong className="block font-bold">{formError ?? (supportRequired ? t("supportRequired") : t("configMissing"))}</strong>
              {formError ? <span className="mt-1 block">{t("registrationErrorSummary")}</span> : null}
            </div>
          ) : null}

          {setupFailure ? (
            <div className="mb-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900" role="status">
              <strong className="block font-bold">{t("setupIncomplete")}</strong>
              <span className="mt-1 block">{t("setupTemporaryFailure")}</span>
              <button type="button" onClick={() => void retrySetup()} disabled={isBusy} className="mt-4 rounded-lg bg-black px-4 py-2 font-bold text-white disabled:cursor-not-allowed disabled:opacity-60">{t("retrySetup")}</button>
            </div>
          ) : null}

          {accountCreated && status === "profile_completion_pending" ? (
            <p className="mb-6 rounded-xl bg-gray-100 p-4 text-sm text-gray-700" role="status">{t("finishingSetup")}</p>
          ) : null}

          {showForm && !accountCreated ? (
            <form onSubmit={recovery ? submitRecovery : submitRegistration} noValidate className="auth-form space-y-5 rounded-2xl border p-5 shadow-sm sm:p-8">
              {!recovery ? (
                <div>
                  <label htmlFor="register-email" className="mb-2 block text-sm font-bold text-gray-700">{t("email")}</label>
                  <input id="register-email" name="email" type="email" autoComplete="email" value={input.email} onChange={(event) => updateField("email", event.target.value)} aria-invalid={Boolean(fieldErrors.email)} aria-describedby="register-email-help register-email-error" className="auth-input" />
                  <p id="register-email-help" className="mt-2 text-xs text-gray-500">{t("registerEmailHelp")}</p>
                  {fieldErrors.email ? <p id="register-email-error" className="mt-1 text-sm text-red-700">{fieldErrors.email}</p> : null}
                </div>
              ) : null}

              <div>
                <label htmlFor="register-display-name" className="mb-2 block text-sm font-bold text-gray-700">{t("displayName")}</label>
                <input id="register-display-name" name="name" type="text" autoComplete="name" value={input.displayName} onChange={(event) => updateField("displayName", event.target.value)} aria-invalid={Boolean(fieldErrors.displayName)} className="auth-input" />
                <p className="mt-2 text-xs text-gray-500">{t("displayNameHelp")}</p>
                {fieldErrors.displayName ? <p className="mt-1 text-sm text-red-700">{fieldErrors.displayName}</p> : null}
              </div>

              {!recovery ? (
                <>
                  <div>
                    <label htmlFor="register-password" className="mb-2 block text-sm font-bold text-gray-700">{t("password")}</label>
                    <div className="auth-password-row">
                      <input id="register-password" name="password" type={showPassword ? "text" : "password"} autoComplete="new-password" value={input.password} onChange={(event) => updateField("password", event.target.value)} aria-invalid={Boolean(fieldErrors.password)} className="auth-input" />
                      <button type="button" className="auth-password-toggle" aria-label={showPassword ? t("hidePassword") : t("showPassword")} onClick={() => setShowPassword((value) => !value)}>{showPassword ? t("hidePassword") : t("showPassword")}</button>
                    </div>
                    <p className="mt-2 text-xs text-gray-500">{t("passwordRequirements")}</p>
                    {fieldErrors.password ? <p className="mt-1 text-sm text-red-700">{fieldErrors.password}</p> : null}
                  </div>
                  <div>
                    <label htmlFor="register-confirm-password" className="mb-2 block text-sm font-bold text-gray-700">{t("confirmPassword")}</label>
                    <div className="auth-password-row">
                      <input id="register-confirm-password" name="confirmPassword" type={showConfirmation ? "text" : "password"} autoComplete="new-password" value={input.confirmPassword} onChange={(event) => updateField("confirmPassword", event.target.value)} aria-invalid={Boolean(fieldErrors.confirmPassword)} className="auth-input" />
                      <button type="button" className="auth-password-toggle" aria-label={showConfirmation ? t("hidePasswordConfirmation") : t("showPasswordConfirmation")} onClick={() => setShowConfirmation((value) => !value)}>{showConfirmation ? t("hidePasswordConfirmation") : t("showPasswordConfirmation")}</button>
                    </div>
                    {fieldErrors.confirmPassword ? <p className="mt-1 text-sm text-red-700">{fieldErrors.confirmPassword}</p> : null}
                  </div>
                </>
              ) : null}

              <fieldset>
                <legend className="mb-2 block text-sm font-bold text-gray-700">{t("language")}</legend>
                <div className="flex gap-2">
                  {(["en", "my"] as const).map((value) => (
                    <label key={value} className="flex flex-1 cursor-pointer items-center gap-2 rounded-xl border border-gray-300 px-4 py-3 text-sm font-semibold text-gray-700 has-[:checked]:border-black has-[:checked]:bg-gray-100">
                      <input type="radio" name="locale" value={value} checked={input.locale === value} onChange={() => updateField("locale", value)} />
                      {value === "en" ? t("english") : t("myanmar")}
                    </label>
                  ))}
                </div>
                {fieldErrors.locale ? <p className="mt-1 text-sm text-red-700">{fieldErrors.locale}</p> : null}
              </fieldset>

              <label className="flex items-start gap-3 text-sm text-gray-700">
                <input type="checkbox" name="termsAccepted" checked={input.termsAccepted} onChange={(event) => updateField("termsAccepted", event.target.checked)} aria-invalid={Boolean(fieldErrors.termsAccepted)} className="mt-1 h-4 w-4" />
                <span>{t("termsAcceptance")}</span>
              </label>
              {fieldErrors.termsAccepted ? <p className="text-sm text-red-700">{fieldErrors.termsAccepted}</p> : null}

              <button type="submit" disabled={isBusy} className="auth-submit">
                {isBusy ? (recovery ? t("finishingSetup") : t("registering")) : recovery ? t("finishSetup") : t("register")}
              </button>
            </form>
          ) : null}

          <div className="mt-6 text-center text-sm text-gray-600">
            <Link href="/login" className="font-bold underline underline-offset-4 hover:text-black">{t("backToLogin")}</Link>
          </div>
        </div>
      </main>
    </>
  );
}
