"use client";

import { useState, type FormEvent } from "react";

import { translate, type Locale } from "../lib/i18n";
import type { CustomerTicketDetail } from "../lib/customer-workflow";

export function CustomerFeedbackPanel({
  locale,
  feedback,
  onSubmitFeedback,
}: {
  locale: Locale;
  feedback: CustomerTicketDetail["feedback"];
  onSubmitFeedback: (rating: number, comments: string) => Promise<void>;
}) {
  const [rating, setRating] = useState(5);
  const [comments, setComments] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (submitting) return;
    setError(false);
    setSubmitting(true);
    try {
      await onSubmitFeedback(rating, comments.trim());
    } catch {
      setError(true);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="cust-feedback">
      <h3>{translate(locale, "customerFeedbackTitle")}</h3>
      {error ? <div className="cust-error" role="alert">{translate(locale, "customerFeedbackError")}</div> : null}
      {feedback ? (
        <div className="cust-feedback-done">
          ✓ {translate(locale, "customerFeedbackSuccess")}
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="cust-feedback-form">
          <div>
            <label>{translate(locale, "customerRatingLabel")}</label>
            <div className="cust-stars">
              {[1, 2, 3, 4, 5].map((star) => (
                <button
                  key={star}
                  type="button"
                  onClick={() => setRating(star)}
                  aria-label={translate(locale, "customerStarRating").replace("{rating}", String(star))}
                  aria-pressed={star === rating}
                  className={`cust-star-btn ${star <= rating ? "is-active" : ""}`}
                >★</button>
              ))}
              <span className="cust-star-count">{rating} / 5</span>
            </div>
          </div>
          <div>
            <label>{translate(locale, "customerCommentsLabel")}</label>
            <textarea
              value={comments}
              onChange={(event) => setComments(event.target.value)}
              rows={2}
              className="cust-feedback-textarea"
            />
          </div>
          <button type="submit" disabled={submitting} className="cust-feedback-submit">
            {submitting ? translate(locale, "customerSubmittingFeedback") : translate(locale, "customerSubmitFeedback")}
          </button>
        </form>
      )}
    </div>
  );
}
