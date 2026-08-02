import type { ComponentType } from "react";
import { ContributionRegistry, type Contribution } from "@/core/contribution-registry";

/**
 * The Dashboard's contribution surface (UI Architecture Update) -- a
 * module registers a widget here exactly the same way it registers
 * navigation or a status bar item (`core/interfaces/navigation-interface.ts`,
 * `core/interfaces/status-bar-interface.ts`): all three are instances of
 * the one generic `ContributionRegistry` (`core/contribution-registry.ts`),
 * not separate, unrelated implementations. Rendered by the Dashboard
 * Widget Grid (`features/dashboard/dashboard-grid.tsx`, Phase 3 Task
 * Group F).
 */
export interface DashboardWidgetContribution extends Contribution {
  title: string;
  /** Renders the widget's content -- a real React component
   *  (`import type` only, no runtime React dependency in this `core/`
   *  file), the same contract `StatusBarContribution.render` uses, so
   *  the widget grid can render each contribution as its own
   *  `<contribution.render />` element and let it manage its own
   *  reactivity, rather than every contribution consumer inventing its
   *  own answer to "how does a registered UI fragment stay live." */
  render: ComponentType;
  /** Grid units (not pixels) -- the grid renders a fixed number of
   *  columns and a fixed row height, so a widget's footprint is always
   *  expressed relative to that grid, matching how `dock.store.ts`
   *  keeps its own preference layer (pin order) separate from the
   *  registry that describes *what exists*. The user's actual current
   *  size/position/pin/visibility for a given install lives in
   *  `stores/dashboard-layout.store.ts`, not here -- this is the
   *  contribution's declared starting point only. */
  defaultSize: { width: number; height: number };
  /** Same reasoning as `StatusBarContribution.isCore`
   *  (`core/interfaces/status-bar-interface.ts`): Core JARVIS's built-in
   *  widgets register under the reserved `moduleId: "core"`, which
   *  isn't a real entry in `ApplicationRegistry` -- so enablement
   *  filtering (`stores/module-enablement.store.ts`'s `isModuleEnabled`)
   *  needs `isCore` directly on the contribution rather than resolved
   *  via a manifest lookup that wouldn't exist for it. */
  isCore: boolean;
}

/** One shared instance -- widget registration is process-wide, matching
 *  `applicationRegistry`'s own singleton pattern. */
export const dashboardWidgetRegistry = new ContributionRegistry<DashboardWidgetContribution>();
