import { registerCoreStatusBarItems } from "@/components/layout/status-bar-contributions";
import { registerAiDashboardWidgets } from "@/features/dashboard/ai-dashboard-registration";
import { registerCoreDashboardWidgets } from "@/features/dashboard/dashboard-widgets";
import { registerPlaceholderModules } from "@/modules/register-modules";
import { registerCorePanels } from "@/core/panel-registry";
import { installConnectionRecovery } from "@/services/backend-connection";
import { ensureRealtimeBridge } from "@/services/realtime-bridge";
import { useConnectionStore } from "@/stores/connection.store";
import { useWorkspaceLayoutStore } from "@/stores/workspace-layout.store";

export type StartupPriority = "high" | "medium" | "low";

export interface StartupTask {
  id: string;
  label: string;
  priority: StartupPriority;
  run: () => void | Promise<unknown>;
}

/**
 * The real work the startup animation (Phase 4, Task Group I) hides --
 * moved here from `main.tsx`, which used to call these directly. Tiers
 * follow the Premium UI & Voice Experience brief's own priority list
 * (Window/Theme/Core UI/Voice String/Dashboard Shell = high; Widgets/
 * Plugins/Memory/Notifications = medium; Background Services/
 * Analytics/Optional Modules/Cache Cleanup = low) mapped onto what
 * actually exists in this codebase today:
 *
 * - Window state and Theme are already handled before this ever runs
 *   (`StoreProvider`'s own hydration gate, `windowService`'s
 *   subscription in `DesktopShell`'s effect) -- nothing to duplicate
 *   here for them.
 * - Dashboard Shell = registering the Status Bar's and Dashboard's own
 *   core contributions (`registerCoreStatusBarItems`,
 *   `registerCoreDashboardWidgets`) -- both synchronous, real, and
 *   already existed as separate calls in `main.tsx`.
 * - "Widgets"/"Plugins" (medium) = `registerPlaceholderModules()`,
 *   since modules are this codebase's real stand-in for plugin-like
 *   units until M9's Plugin Loader exists.
 * - Memory, AI Providers, Command Palette's own backend, and Installed
 *   Plugins have **no real work to do today** -- no backend for any of
 *   them exists yet (the same gap Status Bar's "AI Provider"/"Voice
 *   Status" items already honestly report as "Not configured"). Per
 *   this project's "no fake data" rule, the `low` tier below is
 *   honestly empty rather than padded with fabricated delays just to
 *   fill out three tiers -- it becomes real once a real background
 *   service (cache cleanup, analytics, etc.) actually exists.
 *
 * **M8 Phase 2 makes the `low` tier real.** `backend-connection` reaches
 * the Python process, obtains a session and opens the WebSocket; it sits
 * in `low` because nothing above it needs the backend to have answered,
 * and it never rejects -- a backend that is not running resolves to an
 * explicit `unreachable` state that the UI renders, rather than throwing
 * and stalling the reveal. `realtime-bridge` runs *before* it, in
 * `medium`, so no relayed event can arrive before a handler exists.
 */
const STARTUP_TASKS: StartupTask[] = [
  { id: "status-bar", label: "Status Bar", priority: "high", run: registerCoreStatusBarItems },
  { id: "dashboard-widgets", label: "Dashboard Shell", priority: "high", run: registerCoreDashboardWidgets },
  // M8 Phase 5's eleven AI Dashboard widgets, joining the *same*
  // `dashboardWidgetRegistry` as the four above -- a second call into
  // one registry, not a second registry.
  { id: "ai-dashboard", label: "AI Dashboard", priority: "high", run: registerAiDashboardWidgets },
  // Register panels, *then* restore saved layouts -- in that order, in
  // one task, because the store's rehydrate drops panels whose
  // contribution is unknown. Restoring first would silently empty every
  // saved workspace. `workspace-layout.store.ts` sets `skipHydration`
  // for exactly this reason; this is the explicit trigger.
  {
    id: "panels",
    label: "Workspace Panels",
    priority: "high",
    run: () => {
      registerCorePanels();
      void useWorkspaceLayoutStore.persist.rehydrate();
    },
  },
  { id: "modules", label: "Modules", priority: "medium", run: registerPlaceholderModules },
  { id: "realtime-bridge", label: "Live Events", priority: "medium", run: ensureRealtimeBridge },
  {
    id: "backend-connection",
    label: "JARVIS Backend",
    priority: "low",
    run: async () => {
      // Recovery is installed *before* the first connect, so an attempt
      // that fails at startup (backend not up yet) is retried rather
      // than leaving the app offline until the user reloads.
      installConnectionRecovery();
      await useConnectionStore.getState().connect();
    },
  },
];

async function runTier(priority: StartupPriority): Promise<void> {
  const tasks = STARTUP_TASKS.filter((task) => task.priority === priority);
  await Promise.all(tasks.map((task) => task.run()));
}

let startupPromise: Promise<void> | null = null;

/**
 * Runs every real startup task, high priority first (the dashboard
 * shell/status bar registries the rest of the app assumes are already
 * populated), then medium. `low` has no tasks today (see above) but
 * the tier still runs -- awaited last, so a real future low-priority
 * task never blocks high/medium ones from finishing first.
 *
 * `components/startup/startup-gate.tsx` awaits this alongside the
 * startup animation's own choreographed duration and only reveals the
 * real app once both are done -- this is real synchronization, not a
 * cosmetic delay: `WorkspaceManager` needs `ApplicationRegistry`
 * genuinely populated before it resolves the initial route's module.
 *
 * Idempotent by design (caches and returns the same in-flight/settled
 * promise on every call) -- real initialization must happen exactly
 * once per app lifetime, and this function has more than one caller in
 * practice: `StartupGate`'s own effect runs twice under React
 * StrictMode's deliberate development-mode double-invoke, and a second
 * real call to `registerPlaceholderModules()` would throw (a module
 * can't register with `ApplicationRegistry` twice) -- silently
 * stalling the reveal forever, since the resulting promise rejection
 * had nothing awaiting/handling it. Caching here, at the one real
 * source of truth for "has startup work run yet," is more robust than
 * guarding each call site individually.
 */
export function runStartupSequence(): Promise<void> {
  startupPromise ??= (async () => {
    await runTier("high");
    await runTier("medium");
    await runTier("low");
  })();
  return startupPromise;
}

/** Test-only -- clears the cached promise so a fresh call actually
 *  re-runs the tiers. Production code never needs this: real
 *  initialization is meant to happen exactly once per app lifetime,
 *  by design (see above). */
export function __resetStartupSequenceForTests(): void {
  startupPromise = null;
}
