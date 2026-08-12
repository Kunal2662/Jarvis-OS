import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Info, Stethoscope } from "lucide-react";
import { Button } from "@/components/ui/button";
import { CompletionStep } from "@/features/installer/completion-step";
import { DiagnosticsDialog } from "@/features/installer/installer-diagnostics";
import { InstallProgressStep } from "@/features/installer/install-progress-step";
import { useProvisioningStore } from "@/features/installer/provisioning-store";
import { installationPresence } from "@/features/installer/provisioning-types";
import type {
  DependencyReport,
  InstallationStatus,
  ProvisioningEvent,
  VerificationReport,
} from "@/features/installer/provisioning-types";
import {
  AccountStep,
  CalibrationStep,
  HardwareStep,
  LicenseStep,
  LocationStep,
  ModelStep,
  SummaryStep,
  VoiceStep,
  WelcomeStep,
} from "@/features/installer/installer-steps";
import { canAdvance, useInstallerStore } from "@/features/installer/installer-store";
import { INSTALLER_STEPS, STEP_TITLES } from "@/features/installer/installer-types";
import type { InstallationPlan } from "@/features/installer/installer-types";

/**
 * The installer wizard shell -- M22 Task Group A.
 *
 * **How it gets its data.** `loadPlan` is injected rather than imported.
 * The real implementation shells out to
 * `python -m jarvis.installer plan` through Tauri's command API; in
 * tests it is a stub. An installer runs before JARVIS is installed, so
 * there is no REST API to call — and adding one would have modified the
 * frozen API contract. Injection also means this component has no
 * opinion about *how* the machine is scanned, which is what lets Task
 * Group B swap in the packaged runtime without touching the UI.
 *
 * The scan is triggered by reaching the Hardware step, not by mounting:
 * probing a machine before the user has chosen a location or an account
 * type would produce a plan for the wrong target and the wrong payload
 * shape.
 */

export interface InstallerWizardProps {
  /** Fetches the installation plan. Rejects with a readable message. */
  loadPlan: (input: { location: string; accountType: "personal" | "administrator" }) => Promise<InstallationPlan>;
  /** Proposed default, from `default_install_location()`. */
  defaultLocation: string;

  /**
   * Runs provisioning, calling `onEvent` for each event the backend
   * streams. The real implementation spawns
   * `python -m jarvis.installer provision --stream` through Tauri and
   * parses its NDJSON; tests inject a stub.
   *
   * Injected for the same reason `loadPlan` is: this component should
   * have no opinion about how the host reaches the engine, which is what
   * lets the packaging task group swap the transport without touching
   * the UI.
   */
  runProvisioning: (input: {
    location: string;
    accountType: "personal" | "administrator";
    onEvent: (event: ProvisioningEvent) => void;
  }) => Promise<void>;

  /**
   * Asks the host to stop the running installation.
   *
   * Optional: a host that cannot stop a run passes nothing and the
   * Cancel control is not offered, rather than being shown and doing
   * nothing. The user-visible outcome still arrives through
   * `runProvisioning` rejecting — there is one path to the cancelled
   * state, not two.
   */
  cancelProvisioning?: (() => void) | null;

  /** Application version, shown on completion. */
  version?: string;

  /** Host-shell actions. `null` when the shell cannot perform them --
   *  the button then explains itself rather than disappearing. */
  onLaunch?: (() => void) | null;
  onOpenFolder?: (() => void) | null;

  /** Repairs one step and returns a freshly re-verified report. `null`
   *  when the host cannot repair. See `CompletionStepProps.onRepair`. */
  onRepair?: ((step: string) => Promise<VerificationReport>) | null;

  /**
   * The diagnostics dialog's data, injected for the same reason
   * `loadPlan` is: this component has no opinion about how the host
   * answers "what's at this location". `undefined` disables the
   * Diagnostics trigger entirely rather than opening a dialog that can
   * only ever show an error.
   */
  getInstallationStatus?: (location: string) => Promise<InstallationStatus>;
  verifyInstallation?: (input: {
    location: string;
    accountType: "personal" | "administrator";
  }) => Promise<VerificationReport>;
  checkDependencies?: (input: {
    location: string;
    accountType: "personal" | "administrator";
  }) => Promise<DependencyReport>;
  onOpenLogFolder?: (() => void) | null;
}

export function InstallerWizard({
  loadPlan,
  defaultLocation,
  runProvisioning,
  cancelProvisioning = null,
  version = "",
  onLaunch = null,
  onOpenFolder = null,
  onRepair = null,
  getInstallationStatus,
  verifyInstallation,
  checkDependencies,
  onOpenLogFolder = null,
}: InstallerWizardProps) {
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const step = useInstallerStore((s) => s.step);
  const plan = useInstallerStore((s) => s.plan);
  const planError = useInstallerStore((s) => s.planError);
  const scanning = useInstallerStore((s) => s.scanning);
  const installLocation = useInstallerStore((s) => s.installLocation);
  const accountType = useInstallerStore((s) => s.accountType);
  const next = useInstallerStore((s) => s.next);
  const back = useInstallerStore((s) => s.back);
  const beginScan = useInstallerStore((s) => s.beginScan);
  const setPlan = useInstallerStore((s) => s.setPlan);
  const setPlanError = useInstallerStore((s) => s.setPlanError);
  const advanceable = useInstallerStore(canAdvance);

  const provisioningPhase = useProvisioningStore((s) => s.phase);
  const beginProvisioning = useProvisioningStore((s) => s.begin);
  const ingestProvisioningEvent = useProvisioningStore((s) => s.ingest);
  const failProvisioning = useProvisioningStore((s) => s.fail);

  const stepIndex = INSTALLER_STEPS.indexOf(step);
  const setLocation = useInstallerStore((s) => s.setLocation);

  // Commit the proposed default so the Location step's Continue is live
  // without the user editing the field first. The step *displays*
  // `defaultLocation` when nothing is set, so before this the field
  // looked filled in while `canAdvance` still saw `null` -- Continue
  // stayed disabled and the only way forward was to retype the path
  // already on screen. Caught by the wizard's own flow test.
  useEffect(() => {
    if (installLocation === null) setLocation(defaultLocation);
  }, [installLocation, defaultLocation, setLocation]);

  /**
   * Identifies the scan whose result is still wanted.
   *
   * A per-effect `cancelled` flag looks like the obvious way to guard
   * this and is wrong here: `beginScan()` sets `scanning`, `scanning`
   * was an effect dependency, so starting a scan re-ran the effect,
   * whose cleanup immediately cancelled the request it had just
   * started — and the re-run's own `scanning` guard then refused to
   * retry. The scan resolved into a discarded closure every time and
   * the step sat on its skeleton forever. Caught by the wizard's flow
   * test.
   *
   * A ref survives re-runs, so "is this result still current?" is
   * answered by comparing request ids rather than by which effect
   * invocation created the promise.
   */
  const scanId = useRef(0);

  /**
   * "Update preparation" -- M22 Task Group D. Detected automatically,
   * as soon as a location is chosen, rather than only on request inside
   * the Diagnostics dialog: a returning user re-running the installer
   * over an install that already exists should not have to think to ask
   * whether the wizard noticed.
   *
   * Needs no account type, unlike the Diagnostics dialog's dependency
   * and verification checks -- `status` reports the journal and
   * manifest for a location regardless of who is installing.
   */
  const [existingInstallation, setExistingInstallation] = useState<InstallationStatus | null>(
    null,
  );

  useEffect(() => {
    if (!getInstallationStatus) return;
    const location = installLocation ?? defaultLocation;
    if (!location.trim()) return;

    let cancelled = false;
    getInstallationStatus(location)
      .then((result) => {
        if (!cancelled) setExistingInstallation(result);
      })
      .catch(() => {
        // Silent: this is a proactive courtesy notice, not a step the
        // wizard depends on. A location that cannot be checked yet (not
        // created on disk, say) is not a failure worth surfacing here --
        // the Location and Summary steps' own checks already cover
        // whether the chosen folder is usable.
        if (!cancelled) setExistingInstallation(null);
      });

    return () => {
      cancelled = true;
    };
  }, [installLocation, defaultLocation, getInstallationStatus]);

  const hasExistingInstallation = Boolean(
    existingInstallation && installationPresence(existingInstallation) !== "none",
  );

  // Scan when the Hardware step is reached and there is no valid plan.
  // `setLocation`/`setAccountType` clear the plan, so changing either
  // and coming back re-scans rather than showing a stale result.
  useEffect(() => {
    if (step !== "hardware" || plan || planError || !accountType) return;

    const location = installLocation ?? defaultLocation;
    const id = ++scanId.current;

    beginScan();
    loadPlan({ location, accountType })
      .then((result) => {
        if (id === scanId.current) setPlan(result);
      })
      .catch((error: unknown) => {
        if (id !== scanId.current) return;
        setPlanError(error instanceof Error ? error.message : String(error));
      });
    // `scanning` is deliberately absent from the dependency list -- it
    // is this effect's own output, and depending on it is what caused
    // the race above.
  }, [
    step,
    plan,
    planError,
    installLocation,
    accountType,
    defaultLocation,
    loadPlan,
    beginScan,
    setPlan,
    setPlanError,
  ]);

  /**
   * Start (or resume) provisioning.
   *
   * Also the Retry handler, deliberately: a retry is a fresh
   * `provision` call, and the engine's journal makes that resume from
   * where it stopped rather than start over. A separate "resume"
   * pathway would be the one least often exercised.
   */
  const startProvisioning = useCallback(() => {
    if (!accountType) return;
    const location = installLocation ?? defaultLocation;

    beginProvisioning();
    void runProvisioning({
      location,
      accountType,
      onEvent: ingestProvisioningEvent,
    }).catch((error: unknown) => {
      // A rejection is a failure the stream never got to report -- the
      // process could not start, or the transport broke. The store
      // classifies the message into one of the friendly categories.
      failProvisioning(error instanceof Error ? error.message : String(error));
    });
  }, [
    accountType,
    installLocation,
    defaultLocation,
    runProvisioning,
    beginProvisioning,
    ingestProvisioningEvent,
    failProvisioning,
  ]);

  // Entering the Install step starts the run. Guarded on `idle` so a
  // re-render — or coming back to the step — cannot start a second one
  // over the top of a run already in progress.
  useEffect(() => {
    if (step === "install" && provisioningPhase === "idle") startProvisioning();
  }, [step, provisioningPhase, startProvisioning]);

  // Success advances by itself: there is nothing for the user to
  // acknowledge on a progress screen that has finished, and leaving them
  // to press Continue would make a completed install look stalled.
  useEffect(() => {
    if (step === "install" && provisioningPhase === "succeeded") next();
  }, [step, provisioningPhase, next]);

  const diagnosticsAvailable = Boolean(getInstallationStatus && verifyInstallation);

  return (
    <div className="mx-auto flex h-svh max-w-3xl flex-col gap-6 p-8">
      <div className="flex items-center gap-3">
        <div className="flex-1">
          <ProgressRail currentIndex={stepIndex} />
        </div>
        {/* Reachable from every step, not just Welcome or a failure
            screen: "does something already exist here, and is it
            healthy" is useful at any point in a fresh install too, and
            tying it to one screen would hide it from the rest. Hidden
            entirely rather than shown disabled when the host cannot
            answer it -- the same "offered only when actionable" rule
            Cancel/Launch/Open Folder/Repair already follow. */}
        {diagnosticsAvailable && (
          <Button
            variant="ghost"
            size="sm"
            className="shrink-0 gap-1.5 text-muted-foreground"
            onClick={() => setDiagnosticsOpen(true)}
          >
            <Stethoscope className="size-4" aria-hidden="true" />
            Diagnostics
          </Button>
        )}
      </div>

      {/* Automatic, wizard-wide notice -- not shown on the progress or
          completion screens, which already say "Resuming installation…"
          in their own words once a run is under way; showing both would
          be two messages for one fact. */}
      {hasExistingInstallation && step !== "install" && step !== "ready" && (
        <p className="flex items-start gap-2 rounded-lg border border-border/60 bg-muted/30 p-3 text-secondary">
          <Info className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          An installation already exists at this location. Continuing will update it —
          anything already set up is kept.
        </p>
      )}

      {/* `key` on the step remounts it, which resets scroll position and
          focus to the top of each step — a wizard that keeps the
          previous step's scroll offset feels broken. */}
      <main key={step} className="flex min-h-0 flex-1 flex-col overflow-auto">
        {step === "welcome" && <WelcomeStep />}
        {step === "license" && <LicenseStep />}
        {step === "location" && <LocationStep defaultLocation={defaultLocation} />}
        {step === "account" && <AccountStep />}
        {step === "hardware" && <HardwareStep plan={plan} scanning={scanning} error={planError} />}
        {step === "calibration" && plan && <CalibrationStep plan={plan} />}
        {step === "model" && plan && <ModelStep plan={plan} />}
        {step === "voice" && plan && <VoiceStep plan={plan} />}
        {step === "summary" && plan && <SummaryStep plan={plan} />}
        {step === "install" && (
          <InstallProgressStep onRetry={startProvisioning} onCancel={cancelProvisioning} />
        )}
        {step === "ready" && plan && (
          <CompletionStep
            plan={plan}
            version={version}
            onLaunch={onLaunch}
            onOpenFolder={onOpenFolder}
            onRepair={onRepair}
          />
        )}
      </main>

      <footer className="flex shrink-0 items-center justify-between gap-3">
        <Button
          variant="ghost"
          onClick={back}
          disabled={stepIndex === 0}
          className="gap-1.5"
        >
          <ChevronLeft className="size-4" aria-hidden="true" />
          Back
        </Button>

        <span className="text-muted-foreground text-xs" aria-live="polite">
          Step {stepIndex + 1} of {INSTALLER_STEPS.length} — {STEP_TITLES[step]}
        </span>

        <Button
          onClick={next}
          disabled={!advanceable}
          className="gap-1.5"
        >
          {step === "summary" ? "Install" : "Continue"}
          <ChevronRight className="size-4" aria-hidden="true" />
        </Button>
      </footer>

      {getInstallationStatus && verifyInstallation && (
        <DiagnosticsDialog
          open={diagnosticsOpen}
          onOpenChange={setDiagnosticsOpen}
          location={installLocation ?? defaultLocation}
          accountType={accountType}
          getStatus={getInstallationStatus}
          verify={verifyInstallation}
          checkDependencies={checkDependencies ?? (() => Promise.reject(new Error("Dependency checks are unavailable.")))}
          onRepair={onRepair}
          onOpenLogFolder={onOpenLogFolder}
        />
      )}
    </div>
  );
}

/** A plain progress indicator rather than clickable step links: steps
 *  depend on their predecessors (the scan needs a location and an
 *  account type), so an arbitrary jump would produce a half-configured
 *  install. */
function ProgressRail({ currentIndex }: { currentIndex: number }) {
  const total = INSTALLER_STEPS.length;
  const percent = ((currentIndex + 1) / total) * 100;

  return (
    <div className="flex shrink-0 flex-col gap-2">
      <div
        className="h-1 overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuenow={currentIndex + 1}
        aria-valuemin={1}
        aria-valuemax={total}
        aria-label="Installation progress"
      >
        <div
          className="h-full rounded-full bg-primary transition-[width] duration-300"
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}
