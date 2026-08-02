import { Bell, CheckCircle2, FolderOpen, Mic, Sparkles, Workflow, XCircle, type LucideIcon } from "lucide-react";
import { Link } from "react-router-dom";
import { dashboardWidgetRegistry, type DashboardWidgetContribution } from "@/core/dashboard-widget-registry";
import { useConnectionStatus } from "@/hooks/use-connection-status";
import { CONNECTION_STATUS_DOT_CLASS, CONNECTION_STATUS_LABEL } from "@/lib/connection-status-display";
import { cn } from "@/lib/utils";
import { useBackgroundTasksStore } from "@/stores/background-tasks.store";
import { useNotificationsStore, type NotificationRecord } from "@/stores/notifications.store";

/**
 * Core JARVIS's own built-in Dashboard widgets (Phase 3, Task Group F)
 * -- registered through the exact same `dashboardWidgetRegistry`
 * (`core/dashboard-widget-registry.ts`) a future plugin's own widget
 * would use.
 *
 * The roadmap's original 7-widget list (Tasks, Calendar, Notes,
 * Notifications, Recent Activity, Quick Actions, System Status) names
 * three -- Tasks, Calendar, Notes -- that have no real backing store or
 * feature anywhere in this codebase yet (confirmed by search: no
 * `tasks.store.ts`, no calendar data, no notes data, and no backend
 * endpoint for any of them). Per this project's standing "no fake
 * data"/"no placeholder business logic" rule, they are deliberately
 * NOT registered here -- a widget with a title and an empty shell but
 * no real feature behind it would be exactly the fake implementation
 * this milestone forbids. Each needs its own real feature build (see
 * `docs/IMPLEMENTATION_ROADMAP.md`'s Phase 3 note) before it can honestly
 * contribute a widget. The other four all render real, already-existing
 * application state.
 */

const CORE_MODULE_ID = "core";

const SEVERITY_DOT_CLASS: Record<NotificationRecord["severity"], string> = {
  info: "bg-accent",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-destructive",
};

function NotificationsWidget() {
  const items = useNotificationsStore((s) => s.items);
  const markRead = useNotificationsStore((s) => s.markRead);

  if (items.length === 0) {
    return <p className="text-secondary text-muted-foreground">No notifications</p>;
  }

  const unreadCount = items.filter((item) => !item.read).length;
  const recent = items.slice(0, 5);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-secondary text-muted-foreground">
          {unreadCount === 0 ? "All read" : `${unreadCount} unread`}
        </span>
        {unreadCount > 0 && (
          <button
            type="button"
            onClick={() => {
              for (const item of items) {
                if (!item.read) markRead(item.id);
              }
            }}
            className="text-secondary text-accent hover:underline"
          >
            Mark all read
          </button>
        )}
      </div>
      <ul className="flex flex-col gap-1">
        {recent.map((item) => (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => markRead(item.id)}
              aria-label={`Mark "${item.title}" as read`}
              className="flex w-full items-start gap-2 rounded-md p-1 text-left text-secondary hover:bg-muted"
            >
              <span
                className={cn("mt-1.5 size-1.5 shrink-0 rounded-full", SEVERITY_DOT_CLASS[item.severity])}
                aria-hidden="true"
              />
              <span className={cn("min-w-0 flex-1 truncate", !item.read && "font-medium text-foreground")}>
                {item.title}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StatusRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

function SystemStatusWidget() {
  const status = useConnectionStatus();
  const runningTask = useBackgroundTasksStore((s) => s.tasks.find((t) => t.status === "running"));

  return (
    <dl className="flex flex-col gap-2 text-secondary">
      <StatusRow label="Connection">
        <span className="flex items-center gap-1.5">
          <span className={cn("size-2 rounded-full", CONNECTION_STATUS_DOT_CLASS[status])} aria-hidden="true" />
          {CONNECTION_STATUS_LABEL[status]}
        </span>
      </StatusRow>
      <StatusRow label="Background task">
        {runningTask ? (
          <span>
            {runningTask.label}
            {runningTask.percent !== null ? ` (${runningTask.percent}%)` : ""}
          </span>
        ) : (
          <span className="text-muted-foreground">No active tasks</span>
        )}
      </StatusRow>
      <StatusRow label="AI Provider">
        <span className="text-muted-foreground">Not configured</span>
      </StatusRow>
      <StatusRow label="Voice">
        <span className="text-muted-foreground">Not configured</span>
      </StatusRow>
      <StatusRow label="Automation">
        <span className="text-muted-foreground">Not configured</span>
      </StatusRow>
    </dl>
  );
}

interface ActivityEntry {
  id: string;
  label: string;
  timestamp: string;
  kind: "notification" | "task-completed" | "task-failed";
}

function ActivityIcon({ kind }: { kind: ActivityEntry["kind"] }) {
  if (kind === "task-completed") {
    return <CheckCircle2 className="size-icon-sm shrink-0 text-success" aria-hidden="true" />;
  }
  if (kind === "task-failed") {
    return <XCircle className="size-icon-sm shrink-0 text-destructive" aria-hidden="true" />;
  }
  return <Bell className="size-icon-sm shrink-0 text-muted-foreground" aria-hidden="true" />;
}

/** Merges two real event sources -- notifications and background task
 *  completions/failures -- into one timeline, sorted by each event's
 *  own real timestamp. Deliberately excludes running tasks: those are
 *  "current", not "recent past", and already have their own Status Bar
 *  and System Status widget representation. */
function RecentActivityWidget() {
  const notifications = useNotificationsStore((s) => s.items);
  const tasks = useBackgroundTasksStore((s) => s.tasks);

  const entries: ActivityEntry[] = [
    ...notifications.map((n) => ({
      id: `notification:${n.id}`,
      label: n.title,
      timestamp: n.createdAt,
      kind: "notification" as const,
    })),
    ...tasks
      .filter((t) => t.status !== "running")
      .map((t) => ({
        id: `task:${t.id}`,
        label: t.label,
        timestamp: t.timestamp,
        kind: (t.status === "completed" ? "task-completed" : "task-failed") as ActivityEntry["kind"],
      })),
  ]
    .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
    .slice(0, 5);

  if (entries.length === 0) {
    return <p className="text-secondary text-muted-foreground">No recent activity</p>;
  }

  return (
    <ul className="flex flex-col gap-1.5">
      {entries.map((entry) => (
        <li key={entry.id} className="flex items-center gap-2 text-secondary">
          <ActivityIcon kind={entry.kind} />
          <span className="min-w-0 flex-1 truncate">{entry.label}</span>
        </li>
      ))}
    </ul>
  );
}

/** Real navigation shortcuts to core modules -- the same `Link`-based
 *  navigation Sidebar/Dock already use, not a fabricated action list.
 *  Deliberately excludes Dashboard itself (already active) and Settings
 *  (already reachable from Sidebar's own core group). */
const QUICK_ACTIONS: { label: string; to: string; icon: LucideIcon }[] = [
  { label: "Conversation", to: "/chat", icon: Sparkles },
  { label: "Voice", to: "/voice", icon: Mic },
  { label: "Files", to: "/files", icon: FolderOpen },
  { label: "Automation", to: "/automations", icon: Workflow },
];

function QuickActionsWidget() {
  return (
    <div className="grid grid-cols-2 gap-2">
      {QUICK_ACTIONS.map((action) => (
        <Link
          key={action.to}
          to={action.to}
          // "Open <label>" rather than just "<label>" -- Sidebar/Dock
          // already have a nav link with this exact visible text
          // ("Automation", "Files", ...); an identical accessible name
          // here would make `getByRole("link", { name })` ambiguous for
          // anyone (a screen reader user or a test) trying to tell "the
          // real nav item" apart from "this shortcut to the same place".
          aria-label={`Open ${action.label}`}
          className="flex flex-col items-center gap-1 rounded-lg border border-border p-2 text-center text-secondary text-muted-foreground transition-colors duration-fast hover:bg-muted hover:text-foreground focus-visible:outline-2 focus-visible:outline-ring"
        >
          <action.icon className="size-icon-md" aria-hidden="true" />
          <span aria-hidden="true">{action.label}</span>
        </Link>
      ))}
    </div>
  );
}

function coreWidget(fields: Omit<DashboardWidgetContribution, "moduleId" | "isCore">): DashboardWidgetContribution {
  return { ...fields, moduleId: CORE_MODULE_ID, isCore: true };
}

const CORE_DASHBOARD_WIDGETS: DashboardWidgetContribution[] = [
  coreWidget({
    id: "core.widget.notifications",
    title: "Notifications",
    render: NotificationsWidget,
    defaultSize: { width: 2, height: 1 },
  }),
  coreWidget({
    id: "core.widget.system-status",
    title: "System Status",
    render: SystemStatusWidget,
    defaultSize: { width: 1, height: 2 },
  }),
  coreWidget({
    id: "core.widget.recent-activity",
    title: "Recent Activity",
    render: RecentActivityWidget,
    defaultSize: { width: 1, height: 2 },
  }),
  coreWidget({
    id: "core.widget.quick-actions",
    title: "Quick Actions",
    render: QuickActionsWidget,
    defaultSize: { width: 1, height: 1 },
  }),
];

/** Registers Core JARVIS's 4 built-in dashboard widgets. Called once
 *  from `main.tsx`, alongside `registerCoreStatusBarItems()` -- both are
 *  cold-start registration steps for the app's whole lifetime. */
export function registerCoreDashboardWidgets(): void {
  for (const widget of CORE_DASHBOARD_WIDGETS) {
    dashboardWidgetRegistry.register(widget);
  }
}
