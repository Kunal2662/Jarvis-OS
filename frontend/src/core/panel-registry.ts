/**
 * The Panel Registry -- M8 Phase 3's "every module behaves as a panel".
 *
 * A `ContributionRegistry` instance, not a new registry class. That
 * generic mechanism already exists precisely so Navigation, Dashboard
 * Widgets, Status Bar items and now Panels share one implementation
 * (`core/contribution-registry.ts`'s own header says so); a bespoke
 * `Map` here would be the fourth near-identical registry in a codebase
 * whose rules single out duplicate registries.
 *
 * **A panel is a contribution, not a route.** The distinction matters:
 * the router still owns one full-screen module per URL, and that is
 * unchanged. A panel is the same module's content rendered inside a
 * workspace layout alongside others. A module may have both, one, or
 * neither -- `panelRegistry` and `routes/router.tsx` read different data
 * and neither is derived from the other.
 *
 * **Nothing registers a panel it cannot fill.** Per this project's
 * standing "no fake data" rule, a module with no real content
 * contributes no panel rather than an empty shell with a title bar.
 * `registerCorePanels()` below is explicit about which modules have real
 * content today and which honestly do not.
 */

import { lazy, type ComponentType, type LazyExoticComponent } from "react";
import { ContributionRegistry, type Contribution } from "@/core/contribution-registry";
// Static, unlike every other panel below: `routes/router.tsx` imports
// this eagerly as the app's landing route, and a module statically
// imported anywhere cannot be split into its own chunk. Importing it
// dynamically here would produce a build warning and no second chunk.
import { DashboardGrid } from "@/features/dashboard/dashboard-grid";

/** Where a panel prefers to open when nothing has placed it yet. A
 *  user's own arrangement always wins over this; it is a first-open
 *  default, not a constraint. */
export type PanelZone = "left" | "main" | "right" | "bottom";

export interface PanelContribution extends Contribution {
  /** Shown in the panel's title bar and in the "add panel" menu. */
  title: string;
  /** Lucide icon name, matching `ModuleManifest.icon`'s convention. */
  icon: string;
  defaultZone: PanelZone;
  /**
   * The panel's content. Lazily imported for anything substantial --
   * a workspace can hold a dozen panels and eagerly importing every
   * module's content would pull the whole app into the initial bundle,
   * which is exactly what this phase's code-splitting requirement is
   * about. `panel-frame.tsx` renders it inside a `<Suspense>`.
   */
  render: ComponentType | LazyExoticComponent<ComponentType>;
  /** Panels that make no sense at a phone width are hidden there rather
   *  than squeezed. `false` for the ones that are genuinely useful
   *  narrow (Notifications, Activity). */
  hideOnCompact?: boolean;
  /** A panel the user cannot close -- there are none today, and the
   *  field exists so a future one does not need a special case in the
   *  frame component. */
  permanent?: boolean;
}

export const panelRegistry = new ContributionRegistry<PanelContribution>();

// --- Core panels ------------------------------------------------------
//
// `moduleId: "core"` for the three centres that belong to the shell
// itself rather than to any module -- the same reserved id
// `status-bar-contributions.tsx` and `dashboard-widgets.tsx` already use
// for exactly this reason (they are not `ApplicationRegistry` entries).

const NotificationCenter = lazy(async () => ({
  default: (await import("@/features/notifications/notification-center")).NotificationCenter,
}));
const ActivityCenter = lazy(async () => ({
  default: (await import("@/features/activity/activity-center")).ActivityCenter,
}));
const GlobalSearchPanel = lazy(async () => ({
  default: (await import("@/features/search/global-search-panel")).GlobalSearchPanel,
}));
const VoicePage = lazy(async () => ({
  default: (await import("@/features/voice/voice-page")).VoicePage,
}));
const SettingsPage = lazy(async () => ({
  default: (await import("@/features/settings/settings-page")).SettingsPage,
}));

let registered = false;

/**
 * Register the panels that have real content today.
 *
 * Called from the startup sequence. Idempotent for the same reason
 * `ensureRealtimeBridge()` is: React StrictMode double-invokes effects
 * in development, and `ContributionRegistry.register` throws on a
 * duplicate id -- which would turn a development-only double-invoke into
 * a hard startup failure.
 *
 * **Which modules are deliberately absent.** The nine remaining
 * `MODULE_DEFINITIONS` entries (Conversation, Memory, Automation, Files,
 * Browser, Coding, Finance, Smart Home, Calendar, Gmail, Spotify) have
 * no real route element -- `routes/router.tsx` renders
 * `PlaceholderRoute` for every one of them. Registering a panel that
 * renders "this module hasn't been built yet" inside a title bar with
 * resize handles would dress an unbuilt module up as a working one. They
 * register a panel on the day they get real content, and the framework
 * needs no change when they do.
 */
export function registerCorePanels(): void {
  if (registered) return;
  registered = true;

  panelRegistry.register({
    id: "core.notifications",
    moduleId: "core",
    title: "Notifications",
    icon: "bell",
    defaultZone: "right",
    render: NotificationCenter,
  });
  panelRegistry.register({
    id: "core.activity",
    moduleId: "core",
    title: "Activity",
    icon: "activity",
    defaultZone: "right",
    render: ActivityCenter,
  });
  panelRegistry.register({
    id: "core.search",
    moduleId: "core",
    title: "Search",
    icon: "search",
    defaultZone: "left",
    render: GlobalSearchPanel,
  });
  panelRegistry.register({
    id: "home.dashboard",
    moduleId: "home",
    title: "Dashboard",
    icon: "home",
    defaultZone: "main",
    render: DashboardGrid,
    hideOnCompact: true,
  });
  panelRegistry.register({
    id: "voice.main",
    moduleId: "voice",
    title: "Voice",
    icon: "mic",
    defaultZone: "main",
    render: VoicePage,
  });
  panelRegistry.register({
    id: "settings.main",
    moduleId: "settings",
    title: "Settings",
    icon: "settings",
    defaultZone: "main",
    render: SettingsPage,
    hideOnCompact: true,
  });
}

/** Test seam -- clears registration so a suite can re-register. */
export function resetPanelRegistryForTesting(): void {
  for (const panel of panelRegistry.getAll()) panelRegistry.unregister(panel.id);
  registered = false;
}
