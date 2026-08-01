import { create } from "zustand";
import { persist } from "zustand/middleware";

interface WindowState {
  /** Last-known, non-maximized size -- used to restore after un-maximizing.
   *  The live window chrome state itself (actually resizing the OS window)
   *  is owned by Tauri's window API, called from a window *service*, not
   *  this store -- this store only remembers the UI's last preference. */
  width: number;
  height: number;
  isMaximized: boolean;
  isFullscreen: boolean;
  setSize: (width: number, height: number) => void;
  setMaximized: (isMaximized: boolean) => void;
  setFullscreen: (isFullscreen: boolean) => void;
}

export const useWindowStore = create<WindowState>()(
  persist(
    (set) => ({
      width: 1280,
      height: 800,
      isMaximized: false,
      isFullscreen: false,
      setSize: (width, height) => set({ width, height }),
      setMaximized: (isMaximized) => set({ isMaximized }),
      setFullscreen: (isFullscreen) => set({ isFullscreen }),
    }),
    { name: "jarvis.window" },
  ),
);
