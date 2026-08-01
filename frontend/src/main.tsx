import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/index.css";
import { registerPlaceholderModules } from "@/modules/register-modules";
import { AppProviders } from "@/providers/app-providers";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found in index.html.");
}

/**
 * Registers every module with `ApplicationRegistry` before the app
 * renders a single route -- `WorkspaceManager` (Phase 3, Task Group B)
 * resolves the current path against the registry on first render, so
 * the registry must already be populated by then, not filled in
 * reactively after the fact. Deferred from Task Group A (Foundation)
 * intentionally: deciding when this runs relative to routing/mounting
 * was Task Group B's decision to make, not A's.
 */
void registerPlaceholderModules().then(() => {
  createRoot(rootElement).render(
    <StrictMode>
      <AppProviders />
    </StrictMode>,
  );
});
