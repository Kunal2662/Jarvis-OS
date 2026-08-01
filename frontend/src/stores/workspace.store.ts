import { create } from "zustand";

interface WorkspaceState {
  /** The module id `WorkspaceManager` (core/workspace-manager.ts)
   *  currently has mounted, or `null` if the current route doesn't
   *  resolve to any registered module. Not persisted -- this reflects
   *  live mount state driven by the current route, not a user
   *  preference to restore on next launch. */
  activeModuleId: string | null;
  setActiveModuleId: (id: string | null) => void;
}

/**
 * UI-observable mirror of `WorkspaceManager`'s active-module state.
 * `WorkspaceManager` itself has no React import and cannot be
 * subscribed to directly by a component -- this store is how a future
 * component (Header, Sidebar's active-highlight, Developer Mode's
 * Lifecycle Viewer) reads that state reactively. `core/workspace-manager.ts`
 * writes to it directly via `getState()`, the same non-hook pattern
 * `core/notification-framework.ts` already uses for its own stores.
 */
export const useWorkspaceStore = create<WorkspaceState>((set) => ({
  activeModuleId: null,
  setActiveModuleId: (id) => set({ activeModuleId: id }),
}));
