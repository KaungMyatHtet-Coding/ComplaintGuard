export function AccessibleSkeleton({ label }: { label: string }) {
  return (
    <div className="accessible-skeleton" role="status" aria-live="polite" aria-label={label}>
      <span className="skeleton-loading" aria-hidden="true" />
      <span className="sr-only">{label}</span>
    </div>
  );
}
