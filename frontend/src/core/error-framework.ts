/**
 * The Error Framework (Task 13) -- derives one standardized rendering
 * state from a module's real `ModuleLifecycle` state (module-lifecycle.ts)
 * plus its current permission/auth context, so every module's UI picks
 * from the same fixed set of screens instead of each inventing its own
 * loading/empty/error treatment.
 */

import type { ConnectionState, ModuleState } from "@/core/module-lifecycle";

export type ViewState =
  | "loading"
  | "ready"
  | "empty"
  | "offline"
  | "error"
  | "permission_denied"
  | "auth_required"
  | "config_required";

const LOADING_STATES: readonly ConnectionState[] = ["connecting", "syncing"];

export interface ViewStateContext {
  moduleState: ModuleState;
  /** From `permission-framework.ts`'s `isGranted()` -- `false` only
   *  when a required permission was actually checked and denied, not
   *  merely "not yet asked." */
  requiredPermissionDenied?: boolean;
}

/**
 * The single place `ConnectionState` (a lifecycle concept) maps to
 * `ViewState` (a rendering concept) -- a module's UI never inspects
 * `ConnectionState` directly, always through this function, so the two
 * vocabularies can evolve independently (e.g. a future lifecycle state
 * that doesn't need its own dedicated screen).
 */
export function deriveViewState({ moduleState, requiredPermissionDenied }: ViewStateContext): ViewState {
  if (requiredPermissionDenied) return "permission_denied";

  switch (moduleState.state) {
    case "not_installed":
    case "not_configured":
      return "config_required";
    case "authenticating":
      return "auth_required";
    case "connecting":
    case "syncing":
      return "loading";
    case "connected":
    case "ready":
      return "ready";
    case "empty":
      return "empty";
    case "offline":
    case "disconnected":
      return "offline";
    case "error":
      return "error";
    case "shutdown":
      return "offline"; // nothing left to show beyond "not available right now"
  }
}

export function isLoadingState(state: ConnectionState): boolean {
  return LOADING_STATES.includes(state);
}
