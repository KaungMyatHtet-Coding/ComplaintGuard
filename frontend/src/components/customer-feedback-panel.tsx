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
    <div className="border-t border-gray-200 pt-6 mt-6">
      <h3 className="text-md font-bold text-gray-900 mb-2">
        {translate(locale, "customerFeedbackTitle")}
      </h3>
      {error ? <div role="alert">Failed to submit feedback. Please try again.</div> : null}
      {feedback ? (
        <div className="p-4 bg-green-50 border border-green-200 rounded-lg text-green-800 text-sm font-medium">
          ✓ {translate(locale, "customerFeedbackSuccess")}
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4 bg-gray-50 p-4 rounded-lg border border-gray-200">
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">
              {translate(locale, "customerRatingLabel")}
            </label>
            <div className="flex items-center gap-2">
              {[1, 2, 3, 4, 5].map((star) => (
                <button key={star} type="button" onClick={() => setRating(star)} className={`text-2xl transition-transform ${star <= rating ? "text-yellow-400 scale-110" : "text-gray-300"}`}>★</button>
              ))}
              <span className="text-xs text-gray-500 ml-2 font-medium">{rating} / 5</span>
            </div>
          </div>
          <div>
            <label className="block text-xs font-semibold text-gray-700 mb-1">
              {translate(locale, "customerCommentsLabel")}
            </label>
            <textarea value={comments} onChange={(event) => setComments(event.target.value)} rows={2} className="w-full rounded-lg border border-gray-300 p-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500" />
          </div>
          <button type="submit" disabled={submitting} className="bg-green-600 hover:bg-green-700 text-white font-medium text-sm px-4 py-2 rounded-lg transition-colors">
            {submitting ? translate(locale, "customerSubmittingFeedback") : translate(locale, "customerSubmitFeedback")}
          </button>
        </form>
      )}
    </div>
  );
}
