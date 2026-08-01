import { useEffect } from "react";
import { useThemeStore } from "@/stores/theme.store";

/**
 * Syncs the Zustand theme store onto the `data-theme` attribute on
 * `<html>`, which is what `styles/themes.css` actually keys off. No
 * theme logic lives here beyond that sync -- the three themes'
 * definitions live entirely in CSS.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const theme = useThemeStore((s) => s.theme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    // Kept in sync for any third-party component that only recognizes
    // Tailwind's own `dark:` class convention (see themes.css's `.dark`
    // alias).
    document.documentElement.classList.toggle("dark", theme === "dark" || theme === "jarvis");
  }, [theme]);

  return children;
}
