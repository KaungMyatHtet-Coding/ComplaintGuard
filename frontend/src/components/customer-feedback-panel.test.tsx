import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { CustomerFeedbackPanel } from "./customer-feedback-panel";

const submittedFeedback = {
  rating: 5,
  comments: "Resolution was clear.",
  submittedAt: "2026-08-08T16:11:41.883814Z",
};

function render(feedback: typeof submittedFeedback | null) {
  return renderToStaticMarkup(
    <CustomerFeedbackPanel
      locale="en"
      feedback={feedback}
      onSubmitFeedback={vi.fn()}
    />,
  );
}

describe("CustomerFeedbackPanel", () => {
  it("shows persisted feedback success and hides the form after reload/remount", () => {
    const firstMount = render(submittedFeedback);
    const refreshedMount = render(submittedFeedback);

    for (const markup of [firstMount, refreshedMount]) {
      expect(markup).toContain("Thank you for your rating and feedback.");
      expect(markup).not.toContain("Star Rating");
      expect(markup).not.toContain("Submit feedback");
      expect(markup).not.toContain("<form");
    }
  });

  it("shows the form for a resolved ticket without persisted feedback", () => {
    const markup = render(null);

    expect(markup).toContain("Star Rating");
    expect(markup).toContain("Comments (Optional)");
    expect(markup).toContain("Submit feedback");
    expect(markup).toContain("<form");
    expect(markup).toContain('aria-label="1 out of 5 stars"');
    expect(markup).toContain('aria-label="5 out of 5 stars"');
    expect(markup).toContain('aria-pressed="true"');
    expect(markup).not.toContain("Thank you for your rating and feedback.");
  });

  it("derives display state from each selected ticket instead of transient success", () => {
    expect(render(submittedFeedback)).not.toContain("<form");
    expect(render(null)).toContain("<form");
  });
});
