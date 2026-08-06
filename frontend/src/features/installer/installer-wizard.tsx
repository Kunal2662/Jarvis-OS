import { useEffect, useRef } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AccountStep,
  CalibrationStep,
  HardwareStep,
  InstallStep,
  LicenseStep,
  LocationStep,
  ModelStep,
  ReadyStep,
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
}

export function InstallerWizard({ loadPlan, defaultLocation }: InstallerWizardProps) {
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

  return (
    <div className="mx-auto flex h-svh max-w-3xl flex-col gap-6 p-8">
      <ProgressRail currentIndex={stepIndex} />

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
        {step === "install" && <InstallStep />}
        {step === "ready" && plan && <ReadyStep plan={plan} />}
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
