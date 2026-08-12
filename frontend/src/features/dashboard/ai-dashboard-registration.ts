import { dashboardWidgetRegistry } from "@/core/dashboard-widget-registry";
import type { DashboardWidgetContribution } from "@/core/dashboard-widget-registry";
import {
  KnowledgeGraphWidget,
  NotificationSummaryWidget,
  PerformanceWidget,
  PinnedNotesWidget,
  ProjectsWidget,
  RecentFilesWidget,
  RecentTasksWidget,
  SubsystemStatusWidget,
  SuggestionsWidget,
  SystemOverviewWidget,
  UpcomingCalendarWidget,
} from "@/features/dashboard/ai-dashboard-widgets";

/**
 * The AI Dashboard's widgets, registered through the **existing**
 * `dashboardWidgetRegistry` -- M8 Phase 5.
 *
 * No new registry. `core/dashboard-widget-registry.ts` is already a
 * `ContributionRegistry` instance and already the surface Phase 3's four
 * core widgets register through; these eleven join the same one, so the
 * Dashboard Widget Grid renders, sizes, moves, pins and persists them
 * with no change to the grid at all.
 *
 * A separate module from `dashboard-widgets.tsx` only because that file
 * owns Phase 3's four widgets and their history; both call the same
 * `dashboardWidgetRegistry.register`, and `registerAiDashboardWidgets()`
 * runs in the same startup task as `registerCoreDashboardWidgets()`.
 *
 * **Three widgets from the phase brief are deliberately not here:**
 *
 * - *Recent Conversations* — no conversation-history route exists in the
 *   frozen backend (`/agent/invoke` and `/agent/stream` are one-shot;
 *   sessions carry a `conversation_id` but nothing lists or reads a
 *   conversation). A widget with a title and no data source is the fake
 *   implementation this project forbids.
 * - *Provider Status* — real data (`mcp.providers` in the health
 *   snapshot), but `ARCHITECTURE.md` §22.12 puts provider names
 *   off-limits to personal users. It ships on the **Developer**
 *   dashboard instead.
 * - *AI Status / Memory Status / Knowledge Graph Status / Automation
 *   Status / Voice Status / Vision Status* as six separate widgets —
 *   they share one data source and one presentation, so they ship as a
 *   single `SubsystemStatusWidget`. Six cards showing one light each
 *   would be six copies of four lines, and worse for the question a
 *   user actually asks ("is anything wrong?").
 *
 * *Vision* has no runtime status to report at all: M6 shipped the
 * architecture layer, no vision service registers with the health
 * monitor, and no `vision` search source exists. It is absent rather
 * than permanently "Not known".
 */

const CORE_MODULE_ID = "core";

function widget(
  input: Omit<DashboardWidgetContribution, "moduleId" | "isCore">,
): DashboardWidgetContribution {
  return { ...input, moduleId: CORE_MODULE_ID, isCore: true };
}

export const AI_DASHBOARD_WIDGETS: DashboardWidgetContribution[] = [
  widget({
    id: "core.widget.system-overview",
    title: "System Overview",
    render: SystemOverviewWidget,
    defaultSize: { width: 2, height: 1 },
  }),
  widget({
    id: "core.widget.subsystems",
    title: "Subsystem Status",
    render: SubsystemStatusWidget,
    defaultSize: { width: 1, height: 2 },
  }),
  widget({
    id: "core.widget.performance",
    title: "Performance",
    render: PerformanceWidget,
    defaultSize: { width: 2, height: 1 },
  }),
  widget({
    id: "core.widget.knowledge-graph",
    title: "Knowledge Graph",
    render: KnowledgeGraphWidget,
    defaultSize: { width: 1, height: 1 },
  }),
  widget({
    id: "core.widget.suggestions",
    title: "Suggestions",
    render: SuggestionsWidget,
    defaultSize: { width: 1, height: 2 },
  }),
  widget({
    id: "core.widget.tasks",
    title: "Recent Tasks",
    render: RecentTasksWidget,
    defaultSize: { width: 1, height: 2 },
  }),
  widget({
    id: "core.widget.projects",
    title: "Projects",
    render: ProjectsWidget,
    defaultSize: { width: 1, height: 1 },
  }),
  widget({
    id: "core.widget.pinned-notes",
    title: "Pinned Notes",
    render: PinnedNotesWidget,
    defaultSize: { width: 1, height: 1 },
  }),
  widget({
    id: "core.widget.files",
    title: "Recent Files",
    render: RecentFilesWidget,
    defaultSize: { width: 1, height: 2 },
  }),
  widget({
    id: "core.widget.calendar",
    title: "Upcoming",
    render: UpcomingCalendarWidget,
    defaultSize: { width: 1, height: 2 },
  }),
  widget({
    id: "core.widget.notification-summary",
    title: "Notification Summary",
    render: NotificationSummaryWidget,
    defaultSize: { width: 1, height: 1 },
  }),
];

let registered = false;

/**
 * Idempotent for the same reason `registerCorePanels()` is: React
 * StrictMode double-invokes effects in development, and
 * `ContributionRegistry.register` throws on a duplicate id — which would
 * turn a development-only double-invoke into a hard startup failure.
 */
export function registerAiDashboardWidgets(): void {
  if (registered) return;
  registered = true;
  for (const contribution of AI_DASHBOARD_WIDGETS) {
    dashboardWidgetRegistry.register(contribution);
  }
}

/** Test seam. */
export function resetAiDashboardWidgetsForTesting(): void {
  for (const contribution of AI_DASHBOARD_WIDGETS) {
    dashboardWidgetRegistry.unregister(contribution.id);
  }
  registered = false;
}
