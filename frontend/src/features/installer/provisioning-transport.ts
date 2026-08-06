import type { ProvisioningEvent } from "@/features/installer/provisioning-types";

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
 * ### What exists today, stated plainly
 *
 * **The host bridge is not built.** `@tauri-apps/plugin-shell` is not a
 * dependency of this project and no Rust command exists to spawn a
 * process; adding either is packaging work (Task Group C), and quietly
 * adding a dependency to make a screen look finished would be the wrong
 * call to make unilaterally.
 *
 * So this module does two honest things instead of one dishonest one:
 *
 * 1. It **defines the contract** the Rust side must satisfy — one
 *    command and one event name — so Task Group C implements against a
 *    written interface rather than inventing one, and the UI needs no
 *    change on the day it lands.
 * 2. When the host cannot provide it, it **rejects with a readable
 *    reason** rather than hanging on a screen that says "Preparing…"
 *    forever. `classifyFailure` turns that into friendly copy and the
 *    user gets a Retry, which is the correct behaviour for a capability
 *    that may genuinely appear later in the session.
 *
 * A stub that resolved immediately, or one that emitted invented
 * progress, would make the installer *look* complete while installing
 * nothing — the exact failure mode this project's "no fake data" rule
 * exists to prevent.
 */

/** The Rust command Task Group C implements. */
export const PROVISION_COMMAND = "run_provisioning";

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
