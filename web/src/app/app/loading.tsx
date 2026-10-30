/** Shown while a page's data loads: the shape of a page, not a spinner. */
export default function Loading() {
  return (
    <div className="animate-pulse" aria-busy="true" aria-label="Loading">
      <div className="mb-2 h-7 w-56 rounded bg-surface-2" />
      <div className="mb-6 h-4 w-80 rounded bg-surface-2" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <div key={i} className="h-24 rounded-xl border border-border bg-surface" />
        ))}
      </div>
      <div className="mt-6 h-80 rounded-xl border border-border bg-surface" />
    </div>
  );
}
