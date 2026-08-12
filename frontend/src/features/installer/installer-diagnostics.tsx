import { useEffect, useState } from "react";
import { FileText, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { CheckRow } from "@/features/installer/check-row";
import { VerificationPanel } from "@/features/installer/verification-panel";
import { installationPresence } from "@/features/installer/provisioning-types";
import type {
  DependencyReport,
  InstallationStatus,
  VerificationReport,
} from "@/features/installer/provisioning-types";

/**
 * A dependency has no pass/warn/fail verdict of its own -- `status` is
 * "present" | "missing" | "unknown", and `dependencies.py`'s own
 * docstring is explicit that a missing one is "a finding, not a
 * failure" (only Python itself is required, and the CLI could not be
 * running under a missing Python). Mapped onto `CheckRow`'s verdict
 * the same way `validation.py`'s own non-blocking findings already are
 * -- "no internet" and "below comfortable RAM" render as `warn` with
 * calm copy, not as alarms -- so "no CUDA driver" gets the same
 * treatment rather than a fourth, invented severity.
 */
function dependencyVerdict(status: DependencyReport["dependencies"][number]["status"]): "pass" | "warn" {
  return status === "present" ? "pass" : "warn";
}

/**
 * "Installer diagnostics" + "update preparation" -- M22 Task Group D.
 *
 * Reachable from any step (mounted once by `InstallerWizard`, not tied
 * to a particular screen), because the two questions it answers --
 * "does an installation already exist here?" and "is it healthy?" --
 * are useful regardless of where the user currently is in a fresh
 * install, and are exactly what someone re-running the installer over
 * an existing or broken one needs first.
 *
 * **Reuses `VerificationPanel`** rather than building a second
 * check-list-with-repair view; the only new presentational work here is
 * the journal summary and the log-folder action.
 *
 * A manifest-less, journal-empty location is not verified at all --
 * "9 checks failed" for a folder nobody has installed to yet would read
 * as a problem where there is none, so verification only runs once
 * `status` reports something to verify.
 */

export interface DiagnosticsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  location: string;
  accountType: "personal" | "administrator" | null;
  getStatus: (location: string) => Promise<InstallationStatus>;
  verify: (input: {
    location: string;
    accountType: "personal" | "administrator";
  }) => Promise<VerificationReport>;
  checkDependencies: (input: {
    location: string;
    accountType: "personal" | "administrator";
  }) => Promise<DependencyReport>;
  /** `null` when the host cannot repair. */
  onRepair: ((step: string) => Promise<VerificationReport>) | null;
  /** `null` when the host cannot open a folder. */
  onOpenLogFolder: (() => void) | null;
}

export function DiagnosticsDialog({
  open,
  onOpenChange,
  location,
  accountType,
  getStatus,
  verify,
  checkDependencies,
  onRepair,
  onOpenLogFolder,
}: DiagnosticsDialogProps) {
  const [status, setStatus] = useState<InstallationStatus | null>(null);
  const [verification, setVerification] = useState<VerificationReport | null>(null);
  const [dependencies, setDependencies] = useState<DependencyReport | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    setLoading(true);
    setError(null);
    setStatus(null);
    setVerification(null);
    setDependencies(null);

    async function run() {
      // `status`'s *resolved value* drives what runs next, not the
      // `status` state variable -- reading state here would capture
      // this render's stale closure, not what `getStatus` just returned.
      const result = await getStatus(location);
      if (cancelled) return;
      setStatus(result);

      // Dependency detection and verification are both meaningful only
      // once an account type is chosen -- dependency payload shape and
      // verification's own `--account-type` flag both need one, and the
      // dialog can be opened before the Account step is reached.
      if (!accountType) return;

      const tasks: Promise<void>[] = [
        checkDependencies({ location, accountType }).then((report) => {
          if (!cancelled) setDependencies(report);
        }),
      ];

      // Verify only once there is something to verify: a location with
      // no manifest and no journal progress has nothing installed, and
      // a report full of "folder missing" findings for a target nobody
      // has installed to yet would read as a problem where there is
      // none.
      if (installationPresence(result) !== "none") {
        tasks.push(
          verify({ location, accountType }).then((report) => {
            if (!cancelled) setVerification(report);
          }),
        );
      }

      await Promise.all(tasks);
    }

    run()
      .catch((err: unknown) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, location, accountType, getStatus, verify, checkDependencies]);

  const totalSteps = status ? status.journal.completed.length + status.journal.remaining.length : 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Installer diagnostics</DialogTitle>
          <DialogDescription>What the installer knows about this location.</DialogDescription>
        </DialogHeader>

        {loading && (
          <div className="flex items-center gap-2 py-4 text-muted-foreground text-secondary">
            <Loader2 className="size-4 animate-spin" aria-hidden="true" />
            Checking…
          </div>
        )}

        {!loading && error && (
          <p className="rounded-lg border border-destructive/40 bg-destructive/5 p-3 text-secondary">
            {error}
          </p>
        )}

        {!loading && !error && status && (
          <div className="flex flex-col gap-3">
            <dl className="grid grid-cols-2 gap-3 rounded-lg border border-border/60 p-3">
              <div className="flex flex-col">
                <dt className="text-muted-foreground text-xs">Existing installation</dt>
                <dd className="font-medium">
                  {
                    { complete: "Found", partial: "Partially installed", none: "None found here" }[
                      installationPresence(status)
                    ]
                  }
                </dd>
              </div>
              <div className="flex flex-col">
                <dt className="text-muted-foreground text-xs">Steps completed</dt>
                <dd className="font-medium tabular-nums">
                  {status.journal.completed.length} of {totalSteps || 8}
                </dd>
              </div>
            </dl>

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

            {!verification && (
              <p className="text-muted-foreground text-xs">
                Nothing installed at this location yet.
              </p>
            )}

            {dependencies && (
              <div className="rounded-lg border border-border/60 p-3">
                <p className="pb-1 font-medium text-muted-foreground text-xs uppercase tracking-wide">
                  This device
                </p>
                <ul>
                  {dependencies.dependencies.map((dependency) => (
                    <CheckRow
                      key={dependency.key}
                      label={dependency.label}
                      verdict={dependencyVerdict(dependency.status)}
                      detail={dependency.detail}
                    />
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {onOpenLogFolder && (
            <Button variant="outline" onClick={onOpenLogFolder} className="gap-1.5">
              <FileText className="size-4" aria-hidden="true" />
              Open log folder
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
