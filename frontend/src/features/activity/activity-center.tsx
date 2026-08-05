import { useMemo } from "react";
import { Activity, Bot, CircleCheck, CircleX, Loader2, Workflow } from "lucide-react";
import { VirtualList } from "@/components/common/virtual-list";
import { useAgentActivityStore } from "@/stores/agent-activity.store";
import { useBackgroundTasksStore, type BackgroundTask } from "@/stores/background-tasks.store";

/**
 * The Activity Center -- one timeline of everything JARVIS is currently
 * doing.
 *
 * Three real sources, merged by timestamp:
 *
 * - **Background tasks** (`stores/background-tasks.store.ts`) — the
 *   Notification Framework's progress category.
 * - **Agent steps** (`stores/agent-activity.store.ts`) — the backend's
 *   `agent.step` WebSocket event, wired in M8 Phase 2.
 * - **Automation steps** — the backend's `automation.step` event, same
 *   store, same relay.
 *
 * **It merges, it does not store.** Adding a fourth "activity store"
 * that mirrored the other three would be the duplicate-state mistake
 * this project's rules single out — and it would go stale the moment one
 * of the three updated without it. The merge is a `useMemo` over live
 * store reads, so there is exactly one copy of every fact.
 *
 * Empty until something happens, which on a freshly-started backend is
 * the honest state rather than a defect.
 */

type ActivityKind = "task" | "agent" | "automation";

interface ActivityEntry {
  id: string;
  kind: ActivityKind;
  title: string;
  detail: string;
  at: string;
  status: "running" | "completed" | "failed";
}

function taskStatus(task: BackgroundTask): ActivityEntry["status"] {
  return task.status;
}

/** The backend sends `status` as a free string, so this maps the values
 *  the agent and automation runtimes actually emit and treats anything
 *  unrecognised as still running rather than inventing an outcome. */
function stepStatus(status: string): ActivityEntry["status"] {
  const lowered = status.toLowerCase();
  if (lowered === "completed" || lowered === "ok" || lowered === "success") return "completed";
  if (lowered === "failed" || lowered === "error") return "failed";
  return "running";
}

const KIND_ICON = {
  task: Loader2,
  agent: Bot,
  automation: Workflow,
} as const;

const STATUS_ICON = {
  running: Loader2,
  completed: CircleCheck,
  failed: CircleX,
} as const;

const STATUS_COLOR = {
  running: "text-muted-foreground",
  completed: "text-emerald-500",
  failed: "text-destructive",
} as const;

function ActivityRow({ entry }: { entry: ActivityEntry }) {
  const KindIcon = KIND_ICON[entry.kind];
  const StatusIcon = STATUS_ICON[entry.status];

  return (
    <li className="flex items-start gap-3 border-border/60 border-b px-3 py-2.5">
      <KindIcon
        className={`mt-0.5 size-3.5 shrink-0 text-muted-foreground ${
          entry.kind === "task" && entry.status === "running" ? "animate-spin" : ""
        }`}
        aria-hidden="true"
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium text-secondary">{entry.title}</p>
        {entry.detail && <p className="truncate text-muted-foreground text-xs">{entry.detail}</p>}
      </div>
      <StatusIcon
        className={`mt-0.5 size-3.5 shrink-0 ${STATUS_COLOR[entry.status]} ${
          entry.status === "running" ? "animate-spin" : ""
        }`}
        aria-label={entry.status}
      />
    </li>
  );
}

export function ActivityCenter() {
  const tasks = useBackgroundTasksStore((s) => s.tasks);
  const agentSteps = useAgentActivityStore((s) => s.agentSteps);
  const automationSteps = useAgentActivityStore((s) => s.automationSteps);

  const entries = useMemo<ActivityEntry[]>(() => {
    const merged: ActivityEntry[] = [
      ...tasks.map((task) => ({
        id: `task:${task.id}`,
        kind: "task" as const,
        title: task.label,
        detail: task.percent === null ? task.moduleId : `${task.moduleId} — ${task.percent}%`,
        at: task.timestamp,
        status: taskStatus(task),
      })),
      ...agentSteps.map((step) => ({
        id: `agent:${step.thread_id}:${step.step}`,
        kind: "agent" as const,
        title: `${step.node} (step ${step.step})`,
        detail: step.detail,
        at: step.receivedAt,
        status: stepStatus(step.status),
      })),
      ...automationSteps.map((step) => ({
        id: `automation:${step.step_id}`,
        kind: "automation" as const,
        title: step.action,
        detail: step.step_id,
        at: step.receivedAt,
        status: stepStatus(step.status),
      })),
    ];
    // Newest first: an activity feed is read from the top.
    return merged.sort((a, b) => b.at.localeCompare(a.at));
  }, [tasks, agentSteps, automationSteps]);

  if (entries.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 p-6 text-center">
        <Activity className="size-icon-lg text-muted-foreground" aria-hidden="true" />
        <p className="font-medium text-secondary">Nothing running</p>
        <p className="max-w-xs text-muted-foreground text-xs">
          Agent steps, automation runs and background tasks appear here as they happen.
        </p>
      </div>
    );
  }

  return (
    <VirtualList
      items={entries}
      estimatedItemHeight={60}
      className="h-full"
      renderItem={(entry) => <ActivityRow key={entry.id} entry={entry} />}
    />
  );
}
