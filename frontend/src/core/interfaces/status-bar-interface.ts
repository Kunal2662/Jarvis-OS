import type { ComponentType } from "react";
import { ContributionRegistry, type Contribution } from "@/core/contribution-registry";

export type StatusBarPosition = "left" | "center" | "right";

/**
 * The Status Bar's extension surface (Phase 3, Task Group E) -- a named
 * `ContributionRegistry` instance, the same mechanism Dashboard Widgets
 * and Navigation already use (`core/contribution-registry.ts`), not a
 * fourth bespoke registry. Core JARVIS's own 9 built-in items
 * (`components/layout/status-bar-contributions.tsx`) are registered
 * through this exact same path as any future plugin's status item would
 * be -- Core JARVIS knows nothing about what a plugin contributes here,
 * only that something registered with a given `category`/`priority`.
 *
 * Metadata fields deliberately NOT included, to avoid duplicating what
 * already exists elsewhere:
 * - No `pluginId` -- `Contribution.moduleId` (inherited) already
 *   identifies the owner; a second, differently-named field for the
 *   same fact would be exactly the duplication this task's rules forbid.
 * - No `permissions`/`dependencies` -- both already live on the owning
 *   module's `ModuleManifest` (`core/module-manifest.ts`), looked up via
 *   `moduleId` when needed; a contribution doesn't get its own copy.
 * - No `enabledByDefault` -- module-level enablement
 *   (`stores/module-enablement.store.ts`) is the only enablement
 *   granularity this codebase actually has a mechanism for today; a
 *   second, per-contribution toggle with no UI to drive it yet would be
 *   exactly the kind of inert, speculative field "no fake
 *   implementations" warns against. Add it if/when a real per-item
 *   toggle ships.
 */
export interface StatusBarContribution extends Contribution {
  /** This contribution's own label -- distinct from the owning
   *  module's `ModuleManifest.displayName` the same way
   *  `DashboardWidgetContribution.title` is (a module's status item
   *  doesn't have to be named the same as the module itself, e.g. a
   *  future GitHub module's contribution might be titled "Git Sync"). */
  displayName: string;
  category: StatusBarPosition;
  /** Lower renders first within its `category`. Core items use small,
   *  spaced-out values (10, 20, 30…) so a future plugin can slot
   *  between them without a renumbering. */
  priority: number;
  /** True only for Core JARVIS's own 9 built-in items -- mirrors
   *  `ModuleManifest.isCore`'s meaning one level down (a contribution,
   *  not a whole module, is core or not). */
  isCore: boolean;
  icon?: string;
  /** Renders this item's live content. A real React component
   *  (`import type` only -- no runtime React dependency in this
   *  `core/` file), not a plain callback returning a value: each
   *  contribution manages its own reactivity (subscribing to whatever
   *  store or state it needs) as its own component instance. Calling
   *  hooks inside a `.map()` over this registry's variable-length
   *  `getAll()` result would violate React's Rules of Hooks; rendering
   *  each as its own `<contribution.render />` element does not. */
  render: ComponentType;
}

/** One shared instance -- status bar registration is process-wide,
 *  matching every other named `ContributionRegistry` instance. */
export const statusBarRegistry = new ContributionRegistry<StatusBarContribution>();
