"use client";

import { useMemo, useRef, useState, type FormEvent } from "react";

import { useApp } from "@/components/app-provider";
import {
  ComplaintSubmissionError,
  MAX_COMPLAINT_LENGTH,
  createSubmissionGuard,
  submitComplaint,
  validateComplaintText,
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

export function ComplaintForm({ onSuccess, hideTitle }: { onSuccess?: (ticketId: string) => void; hideTitle?: boolean }) {
  const { locale, profile, t } = useApp();
  const [text, setText] = useState("");
  const [pending, setPending] = useState(false);
  const [errorCode, setErrorCode] = useState<ComplaintErrorCode | null>(null);
  const [success, setSuccess] = useState<ComplaintSuccess | null>(null);
  const guard = useMemo(() => createSubmissionGuard(), []);
  const actionId = useRef<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const checked = validateComplaintText(text);
    if (!checked.valid) {
      setErrorCode(checked.code);
      return;
    }
    if (!profile || profile.role !== "customer") {
      setErrorCode("permission");
      return;
    }

    await guard(async () => {
      setPending(true);
      setErrorCode(null);
      setSuccess(null);
      try {
        const user = getFirebaseServices().auth.currentUser;
        if (!user) throw new ComplaintSubmissionError("authentication");
        const idToken = await user.getIdToken();
        actionId.current ??= crypto.randomUUID();
        const result = await submitComplaint(
          {
            complaintText: checked.complaintText,
            inputLocale: locale,
            actionId: actionId.current,
          },
          idToken,
        );
        setSuccess(result);
        setText("");
        actionId.current = null;
        onSuccess?.();
      } catch (error) {
        setErrorCode(
          error instanceof ComplaintSubmissionError ? error.code : "unexpected",
        );
      } finally {
        setPending(false);
      }
    });
  }

  const fieldError = errorCode === "required" || errorCode === "too_long";

  return (
    <section className="cust-compose" aria-labelledby="complaint-title">
      {!hideTitle && (
        <h2 id="complaint-title" className="cust-compose-title">
          {t("complaintTitle")}
        </h2>
      )}
      {success ? (
        <div className="success-panel" role="status">
          <strong>{t("complaintSuccess")}</strong>
          <span className="ticket-reference">{t("complaintReference")}: {success.complaintId}</span>
        </div>
      ) : null}
      {errorCode && !fieldError ? (
        <div className="cust-error" role="alert">{t(errorKeys[errorCode])}</div>
      ) : null}
      <form onSubmit={handleSubmit} noValidate className="cust-compose-form">
        <div className="cust-compose-input-wrap">
          <textarea
            id="complaint-text"
            aria-describedby={fieldError ? "complaint-error complaint-count" : "complaint-count"}
            aria-invalid={fieldError}
            maxLength={MAX_COMPLAINT_LENGTH}
            required
            rows={3}
            placeholder={t("complaintLead")}
            value={text}
            className="cust-compose-textarea"
            onChange={(event) => {
              setText(event.target.value);
              actionId.current = null;
              if (fieldError) setErrorCode(null);
            }}
          />
          <div className="cust-compose-footer">
            <span id="complaint-count" className="cust-compose-count">
              {text.length}/{MAX_COMPLAINT_LENGTH}
            </span>
            {fieldError ? (
              <span id="complaint-error" className="field-error" role="alert">
                {t(errorKeys[errorCode])}
              </span>
            ) : null}
            <button className="cust-compose-submit" disabled={pending} type="submit">
              {pending ? t("complaintSubmitting") : t("complaintSubmit")}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}
