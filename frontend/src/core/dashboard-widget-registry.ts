import { ContributionRegistry, type Contribution } from "@/core/contribution-registry";

/**
 * The Dashboard's contribution surface (UI Architecture Update) -- a
 * module registers a widget here exactly the same way it registers
 * navigation (`core/interfaces/navigation-interface.ts`): both are
 * instances of the one generic `ContributionRegistry`
 * (`core/contribution-registry.ts`), not separate, unrelated
 * implementations. No widget grid UI renders these yet -- that's a
 * separate, later task; this is the registration surface only.
 */
export interface DashboardWidgetContribution extends Contribution {
  title: string;
  /** Renders the widget's content. A function reference, not
   *  serialized data -- the same shape `NavigationContribution`'s own
   *  `commandPaletteEntries[].action` already uses, appropriate for
   *  same-process, same-bundle first-party modules (every module
   *  today). Typed `unknown` rather than a React type here on purpose:
   *  no widget grid UI exists yet to consume this contract, and this
   *  file has no React dependency to justify importing `ReactNode`
   *  just for a type. */
  render: () => unknown;
  defaultSize: { width: number; height: number };
}

/** One shared instance -- widget registration is process-wide, matching
 *  `applicationRegistry`'s own singleton pattern. */
export const dashboardWidgetRegistry = new ContributionRegistry<DashboardWidgetContribution>();
