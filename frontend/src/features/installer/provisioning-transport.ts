import type {
  DependencyReport,
  InstallationStatus,
  ProvisioningEvent,
  RepairResult,
  VerificationReport,
} from "@/features/installer/provisioning-types";

/**
 * How the installer UI reaches the provisioning engine -- M22 installer
 * UI.
 *
 * The engine is a Python package invoked as
 * `python -m jarvis.installer provision --stream`, which emits
 * newline-delimited JSON. Something has to spawn that process and relay
 * its stdout, and in a Tauri application that something is the Rust
 * side.
 *
 * ### Where the host side lives
 *
 * `src-tauri/src/installer.rs`, added by M22 Task Group C. This file
 * remains the **specification**: the command names and the event name
 * below are what the Rust side implements, not the other way round. The
 * shapes did not change when the bridge landed, which is what the
 * contract-first split was for.
 *
 * The bridge can still be absent at runtime — the installer also runs in
 * a plain browser during development, where no host exists. That case
 * **rejects with a readable reason** rather than hanging on a screen
 * that says "Preparing…" forever. `classifyFailure` turns the message
 * into friendly copy and offers a Retry.
 *
 * A stub that resolved immediately, or one that emitted invented
 * progress, would make the installer *look* complete while installing
 * nothing — the exact failure mode this project's "no fake data" rule
 * exists to prevent.
 */

/** The Rust command Task Group C implements. */
export const PROVISION_COMMAND = "run_provisioning";

/** Asks a running installation to stop. */
export const CANCEL_COMMAND = "cancel_provisioning";

/** The Tauri event each NDJSON line is relayed on. */
export const PROVISION_EVENT = "provisioning://event";

export interface ProvisioningTransportInput {
  location: string;
  accountType: "personal" | "administrator";
  onEvent: (event: ProvisioningEvent) => void;
}

interface TauriGlobal {
  core?: { invoke?: (command: string, args?: unknown) => Promise<unknown> };
  event?: {
    listen?: (
      name: string,
      handler: (message: { payload: unknown }) => void,
    ) => Promise<() => void>;
  };
}

function tauri(): TauriGlobal | null {
  // Tauri injects `__TAURI__` into the window. Feature-detected rather
  // than imported so a browser build neither bundles nor throws.
  const candidate = (globalThis as { __TAURI__?: TauriGlobal }).__TAURI__;
  return candidate ?? null;
}

export function isHostBridgeAvailable(): boolean {
  const host = tauri();
  return Boolean(host?.core?.invoke && host.event?.listen);
}

/**
 * Parse one relayed line into an event, or `null`.
 *
 * Exported because the line-to-event step is the part worth testing on
 * its own: it is where a malformed or partial line from a real process
 * would otherwise become a crash mid-installation. A line that does not
 * parse is skipped rather than thrown — losing one progress update is
 * recoverable, aborting an installation over it is not.
 */
export function parseEventLine(line: string): ProvisioningEvent | null {
  const trimmed = line.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed) as { event?: unknown };
    if (parsed.event !== "progress" && parsed.event !== "result") return null;
    return parsed as ProvisioningEvent;
  } catch {
    return null;
  }
}

/**
 * Run provisioning through the host bridge.
 *
 * Rejects — rather than resolving quietly — when the bridge is absent,
 * so the installer shows a failure with a Retry instead of a progress
 * bar that never moves.
 */
export async function runProvisioningViaHost({
  location,
  accountType,
  onEvent,
}: ProvisioningTransportInput): Promise<void> {
  const host = tauri();
  if (!host?.core?.invoke || !host.event?.listen) {
    throw new Error(
      "Installation needs the JARVIS desktop application. " +
        "Open the installer from the desktop app to continue.",
    );
  }

  const unlisten = await host.event.listen(PROVISION_EVENT, (message) => {
    const payload = message.payload;
    const event =
      typeof payload === "string" ? parseEventLine(payload) : (payload as ProvisioningEvent | null);
    if (event && (event.event === "progress" || event.event === "result")) onEvent(event);
  });

  try {
    await host.core.invoke(PROVISION_COMMAND, { location, accountType });
  } finally {
    // Always detach: a listener surviving a failed run would deliver a
    // later installation's events into a dead screen.
    unlisten();
  }
}

/**
 * Ask the host to stop the running installation.
 *
 * Resolves either way. The outcome the user sees comes from
 * `runProvisioningViaHost` rejecting with a message containing
 * "cancelled" — which `classifyFailure` already maps to the cancelled
 * state — so a failure to deliver the request must not produce a second,
 * competing error on top of it. If the host never stops the process, the
 * run simply continues, which is visible on screen.
 */
export async function cancelProvisioningViaHost(): Promise<void> {
  try {
    await tauri()?.core?.invoke?.(CANCEL_COMMAND);
  } catch {
    // Intentionally swallowed; see above.
  }
}

// --- M22 Task Group D: diagnostics, verification and repair -----------
//
// Five more commands, all non-streaming: the host runs an already-shipped
// CLI subcommand to completion and returns its one JSON document. Each
// rejects with a readable reason when the bridge is absent, same as
// `runProvisioningViaHost` above and for the same reason -- a screen that
// silently shows nothing is indistinguishable from one that is still
// loading.

/** The Rust commands Task Group D implements. */
export const DEPENDENCIES_COMMAND = "check_dependencies";
export const STATUS_COMMAND = "get_installation_status";
export const VERIFY_COMMAND = "verify_installation";
export const REPAIR_COMMAND = "repair_installation";
export const OPEN_LOG_FOLDER_COMMAND = "open_log_folder";

/**
 * Shared by the five functions below.
 *
 * Extracted rather than left inline in each: this file has real test
 * coverage (`provisioning-transport.test.ts`), so — unlike the Rust side
 * of this same task group, which has none without a toolchain — a
 * mistake introduced by sharing this logic would be caught here, which
 * is what makes the same DRY move safe on this side and not on that one.
 */
async function invokeJson<T>(
  command: string,
  args: Record<string, unknown>,
  unavailableMessage: string,
): Promise<T> {
  const host = tauri();
  if (!host?.core?.invoke) {
    throw new Error(unavailableMessage);
  }
  return (await host.core.invoke(command, args)) as T;
}

/** Detect runtime dependencies (Python, Git, CUDA, DirectML, ONNX
 *  Runtime, Visual C++). Installs nothing. */
export async function checkDependenciesViaHost(input: {
  location: string;
  accountType: "personal" | "administrator";
}): Promise<DependencyReport> {
  return invokeJson<DependencyReport>(
    DEPENDENCIES_COMMAND,
    input,
    "Checking dependencies needs the JARVIS desktop application.",
  );
}

/** What provisioning has completed at this location, and whether an
 *  installation already exists here. */
export async function getInstallationStatusViaHost(location: string): Promise<InstallationStatus> {
  return invokeJson<InstallationStatus>(
    STATUS_COMMAND,
    { location },
    "Checking installation status needs the JARVIS desktop application.",
  );
}

/** Verify an existing installation: nine checks, each carrying a
 *  verdict and, when repairable, a step `repairInstallationViaHost`
 *  accepts directly. */
export async function verifyInstallationViaHost(input: {
  location: string;
  accountType: "personal" | "administrator";
}): Promise<VerificationReport> {
  return invokeJson<VerificationReport>(
    VERIFY_COMMAND,
    input,
    "Verifying this installation needs the JARVIS desktop application.",
  );
}

/**
 * Redo one step and everything after it.
 *
 * Not streamed — the CLI's `repair` subcommand has no `--stream` flag,
 * so a repair that re-downloads a large artefact blocks with no live
 * progress until it resolves. Callers show an honest, indeterminate
 * busy state rather than a percentage this call cannot produce.
 */
export async function repairInstallationViaHost(input: {
  location: string;
  accountType: "personal" | "administrator";
  step: string;
}): Promise<RepairResult> {
  return invokeJson<RepairResult>(REPAIR_COMMAND, input, "Repairing this installation needs the JARVIS desktop application.");
}

/**
 * Reveal the installer's log folder.
 *
 * Resolves either way, same as `cancelProvisioningViaHost`: this is a
 * convenience action on a diagnostics screen, and a failure to open a
 * folder should not itself become a second error competing with
 * whatever the user was already trying to diagnose.
 */
export async function openLogFolderViaHost(): Promise<void> {
  try {
    await tauri()?.core?.invoke?.(OPEN_LOG_FOLDER_COMMAND);
  } catch {
    // Intentionally swallowed; see above.
  }
}
