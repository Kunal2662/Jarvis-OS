import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { ThemeName } from "@/types/theme";

interface ThemeState {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
}

/**
 * UI state only -- which theme is active. The actual color values live in
 * `styles/themes.css` as `[data-theme]` blocks; this store's only job is
 * remembering the user's choice across restarts and driving the
 * `data-theme` attribute (see providers/ThemeProvider.tsx).
 */
export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: "dark",
      setTheme: (theme) => set({ theme }),
    }),
    { name: "jarvis.theme" },
  ),
);
