import { create } from "zustand";
import { persist } from "zustand/middleware";

interface SidebarState {
  isCollapsed: boolean;
  toggle: () => void;
  setCollapsed: (collapsed: boolean) => void;
  /** Which nested parent groups (e.g. "ai") the user has expanded --
   *  extends this same store rather than a second one, per the UI
   *  Architecture Update's "do not create duplicate state" rule.
   *  "ai" ships expanded by default; toggling never affects whether a
   *  group's *active* child stays visible -- Sidebar itself
   *  auto-expands a group containing the active module regardless of
   *  this persisted preference. */
  expandedGroupIds: string[];
  toggleGroup: (groupId: string) => void;
}

/**
 * UI state only -- collapsed/expanded and expanded-group ids, both
 * persisted across restarts. Which items exist and what they navigate
 * to is `ApplicationRegistry`'s concern (`core/application-registry.ts`);
 * which one is *active* is `WorkspaceManager`'s
 * (`stores/workspace.store.ts`) -- this store used to also carry an
 * `activeItemId` field, but nothing ever read it (the real active-item
 * source has always been routing, now formalized as WorkspaceManager).
 * Removed rather than wired up in Phase 3 Task Group C, per that
 * task's own rule against a second, duplicate active-state tracker
 * sitting next to the real one.
 */
export const useSidebarStore = create<SidebarState>()(
  persist(
    (set) => ({
      isCollapsed: false,
      toggle: () => set((s) => ({ isCollapsed: !s.isCollapsed })),
      setCollapsed: (collapsed) => set({ isCollapsed: collapsed }),
      expandedGroupIds: ["ai"],
      toggleGroup: (groupId) =>
        set((s) => ({
          expandedGroupIds: s.expandedGroupIds.includes(groupId)
            ? s.expandedGroupIds.filter((id) => id !== groupId)
            : [...s.expandedGroupIds, groupId],
        })),
    }),
    {
      name: "jarvis.sidebar",
      partialize: (s) => ({ isCollapsed: s.isCollapsed, expandedGroupIds: s.expandedGroupIds }),
    },
  ),
);
