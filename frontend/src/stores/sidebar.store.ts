import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SidebarState {
  isCollapsed: boolean;
  toggle: () => void;
  setCollapsed: (collapsed: boolean) => void;
}

/**
 * UI state only -- collapsed/expanded, persisted across restarts. Which
 * items exist and what they navigate to is `ApplicationRegistry`'s
 * concern (`core/application-registry.ts`); which one is *active* is
 * `WorkspaceManager`'s (`stores/workspace.store.ts`) -- this store used
 * to also carry an `activeItemId` field, but nothing ever read it (the
 * real active-item source has always been routing, now formalized as
 * WorkspaceManager). Removed rather than wired up in Phase 3 Task Group
 * C, per that task's own rule against a second, duplicate active-state
 * tracker sitting next to the real one.
 */
export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      isCollapsed: false,
      toggle: () => set((s) => ({ isCollapsed: !s.isCollapsed })),
      setCollapsed: (collapsed) => set({ isCollapsed: collapsed }),
    }),
    { name: "jarvis.sidebar", partialize: (s) => ({ isCollapsed: s.isCollapsed }) },
  ),
);
