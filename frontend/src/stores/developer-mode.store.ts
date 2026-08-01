import { create } from "zustand";

interface DeveloperModeState {
  /** Whether the Developer Panel is unlocked for this session. Real
   *  authentication (the PBKDF2 gate, per ARCHITECTURE.md section 17) is
   *  a backend concern -- this flag only tracks the UI's session state
   *  after the backend has already confirmed the password. Never
   *  persisted: every app restart re-locks Developer Mode, matching the
   *  existing PySide6 gate's own session-only behavior. */
  isUnlocked: boolean;
  activePanelId: string | null;
  unlock: () => void;
  lock: () => void;
  setActivePanel: (id: string | null) => void;
}

export const useDeveloperModeStore = create<DeveloperModeState>()((set) => ({
  isUnlocked: false,
  activePanelId: null,
  unlock: () => set({ isUnlocked: true }),
  lock: () => set({ isUnlocked: false, activePanelId: null }),
  setActivePanel: (id) => set({ activePanelId: id }),
}));
