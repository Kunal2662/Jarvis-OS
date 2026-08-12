import { useState } from "react";
import { Loader2, Wrench } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CheckRow } from "@/features/installer/check-row";
import type { VerificationReport } from "@/features/installer/provisioning-types";

/**
 * The nine post-install checks, with a Repair action on any that are
 * repairable -- M22 Task Group D's "component verification" and
 * "recovery planning" items.
 *
 * **Reused, not duplicated**, across two screens that both need it:
 * `completion-step.tsx` (verification embedded in a just-finished
 * provisioning run) and the diagnostics view (verification run
 * standalone, against an installation from an earlier session). Both
 * mount this component with their own `report` state; neither
 * reimplements the row or the repair flow.
 *
 * **Owns none of the repair transport.** `onRepair` is injected, same
 * shape as `InstallerWizard`'s `runProvisioning`/`cancelProvisioning` --
 * this component's job is to show a report and a button, not to know
 * how a step gets repaired. The caller is responsible for re-verifying
 * after `onRepair` resolves and passing a fresh `report` back down; this
 * component does not assume a repair succeeded just because the call
 * returned, since a repair can complete having failed a later step (a
 * blocked download, for instance) -- only a fresh verification result
 * can say whether the check that triggered it now passes.
 */

export interface VerificationPanelProps {
  report: VerificationReport;
  /** `null` when the host cannot repair -- same "offered only when
   *  actionable" rule the completion screen's Launch/Open Folder
   *  buttons already follow. */
  onRepair: ((step: string) => Promise<void>) | null;
}

export function VerificationPanel({ report, onRepair }: VerificationPanelProps) {
  const [repairingStep, setRepairingStep] = useState<string | null>(null);

  const handleRepair = async (step: string) => {
    if (!onRepair || repairingStep !== null) return;
    setRepairingStep(step);
    try {
      await onRepair(step);
    } finally {
      setRepairingStep(null);
    }
  };

  return (
    <div className="rounded-lg border border-border/60 p-3">
      <p className="pb-1 font-medium text-muted-foreground text-xs uppercase tracking-wide">
        Installation health
      </p>
      <ul>
        {report.results.map((result) => (
          <CheckRow
            key={result.key}
            label={result.label}
            verdict={result.verdict}
            detail={result.detail}
            action={
              result.repairable && result.repair_step && onRepair ? (
                <Button
                  variant="outline"
                  size="sm"
                  className="shrink-0 gap-1.5"
                  disabled={repairingStep !== null}
                  onClick={() => handleRepair(result.repair_step as string)}
                >
                  {repairingStep === result.repair_step ? (
                    <Loader2 className="size-3.5 animate-spin" aria-hidden="true" />
                  ) : (
                    <Wrench className="size-3.5" aria-hidden="true" />
                  )}
                  {repairingStep === result.repair_step ? "Repairing…" : "Repair"}
                </Button>
              ) : undefined
            }
          />
        ))}
      </ul>
    </div>
  );
}
