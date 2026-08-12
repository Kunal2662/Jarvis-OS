import { create } from "zustand";
import {
  INSTALLER_STEPS,
  type AccountType,
  type InstallationPlan,
  type InstallerStep,
} from "@/features/installer/installer-types";

/**
 * The installer wizard's state -- M22 Task Group A.
 *
 * Deliberately **not persisted**. An installer is a single sitting; a
 * half-finished run restored a week later would replay a hardware scan
 * taken on different hardware, or worse, present a stale calibration as
 * current. Re-running takes seconds.
 *
 * The plan itself comes from `python -m jarvis.installer plan` and is
 * never edited here — a user changing the install location or account
 * type invalidates it, so `setLocation`/`setAccountType` clear it and
 * the Hardware step fetches again. Keeping a plan that no longer matches
 * its inputs is how an installer ends up installing something other than
 * what the summary described.
 */

interface InstallerState {
  step: InstallerStep;
  /** Steps the user has completed, so a back-and-forward does not
   *  re-run work that is still valid. */
  furthestStep: number;

  licenseAccepted: boolean;
  installLocation: string | null;
  accountType: AccountType | null;

  /** `null` until the scan completes. */
  plan: InstallationPlan | null;
  planError: string | null;
  scanning: boolean;

  next: () => void;
  back: () => void;
  goTo: (step: InstallerStep) => void;

  acceptLicense: (accepted: boolean) => void;
  setLocation: (path: string) => void;
  setAccountType: (type: AccountType) => void;

  beginScan: () => void;
  setPlan: (plan: InstallationPlan) => void;
  setPlanError: (message: string) => void;
  reset: () => void;
}

const FIRST_STEP: InstallerStep = INSTALLER_STEPS[0];

function indexOf(step: InstallerStep): number {
  return INSTALLER_STEPS.indexOf(step);
}

export const useInstallerStore = create<InstallerState>()((set, get) => ({
  step: FIRST_STEP,
  furthestStep: 0,
  licenseAccepted: false,
  installLocation: null,
  accountType: null,
  plan: null,
  planError: null,
  scanning: false,

  next: () => {
    const index = indexOf(get().step);
    if (index >= INSTALLER_STEPS.length - 1) return;
    const step = INSTALLER_STEPS[index + 1];
    set({ step, furthestStep: Math.max(get().furthestStep, index + 1) });
  },

  back: () => {
    const index = indexOf(get().step);
    if (index <= 0) return;
    set({ step: INSTALLER_STEPS[index - 1] });
  },

  // Only backwards, or forwards into ground already covered. Jumping
  // ahead would skip the license or the hardware scan the later steps
  // read from.
  goTo: (step) => {
    if (indexOf(step) <= get().furthestStep) set({ step });
  },

  acceptLicense: (accepted) => set({ licenseAccepted: accepted }),

  setLocation: (path) => {
    // Free space is measured on the target's volume, so a new location
    // invalidates the plan rather than merely annotating it.
    set({ installLocation: path, plan: null, planError: null });
  },

  setAccountType: (type) => {
    // The payload's *shape* depends on account type -- a personal plan
    // has no model id or resource limits. Reusing an administrator plan
    // for a personal install would leak exactly what §22.11 excludes.
    set({ accountType: type, plan: null, planError: null });
  },

  beginScan: () => set({ scanning: true, planError: null }),
  setPlan: (plan) => set({ plan, scanning: false, planError: null }),
  setPlanError: (message) => set({ planError: message, scanning: false, plan: null }),

  reset: () =>
    set({
      step: FIRST_STEP,
      furthestStep: 0,
      licenseAccepted: false,
      installLocation: null,
      accountType: null,
      plan: null,
      planError: null,
      scanning: false,
    }),
}));

/** Whether the current step's requirements are met. The Next button
 *  reads this rather than each step re-deciding, so a step cannot
 *  forget its own precondition. */
export function canAdvance(state: InstallerState): boolean {
  switch (state.step) {
    case "license":
      return state.licenseAccepted;
    case "location":
      return Boolean(state.installLocation);
    case "account":
      return state.accountType !== null;
    case "hardware":
    case "calibration":
    case "model":
    case "voice":
      // Every one of these renders the plan; none can be passed without it.
      return state.plan !== null;
    case "summary":
      return state.plan?.validation.can_install === true;
    case "install":
      return false; // advanced by the installation completing, not by the user
    default:
      return true;
  }
}
