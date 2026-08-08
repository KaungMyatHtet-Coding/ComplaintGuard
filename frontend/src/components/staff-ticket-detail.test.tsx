import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";

import { StaffResolutionDetails } from "./staff-resolution-details";

describe("StaffResolutionDetails", () => {
  it("renders the complete saved resolution summary and resolved timestamp", () => {
    const summary = "Unauthorized withdrawal report reviewed. Customer confirmed account access.";
    const formatDate = vi.fn(() => "Aug 8, 2026, 3:54 PM");

    const markup = renderToStaticMarkup(
      <StaffResolutionDetails
        resolutionSummary={summary}
        resolvedAt="2026-08-08T15:54:14.452Z"
        resolutionLabel="Resolution summary"
        resolvedAtLabel="Resolved at"
        formatDate={formatDate}
      />,
    );

    expect(markup).toContain(summary);
    expect(markup).toContain("Resolution summary");
    expect(markup).toContain("Resolved at");
    expect(markup).toContain("Aug 8, 2026, 3:54 PM");
    expect(markup).toContain('dateTime="2026-08-08T15:54:14.452Z"');
    expect(formatDate).toHaveBeenCalledWith(new Date("2026-08-08T15:54:14.452Z"));
  });

  it("does not render an empty resolution block for an unresolved ticket", () => {
    const formatDate = vi.fn(() => "unused");

    const markup = renderToStaticMarkup(
      <StaffResolutionDetails
        resolutionSummary={null}
        resolvedAt={null}
        resolutionLabel="Resolution summary"
        resolvedAtLabel="Resolved at"
        formatDate={formatDate}
      />,
    );

    expect(markup).toBe("");
    expect(formatDate).not.toHaveBeenCalled();
  });
});
