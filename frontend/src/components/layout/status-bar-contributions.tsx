import { applicationRegistry } from "@/core/application-registry";
import { statusBarRegistry, type StatusBarContribution } from "@/core/interfaces/status-bar-interface";
import { useConnectionStatus } from "@/hooks/use-connection-status";
import { CONNECTION_STATUS_DOT_CLASS, CONNECTION_STATUS_LABEL } from "@/lib/connection-status-display";
import { cn } from "@/lib/utils";
import { useBackgroundTasksStore } from "@/stores/background-tasks.store";
import { useNotificationsStore } from "@/stores/notifications.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

/**
 * Core JARVIS's own 9 built-in Status Bar items (Phase 3, Task Group E)
 * -- registered through the exact same `statusBarRegistry`
 * (`core/interfaces/status-bar-interface.ts`) a future plugin's own
 * status item would use. Nothing here is special-cased by
 * `components/layout/status-bar.tsx`; it just renders whatever's
 * registered, sorted by `category`/`priority`.
 *
 * Three items (AI Provider, Voice Status, Automation Status) have no
 * real backend data source yet -- no AI-provider-state API, no voice
 * WebSocket relay, no automation-run status exists on the frontend
 * today (confirmed: the WebSocket bridge itself doesn't exist -- see
 * `ARCHITECTURE.md`'s own admission). Per this project's standing "no
 * fake data" rule, they honestly render "Not configured" rather than a
 * fabricated active-looking value -- the same pattern this file's own
 * Connection Status item already uses for "Not connected", not a new
 * one invented for this task.
 */

const CORE_MODULE_ID = "core";

function CurrentWorkspaceItem() {
  const activeModuleId = useWorkspaceStore((s) => s.activeModuleId);
  const activeModule = activeModuleId ? applicationRegistry.get(activeModuleId) : undefined;
  // "Workspace" = the active module's parent group (e.g. "AI") when it
  // has one, or "Core"/"Plugin" otherwise -- derived entirely from
  // already-real manifest data (`parentGroup`, `isCore`), not a
  // fabricated concept distinct from what the registry actually knows.
  const label = !activeModule
    ? "—"
    : activeModule.manifest.parentGroup
      ? "AI"
      : activeModule.manifest.isCore
        ? "Core"
        : "Plugin";
  return <span>{label}</span>;
}

function ActiveModuleItem() {
  const activeModuleId = useWorkspaceStore((s) => s.activeModuleId);
  const activeModule = activeModuleId ? applicationRegistry.get(activeModuleId) : undefined;
  return <span>{activeModule?.manifest.displayName ?? "—"}</span>;
}

function CurrentRunningTaskItem() {
  const runningTask = useBackgroundTasksStore((s) => s.tasks.find((t) => t.status === "running"));
  return <span>{runningTask?.label ?? "No active tasks"}</span>;
}

function BackgroundTaskProgressItem() {
  const runningTask = useBackgroundTasksStore((s) => s.tasks.find((t) => t.status === "running"));
  if (!runningTask) return null;
  return <span>{runningTask.percent === null ? "…" : `${runningTask.percent}%`}</span>;
}

/** Not yet backed by any real data source -- see this file's own header
 *  comment. Reused by AI Provider / Voice Status / Automation Status
 *  rather than each hand-rolling the same honest placeholder. */
function NotConfiguredItem() {
  return <span className="text-muted-foreground">Not configured</span>;
}

/** The real WebSocket backend connectivity indicator -- carried over
 *  verbatim from the pre-Task-Group-E `StatusBar`, not a new "internet
 *  online/offline" check. This project has no separate concept of
 *  "browser has internet" distinct from "the JARVIS backend is
 *  reachable"; inventing one now would be a second, parallel status
 *  concept, not reuse of the existing one. */
function ConnectionStatusItem() {
  const status = useConnectionStatus();
  return (
    <span className="flex items-center gap-2">
      <span className={cn("size-2 rounded-full", CONNECTION_STATUS_DOT_CLASS[status])} aria-hidden="true" />
      {CONNECTION_STATUS_LABEL[status]}
    </span>
  );
}

function NotificationIndicatorItem() {
  const unreadCount = useNotificationsStore((s) => s.unreadCount());
  if (unreadCount === 0) return <span className="text-muted-foreground">No notifications</span>;
  return <span>{unreadCount} unread</span>;
}

function coreItem(fields: Omit<StatusBarContribution, "moduleId" | "isCore">): StatusBarContribution {
  return { ...fields, moduleId: CORE_MODULE_ID, isCore: true };
}

const CORE_STATUS_BAR_ITEMS: StatusBarContribution[] = [
  coreItem({ id: "core.workspace", displayName: "Current Workspace", category: "left", priority: 10, render: CurrentWorkspaceItem }),
  coreItem({ id: "core.active-module", displayName: "Active Module", category: "left", priority: 20, render: ActiveModuleItem }),
  coreItem({
    id: "core.running-task",
    displayName: "Current Running Task",
    category: "center",
    priority: 10,
    render: CurrentRunningTaskItem,
  }),
  coreItem({
    id: "core.task-progress",
    displayName: "Background Task Progress",
    category: "center",
    priority: 20,
    render: BackgroundTaskProgressItem,
  }),
  coreItem({ id: "core.ai-provider", displayName: "AI Provider", category: "right", priority: 10, render: NotConfiguredItem }),
  coreItem({ id: "core.voice-status", displayName: "Voice Status", category: "right", priority: 20, render: NotConfiguredItem }),
  coreItem({
    id: "core.automation-status",
    displayName: "Automation Status",
    category: "right",
    priority: 30,
    render: NotConfiguredItem,
  }),
  coreItem({
    id: "core.connection-status",
    displayName: "Internet / Offline",
    category: "right",
    priority: 40,
    render: ConnectionStatusItem,
  }),
  coreItem({
    id: "core.notifications",
    displayName: "Notification Indicator",
    category: "right",
    priority: 50,
    render: NotificationIndicatorItem,
  }),
];

/** Registers Core JARVIS's 9 built-in status items. Called once from
 *  `main.tsx`, alongside `registerPlaceholderModules()` -- both are
 *  cold-start registration steps, not tied to any module's mount/
 *  unmount lifecycle (these exist for the app's whole lifetime). */
export function registerCoreStatusBarItems(): void {
  for (const item of CORE_STATUS_BAR_ITEMS) {
    statusBarRegistry.register(item);
  }
}
