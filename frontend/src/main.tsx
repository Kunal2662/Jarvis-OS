import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "@/index.css";
import { AppProviders } from "@/providers/app-providers";

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("Root element #root not found in index.html.");
}

/**
 * Registering every module with `ApplicationRegistry`, and Core
 * JARVIS's own built-in Status Bar/Dashboard contributions, used to
 * happen here directly before the first render. As of Phase 4, Task
 * Group I, that real work moved into `core/startup-orchestrator.ts`,
 * run by `components/startup/startup-gate.tsx` (mounted inside
 * `AppProviders`) alongside the cinematic startup sequence -- the app
 * can render immediately; `StartupGate` is what actually waits for the
 * registries to be populated before revealing the real route tree.
 */
createRoot(rootElement).render(
  <StrictMode>
    <AppProviders />
  </StrictMode>,
);
