import type { ComponentType } from "react";
import { ContributionRegistry, type Contribution } from "@/core/contribution-registry";

/**
 * The Dashboard's contribution surface (UI Architecture Update) -- a
 * module registers a widget here exactly the same way it registers
 * navigation or a status bar item (`core/interfaces/navigation-interface.ts`,
 * `core/interfaces/status-bar-interface.ts`): all three are instances of
 * the one generic `ContributionRegistry` (`core/contribution-registry.ts`),
 * not separate, unrelated implementations. No widget grid UI renders
 * these yet -- that's a separate, later task; this is the registration
 * surface only.
 */
export interface DashboardWidgetContribution extends Contribution {
  title: string;
  /** Renders the widget's content -- a real React component
   *  (`import type` only, no runtime React dependency in this `core/`
   *  file), the same contract `StatusBarContribution.render` uses, so a
   *  future widget grid UI can render each contribution as its own
   *  `<contribution.render />` element and let it manage its own
   *  reactivity, rather than every contribution consumer inventing its
   *  own answer to "how does a registered UI fragment stay live." */
  render: ComponentType;
  defaultSize: { width: number; height: number };
}

/** One shared instance -- widget registration is process-wide, matching
 *  `applicationRegistry`'s own singleton pattern. */
export const dashboardWidgetRegistry = new ContributionRegistry<DashboardWidgetContribution>();
