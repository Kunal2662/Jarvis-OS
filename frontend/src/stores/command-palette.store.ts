import { create } from "zustand";

interface CommandPaletteState {
  isOpen: boolean;
  open: () => void;
  close: () => void;
  toggle: () => void;
}

/**
 * UI state only -- open/closed. Deliberately NOT `persist`-backed unlike
 * `sidebar.store.ts`/`dock.store.ts`: a command palette that reopens
 * itself on the next launch would be a real UX bug, not a preference
 * worth remembering, so this always starts closed.
 */
export const useCommandPaletteStore = create<CommandPaletteState>()((set) => ({
  isOpen: false,
  open: () => set({ isOpen: true }),
  close: () => set({ isOpen: false }),
  toggle: () => set((s) => ({ isOpen: !s.isOpen })),
}));
