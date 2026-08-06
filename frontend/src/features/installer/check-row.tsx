import { CircleAlert, CircleCheck, CircleX } from "lucide-react";
import type { ReactNode } from "react";

/**
 * One labelled check with a pass/warn/fail verdict -- shared by every
 * screen in the installer that renders a list of checks.
 *
 * **Extracted from `installer-steps.tsx`'s `SummaryStep`** (M22 Task
 * Group D), which had its own private `ValidationRow` rendering exactly
 * this shape for the seven pre-flight checks. Task Group D's own brief
 * requires "no duplicated widgets", and building a second, near-identical
 * row for the nine post-install verification checks would have been
 * exactly that. `SummaryStep` now imports this instead of defining its
 * own copy; `installer-wizard.test.tsx` and `installer-contract.test.ts`
 * exercise it unchanged, which is what makes this move safe to make
 * without a defect to justify it -- a regression here fails an existing
 * test rather than shipping silently.
 *
 * Deliberately ignorant of what a check verdict *means* to its caller.
 * A pre-flight `ValidationResult` carries `blocking`; a post-install
 * `VerificationResultEvent` carries `repairable`/`repair_step`. Neither
 * concept lives here — the caller decides whether there is an action to
 * offer and passes it as `action`, so this component has one job: show a
 * verdict, a label and a detail, consistently, everywhere a check is
 * rendered.
 */

export type CheckVerdict = "pass" | "warn" | "fail";

const VERDICT_ICON = {
  pass: CircleCheck,
  warn: CircleAlert,
  fail: CircleX,
} as const;

const VERDICT_COLOUR = {
  pass: "text-emerald-500",
  warn: "text-amber-500",
  fail: "text-destructive",
} as const;

export interface CheckRowProps {
  label: string;
  verdict: CheckVerdict;
  detail: string;
  /** Rendered after the detail text -- a Repair button, for instance.
   *  Omitted for a check with nothing actionable to offer. */
  action?: ReactNode;
}

export function CheckRow({ label, verdict, detail, action }: CheckRowProps) {
  const Icon = VERDICT_ICON[verdict];
  return (
    <li className="flex items-start gap-3 py-1.5">
      <Icon
        className={`mt-0.5 size-4 shrink-0 ${VERDICT_COLOUR[verdict]}`}
        aria-label={verdict}
      />
      <div className="min-w-0 flex-1">
        <p className="font-medium text-secondary">{label}</p>
        <p className="text-muted-foreground text-xs">{detail}</p>
      </div>
      {action}
    </li>
  );
}
