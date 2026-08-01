import { useEffect } from "react";
import { useDeveloperModeStore } from "@/stores/developer-mode.store";

/**
 * Wires the global Developer Mode toggle shortcut (Ctrl+Shift+D, matching
 * the existing PySide6 build's convention) app-wide. This does NOT
 * perform authentication -- it only toggles whether the (locked, per
 * ARCHITECTURE.md section 17) Developer Panel is visible. The real
 * PBKDF2 unlock check happens against the backend once the API exists
 * (see services/api/); until then `unlock()` is unreachable from here by
 * design.
 */
export function DeveloperProvider({ children }: { children: React.ReactNode }) {
  const setActivePanel = useDeveloperModeStore((s) => s.setActivePanel);
  const activePanelId = useDeveloperModeStore((s) => s.activePanelId);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.ctrlKey && event.shiftKey && event.key.toLowerCase() === "d") {
        event.preventDefault();
        setActivePanel(activePanelId ? null : "overview");
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activePanelId, setActivePanel]);

  return children;
}
