import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * The one loading indicator every future async view uses -- per
 * ARCHITECTURE.md section 14's "no per-component bespoke duration" rule,
 * this reuses Tailwind's own `animate-spin` (a continuous rotation has no
 * meaningful "duration" to standardize) rather than a Motion-driven
 * animation.
 */
export function LoadingSpinner({ className }: { className?: string }) {
  return (
    <Loader2
      className={cn("size-icon-md animate-spin text-muted-foreground", className)}
      aria-hidden="true"
    />
  );
}

/** A named loading region for screen readers -- wraps a `LoadingSpinner`
 *  with an accessible label instead of leaving a bare spinning icon. */
export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex items-center justify-center gap-2 p-8">
      <LoadingSpinner />
      <span className="text-secondary text-muted-foreground">{label}…</span>
    </div>
  );
}
