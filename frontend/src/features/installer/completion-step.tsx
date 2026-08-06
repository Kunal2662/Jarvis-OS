import { useState } from "react";
import { CircleCheck, FolderOpen, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProvisioningStore } from "@/features/installer/provisioning-store";
import { VerificationPanel } from "@/features/installer/verification-panel";
import type { InstallationPlan } from "@/features/installer/installer-types";
import type { VerificationReport } from "@/features/installer/provisioning-types";

/**
 * The completion screen -- M22 installer UI.
 *
 * Replaces TG-A's placeholder, whose Launch button was disabled because
 * there was nothing behind it. Both actions are injected rather than
 * imported: launching the application and revealing a folder are
 * host-shell operations (Tauri commands), and this component should not
 * know which shell it is running in — the same dependency-injection
 * shape `InstallerWizard` already uses for `loadPlan`.
 *
 * **The installed-components list names capabilities, not artefacts.**
 * The result stream carries friendly names only, so "Local AI" and
 * "Voice" is not a summary of the truth — it is the truth as the backend
 * reported it to a personal user.
 */

export interface CompletionStepProps {
  plan: InstallationPlan;
  version: string;
  /** `null` disables the button with a reason rather than hiding it, so
   *  a shell without the capability is explained rather than silently
   *  different. */
  onLaunch: (() => void) | null;
  onOpenFolder: (() => void) | null;
  /**
   * Repairs one step, then returns a **freshly re-verified** report --
   * not the repair's own result, which can complete having failed a
   * later step (a blocked download, say) without ever re-running the
   * check that was repaired. Only a new verification pass can say
   * whether the repaired check now passes.
   *
   * `null` when the host cannot repair, same rule as the two props
   * above -- offered only when it can actually do something.
   */
  onRepair: ((step: string) => Promise<VerificationReport>) | null;
}

export function CompletionStep({
  plan,
  version,
  onLaunch,
  onOpenFolder,
  onRepair,
}: CompletionStepProps) {
  const result = useProvisioningStore((s) => s.result);
  const downloads = useProvisioningStore((s) => s.downloads);

  // Seeded from this run's own result and then owned locally: a repair
  // replaces it with a fresh report, and the provisioning store's
  // `result` is this screen's *input*, not something it should mutate.
  const [verification, setVerification] = useState<VerificationReport | null>(
    result?.verification ?? null,
  );

  const components = [
    ...new Set([
      ...downloads
        .filter((item) => item.state === "completed" || item.state === "skipped")
        .map((item) => item.name),
      ...(plan.recommended_model ? [`${plan.recommended_model.label} model`] : []),
      plan.voice.identity_name ? "Voice" : null,
    ].filter((entry): entry is string => Boolean(entry))),
  ];

  return (
    <div className="flex flex-col gap-5">
      <header className="flex flex-col items-center gap-2 text-center">
        <CircleCheck className="size-10 text-emerald-500" aria-hidden="true" />
        <h2 className="font-semibold text-card-title">Installation complete</h2>
        <p className="text-muted-foreground text-secondary">
          JARVIS is set up and ready on this device.
        </p>
      </header>

      <dl className="grid gap-3 rounded-lg border border-border/60 p-4 sm:grid-cols-2">
        <div className="flex flex-col">
          <dt className="text-muted-foreground text-xs">Version</dt>
          <dd className="font-medium tabular-nums">{version}</dd>
        </div>
        <div className="flex flex-col">
          <dt className="text-muted-foreground text-xs">Capability score</dt>
          <dd className="font-medium tabular-nums">{plan.calibration.score}/100</dd>
        </div>
        <div className="flex flex-col sm:col-span-2">
          <dt className="pb-1 text-muted-foreground text-xs">Installed</dt>
          <dd className="flex flex-wrap gap-1.5">
            {components.length === 0 ? (
              <span className="text-muted-foreground text-xs">Core application only.</span>
            ) : (
              components.map((component) => (
                <span
                  key={component}
                  className="rounded bg-muted px-2 py-0.5 text-secondary text-xs"
                >
                  {component}
                </span>
              ))
            )}
          </dd>
        </div>
      </dl>

      {/* The full nine-check report, not just its warnings -- "verified"
          and "we did not look" are different claims, and a pass deserves
          to be shown as confidently as a warning. Repairable failures get
          a Repair button; `onRepair` re-verifies afterward rather than
          trusting the repair's own optimistic result. */}
      {verification && (
        <VerificationPanel
          report={verification}
          onRepair={
            onRepair
              ? async (step) => {
                  const refreshed = await onRepair(step);
                  setVerification(refreshed);
                }
              : null
          }
        />
      )}

      <div className="flex flex-col gap-2 sm:flex-row">
        <Button
          size="lg"
          className="flex-1 gap-2"
          onClick={onLaunch ?? undefined}
          disabled={onLaunch === null}
          title={onLaunch === null ? "Available from the desktop application" : undefined}
        >
          <Rocket className="size-4" aria-hidden="true" />
          Launch JARVIS
        </Button>
        <Button
          size="lg"
          variant="outline"
          className="flex-1 gap-2"
          onClick={onOpenFolder ?? undefined}
          disabled={onOpenFolder === null}
          title={onOpenFolder === null ? "Available from the desktop application" : undefined}
        >
          <FolderOpen className="size-4" aria-hidden="true" />
          Open installation folder
        </Button>
      </div>
    </div>
  );
}
