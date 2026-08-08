export function StaffResolutionDetails({
  resolutionSummary,
  resolvedAt,
  resolutionLabel,
  resolvedAtLabel,
  formatDate,
}: {
  resolutionSummary: string | null;
  resolvedAt: string | null;
  resolutionLabel: string;
  resolvedAtLabel: string;
  formatDate: (value: Date) => string;
}) {
  if (!resolutionSummary && !resolvedAt) return null;

  return (
    <section className="resolution-details">
      {resolutionSummary ? <><h3>{resolutionLabel}</h3><p>{resolutionSummary}</p></> : null}
      {resolvedAt ? <p><strong>{resolvedAtLabel}</strong> <time dateTime={resolvedAt}>{formatDate(new Date(resolvedAt))}</time></p> : null}
    </section>
  );
}
