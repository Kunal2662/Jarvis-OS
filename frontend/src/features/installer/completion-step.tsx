import { CircleAlert, CircleCheck, FolderOpen, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useProvisioningStore } from "@/features/installer/provisioning-store";
import type { InstallationPlan } from "@/features/installer/installer-types";

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
}

export function CompletionStep({ plan, version, onLaunch, onOpenFolder }: CompletionStepProps) {
  const result = useProvisioningStore((s) => s.result);
  const downloads = useProvisioningStore((s) => s.downloads);

  // Warnings are worth surfacing: an installation can succeed while a
  // component could not be integrity-checked, and saying so is the
  // difference between "verified" and "we did not look".
  const warnings =
    result?.verification?.results.filter((entry) => entry.verdict === "warn") ?? [];

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

      {warnings.length > 0 && (
        <div className="flex flex-col gap-1 rounded-lg border border-amber-500/40 bg-amber-500/5 p-3">
          <p className="flex items-center gap-1.5 font-medium text-secondary">
            <CircleAlert className="size-3.5 shrink-0 text-amber-500" aria-hidden="true" />
            Worth knowing
          </p>
          {warnings.map((warning) => (
            <p key={warning.key} className="text-muted-foreground text-xs">
              {warning.detail}
            </p>
          ))}
        </div>
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
