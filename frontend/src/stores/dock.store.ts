import { create } from "zustand";
import { persist } from "zustand/middleware";

interface DockState {
  pinnedItemIds: string[];
  pin: (id: string) => void;
  unpin: (id: string) => void;
  isPinned: (id: string) => boolean;
}

/**
 * UI state only -- which item ids are pinned to the dock, in order.
 * Per ARCHITECTURE.md section 14's Dock Behavior standard: pin/unpin is
 * instant, no confirmation dialog.
 */
export const useDockStore = create<DockState>()(
  persist(
    (set, get) => ({
      pinnedItemIds: [],
      pin: (id) =>
        set((s) => (s.pinnedItemIds.includes(id) ? s : { pinnedItemIds: [...s.pinnedItemIds, id] })),
      unpin: (id) => set((s) => ({ pinnedItemIds: s.pinnedItemIds.filter((x) => x !== id) })),
      isPinned: (id) => get().pinnedItemIds.includes(id),
    }),
    { name: "jarvis.dock" },
  ),
);
