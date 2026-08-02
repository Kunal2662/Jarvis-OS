import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/index.css";
import { registerCoreStatusBarItems } from "@/components/layout/status-bar-contributions";
import { registerCoreDashboardWidgets } from "@/features/dashboard/dashboard-widgets";
import { registerPlaceholderModules } from "@/modules/register-modules";
import { AppProviders } from "@/providers/app-providers";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found in index.html.");
}

/**
 * Registers every module with `ApplicationRegistry`, and Core JARVIS's
 * own built-in Status Bar items and Dashboard widgets with their
 * respective `ContributionRegistry` instances, before the app renders a
 * single route -- `WorkspaceManager` (Phase 3, Task Group B) resolves
 * the current path against the registry on first render, and the
 * Dashboard route renders immediately for `home`, so all three
 * registries must already be populated by then, not filled in
 * reactively after the fact. `registerCoreStatusBarItems()` and
 * `registerCoreDashboardWidgets()` are both synchronous (no async work,
 * unlike module `initialize()`), so they run before the `.then()`
 * rather than needing their own promise chain.
 */
registerCoreStatusBarItems();
registerCoreDashboardWidgets();
void registerPlaceholderModules().then(() => {
  createRoot(rootElement).render(
    <StrictMode>
      <AppProviders />
    </StrictMode>,
  );
});
