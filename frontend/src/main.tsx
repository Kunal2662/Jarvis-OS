import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/index.css";
import { registerCoreStatusBarItems } from "@/components/layout/status-bar-contributions";
import { registerPlaceholderModules } from "@/modules/register-modules";
import { AppProviders } from "@/providers/app-providers";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found in index.html.");
}

/**
 * Registers every module with `ApplicationRegistry`, and Core JARVIS's
 * own built-in Status Bar items with `statusBarRegistry`, before the
 * app renders a single route -- `WorkspaceManager` (Phase 3, Task Group
 * B) resolves the current path against the registry on first render, so
 * both registries must already be populated by then, not filled in
 * reactively after the fact. `registerCoreStatusBarItems()` is
 * synchronous (no async work, unlike module `initialize()`), so it runs
 * before the `.then()` rather than needing its own promise chain.
 */
registerCoreStatusBarItems();
void registerPlaceholderModules().then(() => {
  createRoot(rootElement).render(
    <StrictMode>
      <AppProviders />
    </StrictMode>,
  );
});
