import { useMemo } from "react";
import {
  Bell,
  Brain,
  CalendarDays,
  CheckSquare,
  FileText,
  FolderKanban,
  Mic,
  Network,
  Sparkles,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { ResourceView } from "@/components/common/resource-view";
import { useBackendResource } from "@/hooks/use-backend-resource";
import {
  calendarApi,
  filesApi,
  intelligenceApi,
  knowledgeApi,
  notesApi,
  projectsApi,
  tasksApi,
} from "@/services/api/endpoints";
import {
  formatBytes,
  formatUptime,
  selectAiWorkspaceStatus,
  selectFilesStatus,
  selectOverallStatus,
  selectServiceStatus,
  selectSourceStatus,
  useHealthStore,
  type SubsystemStatus,
} from "@/stores/health.store";
import { useNotificationsStore } from "@/stores/notifications.store";
import { useWorkspaceLayoutStore, selectActiveWorkspace } from "@/stores/workspace-layout.store";

/**
 * The AI Dashboard's widgets -- M8 Phase 5.
 *
 * **Every number here comes from the frozen backend.** The status
 * widgets read the `health.updated` snapshot
 * (`stores/health.store.ts`); the content widgets call real REST
 * routes. Nothing is seeded, and a widget with no data says so rather
 * than showing a plausible zero.
 *
 * **Nothing here reveals a provider.** `ARCHITECTURE.md` §22.12 puts
 * provider names, routing and backend service names off-limits to
 * personal users, so the Provider Status widget lives on the *Developer*
 * dashboard instead of this one. That is the single substantive
 * divergence from the phase brief's widget list, and it is the
 * architecture decision winning over the list, deliberately.
 *
 * Two widgets the brief lists have **no backing API** and are therefore
 * absent rather than faked — see `MILESTONE_REPORT.md`:
 * *Recent Conversations* (no conversation-history route exists) and
 * *Pinned Projects* (`Project` has no `pinned` column; `Note` and
 * `Workspace` do, so Pinned Notes ships in its place).
 */

// --- Shared presentation ---------------------------------------------

const STATUS_STYLE: Record<SubsystemStatus, { dot: string; label: string }> = {
  healthy: { dot: "bg-emerald-500", label: "Ready" },
  degraded: { dot: "bg-amber-500", label: "Degraded" },
  disabled: { dot: "bg-muted-foreground/50", label: "Off" },
  unknown: { dot: "bg-muted-foreground/30", label: "Not known" },
};

function StatusRow({ icon: Icon, name, status }: { icon: LucideIcon; name: string; status: SubsystemStatus }) {
  const style = STATUS_STYLE[status];
  return (
    <li className="flex items-center gap-2 py-1">
      <Icon className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate text-secondary">{name}</span>
      <span className="flex items-center gap-1.5 text-muted-foreground text-xs">
        <span className={`size-1.5 rounded-full ${style.dot}`} aria-hidden="true" />
        {style.label}
      </span>
    </li>
  );
}

function Stat({ value, caption }: { value: string; caption: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-semibold text-widget-title tabular-nums">{value}</span>
      <span className="text-muted-foreground text-xs">{caption}</span>
    </div>
  );
}

/** Every status widget needs the same "no snapshot yet" treatment: the
 *  backend has not spoken, and inventing a green light would be the
 *  worst possible lie for a health display. */
function useHasSnapshot(): boolean {
  return useHealthStore((s) => s.snapshot !== null);
}

function AwaitingBackend({ what }: { what: string }) {
  return (
    <p className="p-4 text-center text-muted-foreground text-xs">
      Waiting for the backend to report {what}.
    </p>
  );
}

// --- System overview --------------------------------------------------

export function SystemOverviewWidget() {
  const snapshot = useHealthStore((s) => s.snapshot);
  const status = useHealthStore(selectOverallStatus);

  if (!snapshot) return <AwaitingBackend what="system health" />;

  return (
    <div className="grid grid-cols-2 gap-4 p-3">
      <Stat value={STATUS_STYLE[status].label} caption="Overall" />
      <Stat value={formatUptime(snapshot.uptime_seconds)} caption="Uptime" />
      <Stat
        value={snapshot.cpu_percent === undefined ? "—" : `${snapshot.cpu_percent.toFixed(0)}%`}
        caption="CPU"
      />
      <Stat value={formatBytes(snapshot.memory_rss_bytes)} caption="Memory" />
    </div>
  );
}

// --- Subsystem status -------------------------------------------------

/**
 * One widget for the six "… Status" rows the brief lists separately.
 *
 * They share a data source (one health snapshot) and a presentation (a
 * name and a light), so six widgets would be six copies of the same four
 * lines. A user scanning "is anything wrong?" is also better served by
 * one list than by hunting six cards.
 */
export function SubsystemStatusWidget() {
  const hasSnapshot = useHasSnapshot();
  const ai = useHealthStore(selectAiWorkspaceStatus);
  const memory = useHealthStore(selectSourceStatus("memory"));
  const knowledge = useHealthStore(selectSourceStatus("knowledge"));
  const automation = useHealthStore(selectServiceStatus("automation"));
  const voice = useHealthStore(selectServiceStatus("voice"));
  const files = useHealthStore(selectFilesStatus);

  if (!hasSnapshot) return <AwaitingBackend what="subsystem status" />;

  return (
    <ul className="px-3 py-1 text-secondary">
      <StatusRow icon={Sparkles} name="AI workspace" status={ai} />
      <StatusRow icon={Brain} name="Memory" status={memory} />
      <StatusRow icon={Network} name="Knowledge graph" status={knowledge} />
      <StatusRow icon={Workflow} name="Automation" status={automation} />
      <StatusRow icon={Mic} name="Voice" status={voice} />
      <StatusRow icon={FileText} name="Files" status={files} />
    </ul>
  );
}

// --- Performance ------------------------------------------------------

export function PerformanceWidget() {
  const snapshot = useHealthStore((s) => s.snapshot);
  if (!snapshot) return <AwaitingBackend what="performance metrics" />;

  const services = snapshot.active_services?.length ?? 0;
  const failed = snapshot.failed_services?.length ?? 0;

  return (
    <div className="grid grid-cols-2 gap-4 p-3">
      <Stat
        value={
          snapshot.startup_duration_ms === undefined
            ? "—"
            : `${(snapshot.startup_duration_ms / 1000).toFixed(2)}s`
        }
        caption="Startup"
      />
      <Stat value={formatBytes(snapshot.disk_free_bytes)} caption="Disk free" />
      {/* Counts, not names: a service *name* is §22.12-restricted, a
          count is not, and the count is what answers "is anything
          wrong?" on a personal dashboard. */}
      <Stat value={String(services)} caption="Services running" />
      <Stat value={String(failed)} caption="Services failed" />
    </div>
  );
}

// --- Content widgets --------------------------------------------------

/** The backend workspace this layout is bound to, or `null`. Several
 *  widgets scope their query by it; without one they say so rather than
 *  fetching every workspace's data and calling it "recent". */
function useBoundWorkspaceId(): string | null {
  return useWorkspaceLayoutStore((s) => selectActiveWorkspace(s).backendWorkspaceId);
}

function NoWorkspaceBound({ what }: { what: string }) {
  return (
    <p className="p-4 text-center text-muted-foreground text-xs">
      Bind this workspace to a JARVIS workspace to see its {what}.
    </p>
  );
}

export function RecentTasksWidget() {
  const workspaceId = useBoundWorkspaceId();
  const { state, refresh } = useBackendResource(
    () => tasksApi.list({ workspace_id: workspaceId ?? undefined, limit: 5 }),
    [workspaceId],
    { enabled: workspaceId !== null, isEmpty: (page) => (page as { items: unknown[] }).items.length === 0 },
  );

  if (!workspaceId) return <NoWorkspaceBound what="tasks" />;

  return (
    <ResourceView state={state} label="Tasks" onRetry={refresh} emptyMessage="No open tasks.">
      {(page) => (
        <ul className="px-3 py-1">
          {page.items.map((task) => (
            <li key={task.id} className="flex items-center gap-2 py-1">
              <CheckSquare className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-secondary">{task.title}</span>
              <span className="shrink-0 text-muted-foreground text-xs">{task.status}</span>
            </li>
          ))}
        </ul>
      )}
    </ResourceView>
  );
}

export function ProjectsWidget() {
  const workspaceId = useBoundWorkspaceId();
  const { state, refresh } = useBackendResource(
    () => projectsApi.list({ workspace_id: workspaceId ?? undefined, status: "active", limit: 5 }),
    [workspaceId],
    { enabled: workspaceId !== null, isEmpty: (page) => (page as { items: unknown[] }).items.length === 0 },
  );

  if (!workspaceId) return <NoWorkspaceBound what="projects" />;

  return (
    <ResourceView state={state} label="Projects" onRetry={refresh} emptyMessage="No active projects.">
      {(page) => (
        <ul className="px-3 py-1">
          {page.items.map((project) => (
            <li key={project.id} className="flex items-center gap-2 py-1">
              <FolderKanban className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-secondary">{project.name}</span>
            </li>
          ))}
        </ul>
      )}
    </ResourceView>
  );
}

/**
 * Pinned *notes*, not pinned projects.
 *
 * The brief asks for Pinned Projects; the frozen schema has no `pinned`
 * column on `Project` (only `status`), while `Note` and `Workspace` both
 * do. Rather than invent a pin the backend cannot store, this surfaces
 * the pin that genuinely exists, and `ProjectsWidget` above covers
 * projects by their real `status` field.
 */
export function PinnedNotesWidget() {
  const workspaceId = useBoundWorkspaceId();
  const { state, refresh } = useBackendResource(
    () => notesApi.list({ workspace_id: workspaceId ?? undefined, limit: 20 }),
    [workspaceId],
    { enabled: workspaceId !== null },
  );

  if (!workspaceId) return <NoWorkspaceBound what="notes" />;

  return (
    <ResourceView state={state} label="Pinned notes" onRetry={refresh} emptyMessage="Nothing pinned.">
      {(page) => {
        const pinned = page.items.filter((note) => note.pinned).slice(0, 5);
        if (pinned.length === 0) {
          return <p className="p-4 text-center text-muted-foreground text-xs">Nothing pinned.</p>;
        }
        return (
          <ul className="px-3 py-1">
            {pinned.map((note) => (
              <li key={note.id} className="flex items-center gap-2 py-1">
                <FileText className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-secondary">{note.title}</span>
              </li>
            ))}
          </ul>
        );
      }}
    </ResourceView>
  );
}

export function RecentFilesWidget() {
  const workspaceId = useBoundWorkspaceId();
  const { state, refresh } = useBackendResource(
    () => filesApi.list({ workspace_id: workspaceId ?? undefined, limit: 5 }),
    [workspaceId],
    { enabled: workspaceId !== null, isEmpty: (page) => (page as { items: unknown[] }).items.length === 0 },
  );

  if (!workspaceId) return <NoWorkspaceBound what="files" />;

  return (
    <ResourceView state={state} label="Files" onRetry={refresh} emptyMessage="No files yet.">
      {(page) => (
        <ul className="px-3 py-1">
          {page.items.map((file) => (
            <li key={file.id} className="flex items-center gap-2 py-1">
              <FileText className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-secondary">{file.filename}</span>
            </li>
          ))}
        </ul>
      )}
    </ResourceView>
  );
}

export function UpcomingCalendarWidget() {
  const workspaceId = useBoundWorkspaceId();
  const { state, refresh } = useBackendResource(
    () => calendarApi.agenda(workspaceId ?? "", 7),
    [workspaceId],
    { enabled: workspaceId !== null },
  );

  if (!workspaceId) return <NoWorkspaceBound what="calendar" />;

  return (
    <ResourceView state={state} label="Calendar" onRetry={refresh} emptyMessage="Nothing scheduled.">
      {(agenda) => {
        // The backend owns the agenda shape; read defensively rather
        // than asserting a structure this client did not verify.
        const entries = Array.isArray((agenda as { events?: unknown }).events)
          ? ((agenda as { events: Array<{ id?: string; title?: string; starts_at?: string }> }).events)
          : [];
        if (entries.length === 0) {
          return <p className="p-4 text-center text-muted-foreground text-xs">Nothing scheduled.</p>;
        }
        return (
          <ul className="px-3 py-1">
            {entries.slice(0, 5).map((event, index) => (
              <li key={event.id ?? index} className="flex items-center gap-2 py-1">
                <CalendarDays className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
                <span className="min-w-0 flex-1 truncate text-secondary">{event.title ?? "Untitled"}</span>
              </li>
            ))}
          </ul>
        );
      }}
    </ResourceView>
  );
}

/** M10B's real suggestion engine — the closest thing the frozen backend
 *  has to "what should I do next", and genuinely computed rather than a
 *  hardcoded action list. */
export function SuggestionsWidget() {
  const { state, refresh } = useBackendResource(() => intelligenceApi.suggestions(), []);

  return (
    <ResourceView state={state} label="Suggestions" onRetry={refresh} emptyMessage="No suggestions right now.">
      {(suggestions) => (
        <ul className="px-3 py-1">
          {suggestions.slice(0, 5).map((suggestion) => (
            <li key={suggestion.id} className="flex items-center gap-2 py-1">
              <Sparkles className="size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
              <span className="min-w-0 flex-1 truncate text-secondary">{suggestion.title}</span>
            </li>
          ))}
        </ul>
      )}
    </ResourceView>
  );
}

export function KnowledgeGraphWidget() {
  const { state, refresh } = useBackendResource(() => knowledgeApi.export(), []);
  const status = useHealthStore(selectSourceStatus("knowledge"));

  return (
    <ResourceView state={state} label="Knowledge graph" skeleton="stats" onRetry={refresh}>
      {(graph) => {
        const entities = Array.isArray((graph as { entities?: unknown }).entities)
          ? (graph as { entities: unknown[] }).entities.length
          : null;
        const relations = Array.isArray((graph as { relations?: unknown }).relations)
          ? (graph as { relations: unknown[] }).relations.length
          : null;
        return (
          <div className="grid grid-cols-2 gap-4 p-3">
            <Stat value={entities === null ? "—" : String(entities)} caption="Entities" />
            <Stat value={relations === null ? "—" : String(relations)} caption="Relations" />
            <Stat value={STATUS_STYLE[status].label} caption="Search source" />
          </div>
        );
      }}
    </ResourceView>
  );
}

export function NotificationSummaryWidget() {
  const items = useNotificationsStore((s) => s.items);
  const counts = useMemo(() => {
    const unread = items.filter((item) => !item.read).length;
    const errors = items.filter((item) => item.severity === "error").length;
    return { total: items.length, unread, errors };
  }, [items]);

  if (counts.total === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-1.5 p-6 text-center">
        <Bell className="size-icon-md text-muted-foreground" aria-hidden="true" />
        <p className="text-muted-foreground text-xs">No notifications.</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-3 gap-4 p-3">
      <Stat value={String(counts.total)} caption="Total" />
      <Stat value={String(counts.unread)} caption="Unread" />
      <Stat value={String(counts.errors)} caption="Errors" />
    </div>
  );
}
