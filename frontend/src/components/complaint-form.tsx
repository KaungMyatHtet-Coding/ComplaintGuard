"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { useApp } from "@/components/app-provider";
import {
  ComplaintSubmissionError,
  MAX_COMPLAINT_LENGTH,
  canReuseComplaintAttempt,
  createSubmissionGuard,
  submitComplaint,
  validateComplaintText,
  type ComplaintAttempt,
  type ComplaintAttemptPhase,
  type ComplaintErrorCode,
  type ComplaintSuccess,
} from "@/lib/complaint-submission";
import { getFirebaseServices } from "@/lib/firebase";

const errorKeys = {
  required: "complaintRequired",
  too_long: "complaintTooLong",
  authentication: "complaintAuthError",
  permission: "complaintPermissionError",
  backend: "complaintBackendError",
  unexpected: "complaintUnexpectedError",
} as const;

type ComplaintFormProps = {
  sessionUid: string;
  attempt: ComplaintAttempt | null;
  onAttemptChange: (attempt: ComplaintAttempt | null) => void;
  onSuccess: (result: ComplaintSuccess) => void;
  hideTitle?: boolean;
};

export function ComplaintForm({ sessionUid, attempt, onAttemptChange, onSuccess, hideTitle }: ComplaintFormProps) {
  const { locale, profile, t } = useApp();
  const [text, setText] = useState(attempt?.complaintText ?? "");
  const [pending, setPending] = useState(attempt?.phase === "submitting");
  const [errorCode, setErrorCode] = useState<ComplaintErrorCode | null>(null);
  const [unknownOutcome, setUnknownOutcome] = useState(attempt?.phase === "unknown");
  const [attemptConflict, setAttemptConflict] = useState(false);
  const guard = useMemo(() => createSubmissionGuard(), []);
  const actionId = useRef(attempt?.actionId ?? null);
  const attemptLocale = useRef(attempt?.inputLocale ?? locale);
  const controllerRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);
  const requestGenerationRef = useRef(0);
  const requestStartedRef = useRef(false);
  const textRef = useRef(text);
  const localeRef = useRef(locale);

  useEffect(() => {
    textRef.current = text;
  }, [text]);

  useEffect(() => {
    localeRef.current = locale;
  }, [locale]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      requestGenerationRef.current += 1;
      controllerRef.current?.abort();
      controllerRef.current = null;
      if (requestStartedRef.current && actionId.current) {
        onAttemptChange({
          sessionUid,
          complaintText: textRef.current,
          inputLocale: attemptLocale.current,
          actionId: actionId.current,
          phase: "unknown",
        });
      }
    };
  }, [onAttemptChange, sessionUid]);

  useEffect(() => {
    if (actionId.current && attemptLocale.current !== locale && !pending) {
      setAttemptConflict(true);
      setUnknownOutcome(true);
      if (attempt && attempt.phase !== "unknown") onAttemptChange({ ...attempt, phase: "unknown" });
    } else if (actionId.current && attemptLocale.current === locale) {
      setAttemptConflict(false);
    }
  }, [attempt, locale, onAttemptChange, pending]);

  function isCurrent(generation: number): boolean {
    return mountedRef.current && generation === requestGenerationRef.current;
  }

  function updateAttempt(phase: ComplaintAttemptPhase, complaintText: string, nextActionId: string) {
    onAttemptChange({
      sessionUid,
      complaintText,
      inputLocale: attemptLocale.current,
      actionId: nextActionId,
      phase,
    });
  }

  async function submitCurrentAttempt() {
    if (attemptConflict) return;
    const checked = validateComplaintText(text);
    if (!checked.valid) {
      setErrorCode(checked.code);
      return;
    }
    if (!profile || profile.role !== "customer" || !profile.active) {
      setErrorCode("permission");
      return;
    }

    await guard(async () => {
      const generation = ++requestGenerationRef.current;
      const controller = new AbortController();
      controllerRef.current = controller;
      requestStartedRef.current = true;
      setPending(true);
      setErrorCode(null);
      setUnknownOutcome(false);
      try {
        let user: ReturnType<typeof getFirebaseServices>["auth"]["currentUser"];
        try {
          user = getFirebaseServices().auth.currentUser;
        } catch {
          throw new ComplaintSubmissionError("backend");
        }
        if (!user || user.uid !== sessionUid) throw new ComplaintSubmissionError("authentication");
        let idToken: string;
        try {
          idToken = await user.getIdToken();
        } catch {
          throw new ComplaintSubmissionError("authentication");
        }
        actionId.current ??= crypto.randomUUID();
        attemptLocale.current = locale;
        updateAttempt("submitting", checked.complaintText, actionId.current);
        const result = await submitComplaint(
          {
            complaintText: checked.complaintText,
            inputLocale: locale,
            actionId: actionId.current,
          },
          idToken,
          fetch,
          controller.signal,
        );
        if (
          !isCurrent(generation) ||
          user.uid !== sessionUid ||
          getFirebaseServices().auth.currentUser?.uid !== sessionUid ||
          localeRef.current !== attemptLocale.current
        ) return;
        actionId.current = null;
        requestStartedRef.current = false;
        onAttemptChange(null);
        onSuccess(result);
      } catch (error) {
        if (!isCurrent(generation)) return;
        const submissionError = error instanceof ComplaintSubmissionError ? error : new ComplaintSubmissionError("unexpected", "unknown");
        if (submissionError.outcome === "unknown") {
          setUnknownOutcome(true);
          if (actionId.current) updateAttempt("unknown", checked.complaintText, actionId.current);
        } else {
          actionId.current = null;
          requestStartedRef.current = false;
          onAttemptChange(null);
          setErrorCode(submissionError.code);
        }
      } finally {
        if (isCurrent(generation)) {
          controllerRef.current = null;
          setPending(false);
        }
      }
    });
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitCurrentAttempt();
  }

  const fieldError = errorCode === "required" || errorCode === "too_long";

  return (
    <section className="cust-compose" aria-labelledby="complaint-title">
      {!hideTitle && (
        <h2 id="complaint-title" className="cust-compose-title">
          {t("complaintTitle")}
        </h2>
      )}
      {unknownOutcome ? (
        <div className="cust-error" role="alert">
          <span>{t("complaintUnknownOutcome")}</span>
          {attemptConflict ? <span>{t("complaintUnknownEdit")}</span> : null}
        </div>
      ) : null}
      {errorCode && !fieldError ? (
        <div className="cust-error" role="alert">{t(errorKeys[errorCode])}</div>
      ) : null}
      <form id="complaint-form" onSubmit={handleSubmit} noValidate className="cust-compose-form">
        <div className="cust-compose-input-wrap">
          <label htmlFor="complaint-text" className="sr-only">{t("complaintTextLabel")}</label>
          <textarea
            id="complaint-text"
            aria-describedby={fieldError ? "complaint-safety complaint-error complaint-count" : "complaint-safety complaint-count"}
            aria-invalid={fieldError}
            maxLength={MAX_COMPLAINT_LENGTH}
            required
            rows={3}
            placeholder={t("complaintLead")}
            value={text}
            className="cust-compose-textarea"
            onChange={(event) => {
              const nextText = event.target.value;
              setText(nextText);
              if (actionId.current && attempt && !canReuseComplaintAttempt(attempt, nextText, locale)) {
                setAttemptConflict(true);
                if (attempt.phase === "submitting") {
                  requestGenerationRef.current += 1;
                  controllerRef.current?.abort();
                  controllerRef.current = null;
                  setPending(false);
                  setUnknownOutcome(true);
                  onAttemptChange({ ...attempt, phase: "unknown" });
                }
              } else if (actionId.current) {
                setAttemptConflict(false);
              }
              if (fieldError) setErrorCode(null);
            }}
          />
          <p id="complaint-safety" className="field-help">{t("complaintSafetyReminder")}</p>
          <div className="cust-compose-footer">
            <span id="complaint-count" className="cust-compose-count">
              {text.length}/{MAX_COMPLAINT_LENGTH}
            </span>
            {fieldError ? (
              <span id="complaint-error" className="field-error" role="alert">
                {t(errorKeys[errorCode])}
              </span>
            ) : null}
            <button
              className="cust-compose-submit"
              disabled={pending || attemptConflict}
              type={unknownOutcome ? "button" : "submit"}
              onClick={unknownOutcome ? () => void submitCurrentAttempt() : undefined}
            >
              {pending ? t("complaintSubmitting") : unknownOutcome ? t("complaintRetryUnknown") : t("complaintSubmit")}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
