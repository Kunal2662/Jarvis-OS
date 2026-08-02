import { create } from "zustand";
import { persist } from "zustand/middleware";

interface ModuleEnablementState {
  /** Module ids the user has explicitly enabled -- distinct from
   *  `ApplicationRegistry`'s "registered" (code exists, can run):
   *  "installed and enabled" per the UI Architecture Update means
   *  registered AND present in this set. Core modules
   *  (`ModuleManifest.isCore`) are always enabled and never stored
   *  here -- `isModuleEnabled()` below treats `isCore` as an
   *  unconditional true, so a core module can never end up silently
   *  disabled by a stale or corrupted persisted set. */
  enabledModuleIds: string[];
  enableModule: (moduleId: string) => void;
  disableModule: (moduleId: string) => void;
}

export const useModuleEnablementStore = create<ModuleEnablementState>()(
  persist(
    (set) => ({
      enabledModuleIds: [],
      enableModule: (moduleId) =>
        set((s) => ({
          enabledModuleIds: s.enabledModuleIds.includes(moduleId)
            ? s.enabledModuleIds
            : [...s.enabledModuleIds, moduleId],
        })),
      disableModule: (moduleId) =>
        set((s) => ({ enabledModuleIds: s.enabledModuleIds.filter((id) => id !== moduleId) })),
    }),
    { name: "jarvis.module-enablement" },
  ),
);

/**
 * True if `moduleId` should render/participate anywhere in the UI --
 * core modules always are; everything else only if the user opted in.
 * A plain function, not a store selector, since it also needs the
 * manifest's `isCore` flag, which this store alone doesn't carry --
 * callers combine a registry lookup with this store's state (see
 * `components/layout/sidebar.tsx`).
 */
export function isModuleEnabled(isCore: boolean, moduleId: string, enabledModuleIds: string[]): boolean {
  return isCore || enabledModuleIds.includes(moduleId);
}
