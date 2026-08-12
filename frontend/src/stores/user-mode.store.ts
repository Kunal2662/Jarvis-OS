import { create } from "zustand";
import { atLeast, canReveal, type RestrictedInformation, type UserMode } from "@/core/user-mode";
import { useDeveloperModeStore } from "@/stores/developer-mode.store";

/**
 * The app's current audience -- the React-facing read of
 * `core/user-mode.ts`.
 *
 * **Derived, not stored.** The mode comes from Developer Mode's existing
 * session unlock (`stores/developer-mode.store.ts`, Phase 1) plus an
 * administrator flag. Keeping a second independent copy of "is developer
 * mode on" is the duplicate-state failure this project's rules single
 * out, and here it would be a *security* failure: two flags that can
 * disagree about whether provider names may be shown will eventually
 * disagree in the permissive direction.
 *
 * **Never persisted.** Developer Mode re-locks on every restart, by
 * design (the PySide6 gate behaved the same way). A persisted
 * administrator flag would be a privilege that survives without
 * re-authentication, which is the wrong default for something whose real
 * backend gate does not exist yet.
 */
interface UserModeState {
  /** Set only after the backend confirms an administrator. No backend
   *  account model exists yet (`ARCHITECTURE.md` §22.11 is approved, not
   *  built), so nothing sets this to `true` in production today -- and
   *  the gates are written and tested as though it could. */
  isAdministrator: boolean;
  setAdministrator: (value: boolean) => void;
}

const useUserModeState = create<UserModeState>()((set) => ({
  isAdministrator: false,
  setAdministrator: (value) => set({ isAdministrator: value }),
}));

/** The one place the current mode is decided. */
export function resolveUserMode(): UserMode {
  if (useUserModeState.getState().isAdministrator) return "administrator";
  return useDeveloperModeStore.getState().isUnlocked ? "developer" : "personal";
}

/** Reactive read for components. Subscribes to both underlying stores,
 *  so unlocking Developer Mode re-renders every gated surface at once. */
export function useUserMode(): UserMode {
  const isAdministrator = useUserModeState((s) => s.isAdministrator);
  const isUnlocked = useDeveloperModeStore((s) => s.isUnlocked);
  if (isAdministrator) return "administrator";
  return isUnlocked ? "developer" : "personal";
}

/** `true` when the current audience may see this class of information.
 *  The hook every §22.12-restricted surface calls. */
export function useCanReveal(information: RestrictedInformation): boolean {
  return canReveal(useUserMode(), information);
}

/** `true` when the current audience is at least `required`. */
export function useHasMode(required: UserMode): boolean {
  return atLeast(useUserMode(), required);
}

export const setAdministrator = (value: boolean): void =>
  useUserModeState.getState().setAdministrator(value);

/** Test seam. */
export function resetUserModeForTesting(): void {
  useUserModeState.setState({ isAdministrator: false });
  useDeveloperModeStore.getState().lock();
}
