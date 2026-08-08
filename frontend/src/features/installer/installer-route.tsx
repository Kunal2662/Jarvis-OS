import { useCallback } from "react";
import { InstallerWizard } from "@/features/installer/installer-wizard";
import { useInstallerStore } from "@/features/installer/installer-store";
import {
  cancelProvisioningViaHost,
  checkDependenciesViaHost,
  getInstallationStatusViaHost,
  isHostBridgeAvailable,
  openLogFolderViaHost,
  repairInstallationViaHost,
  runProvisioningViaHost,
  verifyInstallationViaHost,
} from "@/features/installer/provisioning-transport";
import type { InstallationPlan } from "@/features/installer/installer-types";
import type { VerificationReport } from "@/features/installer/provisioning-types";

/**
 * The installer's route element -- M22 installer UI.
 *
 * Task Groups A and B built `InstallerWizard` and the provisioning
 * engine but left the wizard **mounted nowhere**: it had no route, so
 * nothing in the running application could reach it. This is that entry
 * point, and it is the composition root where the injected `loadPlan`
 * and `runProvisioning` are bound to real implementations.
 *
 * `/install` is deliberately not a module route. It has no
 * `MODULE_DEFINITIONS` entry and never appears in the Sidebar, for the
 * same reason `/workspace` does not: it is a shell surface, not a module
 * a user could enable or disable.
 */

/** Where the plan comes from. Same bridge as provisioning, same reason
 *  it may be absent — see `provisioning-transport.ts`. */
async function loadPlanViaHost(input: {
  location: string;
  accountType: "personal" | "administrator";
}): Promise<InstallationPlan> {
  const host = (globalThis as { __TAURI__?: { core?: { invoke?: (c: string, a?: unknown) => Promise<unknown> } } })
    .__TAURI__;

  if (!host?.core?.invoke) {
    throw new Error(
      "Checking this device needs the JARVIS desktop application. " +
        "Open the installer from the desktop app to continue.",
    );
  }

  return (await host.core.invoke("load_installation_plan", input)) as InstallationPlan;
}

/**
 * The folder proposed when the host has not supplied one.
 *
 * A *proposal*, not a decision: the Location step exists precisely so
 * the user can change it, and the backend measures free space on
 * whatever they end up choosing. Defaulting to `""` instead left the
 * field looking filled while `canAdvance` saw nothing, so Continue was
 * permanently disabled with no explanation — the same class of bug as
 * the one Task Group A's own flow test caught, in the one code path that
 * test could not reach because it supplied a location itself.
 *
 * Mirrors `default_install_location()`: `%LOCALAPPDATA%` on Windows,
 * `~/.jarvis` elsewhere. Per-user, so no elevation is needed.
 */
function proposedLocation(): string {
  const onWindows = /win/i.test(navigator.userAgent);
  return onWindows ? String.raw`%LOCALAPPDATA%\JARVIS` : "~/.jarvis";
}

export interface InstallerRouteProps {
  /** Overridable so tests and a future packaged shell can supply their
   *  own transports without this module knowing which host it is in. */
  loadPlan?: typeof loadPlanViaHost;
  runProvisioning?: typeof runProvisioningViaHost;
  defaultLocation?: string;
  version?: string;
}

export function InstallerRoute({
  loadPlan = loadPlanViaHost,
  runProvisioning = runProvisioningViaHost,
  defaultLocation,
  version = "",
}: InstallerRouteProps) {
  const bridged = isHostBridgeAvailable();
  const location = defaultLocation || proposedLocation();
  // Read, never written here: the Account step owns this choice.
  // `onRepair` is only reachable from the completion screen, which every
  // earlier step's `canAdvance` check already requires an account type
  // to reach -- so this is `null` only in a state the repair action
  // itself guards against below, not one the wizard flow can produce.
  const accountType = useInstallerStore((s) => s.accountType);

  const onCancel = useCallback(() => {
    void cancelProvisioningViaHost();
  }, []);

  const onRepair = useCallback(
    async (step: string): Promise<VerificationReport> => {
      if (!accountType) {
        throw new Error("Repair needs an account type, and none has been chosen yet.");
      }
      await repairInstallationViaHost({ location, accountType, step });
      // Re-verify rather than trust the repair's own result: a repair
      // can complete having failed a *later* step (a blocked download)
      // without the check that triggered it ever running again.
      return verifyInstallationViaHost({ location, accountType });
    },
    [location, accountType],
  );

  const onLaunch = useCallback(() => {
    const host = (globalThis as { __TAURI__?: { core?: { invoke?: (c: string) => Promise<unknown> } } })
      .__TAURI__;
    void host?.core?.invoke?.("launch_application");
  }, []);

  const onOpenFolder = useCallback(() => {
    const host = (globalThis as { __TAURI__?: { core?: { invoke?: (c: string) => Promise<unknown> } } })
      .__TAURI__;
    void host?.core?.invoke?.("open_installation_folder");
  }, []);

  const onOpenLogFolder = useCallback(() => {
    void openLogFolderViaHost();
  }, []);

  return (
    <InstallerWizard
      loadPlan={loadPlan}
      runProvisioning={runProvisioning}
      defaultLocation={location}
      version={version}
      // `null` rather than a no-op: the completion screen disables the
      // button with a reason, which tells the user why it cannot act
      // instead of appearing to work and doing nothing.
      // Same rule as the two below: offered only when a host can
      // actually act on it.
      cancelProvisioning={bridged ? onCancel : null}
      onLaunch={bridged ? onLaunch : null}
      onOpenFolder={bridged ? onOpenFolder : null}
      onRepair={bridged ? onRepair : null}
      // Diagnostics is offered whenever the bridge exists; unlike the
      // repair/launch/folder actions it needs no account type to be
      // useful (the dialog itself skips verification without one).
      getInstallationStatus={bridged ? getInstallationStatusViaHost : undefined}
      verifyInstallation={bridged ? verifyInstallationViaHost : undefined}
      checkDependencies={bridged ? checkDependenciesViaHost : undefined}
      onOpenLogFolder={bridged ? onOpenLogFolder : null}
    />
  );
}
