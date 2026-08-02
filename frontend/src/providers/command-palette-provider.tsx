import { useEffect } from "react";
import { useCommandPaletteStore } from "@/stores/command-palette.store";

/**
 * Wires the global Command Palette shortcut app-wide (Phase 3, Task
 * Group G) -- the exact `useEffect` + `window` keydown + cleanup idiom
 * `providers/developer-provider.tsx` already established for
 * `Ctrl+Shift+D`, not a new pattern.
 *
 * Binds BOTH `Ctrl+K` and `Ctrl+Shift+P`: `docs/MASTER_ROADMAP.md`
 * (M11B) and `docs/IMPLEMENTATION_ROADMAP.md` (Phase 3 checklist) both
 * name `Ctrl+Shift+P` as the canonical binding, but
 * `components/layout/header.tsx`'s existing Search button already
 * visually promises "Ctrl+K" to users since Phase 1 -- honoring only
 * one would silently break the other's promise, so both open the same
 * palette rather than picking one and leaving the other's UI dishonest.
 */
export function CommandPaletteProvider({ children }: { children: React.ReactNode }) {
  const toggle = useCommandPaletteStore((s) => s.toggle);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      const key = event.key.toLowerCase();
      const isCtrlK = event.ctrlKey && !event.shiftKey && key === "k";
      const isCtrlShiftP = event.ctrlKey && event.shiftKey && key === "p";
      if (isCtrlK || isCtrlShiftP) {
        event.preventDefault();
        toggle();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [toggle]);

  return children;
}
