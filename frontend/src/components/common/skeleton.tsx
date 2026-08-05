/**
 * Skeleton loaders -- M8 Phase 6.
 *
 * A skeleton is only honest when it is the *shape of the thing that is
 * coming*. A generic grey box that turns into a three-column table has
 * told the user nothing and made the layout jump; that is worse than a
 * spinner, not better. So this module exports shapes (`SkeletonText`,
 * `SkeletonRows`, `SkeletonStat`) rather than one `<Skeleton>` that each
 * call site guesses dimensions for.
 *
 * **Only for content whose layout is known in advance.** Where it is not
 * — a search result list of unknown length — `LoadingState`'s spinner
 * remains the right answer, and this module does not replace it.
 *
 * The pulse respects `prefers-reduced-motion` through Tailwind's own
 * `motion-safe:` variant rather than reading the accessibility store: a
 * skeleton can render before `StoreProvider` has hydrated, and a
 * CSS-level answer works there too.
 */

const BASE = "rounded bg-muted motion-safe:animate-pulse";

export function SkeletonText({ className = "" }: { className?: string }) {
  return <div className={`${BASE} h-3.5 ${className}`} aria-hidden="true" />;
}

/**
 * `n` list rows at a fixed height.
 *
 * `aria-hidden` on the shapes, with one live region carrying the real
 * announcement: a screen reader should hear "Loading notifications",
 * not eight anonymous list items.
 */
export function SkeletonRows({
  rows = 3,
  label = "Loading",
  className = "",
}: {
  rows?: number;
  label?: string;
  className?: string;
}) {
  return (
    <div className={`flex flex-col gap-2 p-3 ${className}`} role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex items-center gap-2" aria-hidden="true">
          <div className={`${BASE} size-8 shrink-0 rounded-full`} />
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <div className={`${BASE} h-3 w-1/2`} />
            <div className={`${BASE} h-2.5 w-3/4`} />
          </div>
        </div>
      ))}
    </div>
  );
}

/** The shape of a single headline number plus its caption. */
export function SkeletonStat({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex flex-col gap-1.5" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      <div className={`${BASE} h-6 w-16`} aria-hidden="true" />
      <div className={`${BASE} h-2.5 w-24`} aria-hidden="true" />
    </div>
  );
}

/** A grid of stat shapes — what most dashboard widgets are waiting for. */
export function SkeletonStatGrid({ count = 4, label = "Loading" }: { count?: number; label?: string }) {
  return (
    <div className="grid grid-cols-2 gap-4 p-3" role="status" aria-live="polite">
      <span className="sr-only">{label}</span>
      {Array.from({ length: count }, (_, index) => (
        <div key={index} className="flex flex-col gap-1.5" aria-hidden="true">
          <div className={`${BASE} h-6 w-16`} />
          <div className={`${BASE} h-2.5 w-20`} />
        </div>
      ))}
    </div>
  );
}
