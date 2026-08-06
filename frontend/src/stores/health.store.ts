import { create } from "zustand";

/**
 * The backend's health snapshot -- M8 Phase 5's source of truth for every
 * "… Status" widget on the AI Dashboard.
 *
 * **It arrives over the WebSocket, not REST.** `GET /api/v1/health` is a
 * bare liveness probe (`{status, version}`) and deliberately so — its own
 * route docstring says a probe is polled by tooling that wants a flat,
 * minimal body. The *rich* snapshot is what `HealthMonitor.poll_once()`
 * publishes as `health.updated`, and the relay forwards it. So the
 * dashboard subscribes rather than polls, which is also why its numbers
 * move on their own without a refresh button.
 *
 * The backend is frozen, so this store adds no endpoint: it consumes an
 * event that has existed since M9 and that nothing on the frontend was
 * reading.
 *
 * **Every field below was read off the collectors that produce it**
 * (`core/lifecycle/health_monitor.py` and the two `register_collector`
 * calls in `app.py`), not guessed from the roadmap — the same discipline
 * M8 Phase 2's WebSocket contract fix established after eleven invented
 * event names shipped.
 */

/** `HealthMonitor.snapshot()`'s own keys. */
export interface HealthSnapshot {
  cpu_percent?: number;
  memory_rss_bytes?: number;
  disk_total_bytes?: number;
  disk_free_bytes?: number;
  uptime_seconds?: number;
  startup_duration_ms?: number;
  active_services?: string[];
  failed_services?: string[];
  restart_count?: number;
  status?: "healthy" | "degraded";
  /** The `mcp` collector (M10.5). Provider names live here — §22.12
   *  restricted, so only Developer/Administrator surfaces read it. */
  mcp?: {
    registered_transports?: string[];
    heartbeat_running?: boolean;
    heartbeats?: unknown[];
    providers?: Record<string, unknown>;
    auth?: Record<string, unknown>;
  };
  /** The `workspace_platform` collector (M11 Task Group F). */
  workspace_platform?: {
    files?: { storage_root?: string; storage_root_exists?: boolean; indexing_enabled?: boolean };
    ai_workspace?: {
      enabled?: boolean;
      assist_enabled?: boolean;
      context_budget_chars?: number;
    };
    egress?: Record<string, number>;
    search_sources?: string[];
  };
  [key: string]: unknown;
}

interface HealthState {
  /** `null` until the first `health.updated` arrives — distinguishable
   *  from a snapshot that happens to be empty, which would otherwise
   *  render as "everything is off" rather than "not known yet". */
  snapshot: HealthSnapshot | null;
  /** When the last snapshot arrived, so a stale one can be shown as
   *  stale rather than as current. */
  receivedAt: string | null;
  apply: (snapshot: HealthSnapshot, receivedAt?: string) => void;
  clear: () => void;
}

export const useHealthStore = create<HealthState>()((set) => ({
  snapshot: null,
  receivedAt: null,
  apply: (snapshot, receivedAt = new Date().toISOString()) => set({ snapshot, receivedAt }),
  // Called on disconnect: a snapshot from before an outage describes a
  // backend that is no longer running, and showing it as live is exactly
  // the fake data this project forbids.
  clear: () => set({ snapshot: null, receivedAt: null }),
}));

// --- Selectors --------------------------------------------------------
//
// Derived reads live here rather than in each widget so that "is the
// knowledge graph up?" has one answer. Each returns `null` for "not
// known", never a cheerful default.

export type SubsystemStatus = "healthy" | "degraded" | "disabled" | "unknown";

export function selectOverallStatus(s: HealthState): SubsystemStatus {
  if (!s.snapshot) return "unknown";
  return s.snapshot.status === "degraded" ? "degraded" : "healthy";
}

/** A named backend service's state, from the service manager's own
 *  running/failed lists. */
export function selectServiceStatus(name: string) {
  return (s: HealthState): SubsystemStatus => {
    if (!s.snapshot) return "unknown";
    if (s.snapshot.failed_services?.includes(name)) return "degraded";
    if (s.snapshot.active_services?.includes(name)) return "healthy";
    return "unknown";
  };
}

/** Knowledge and memory report through M10A's search-source registry: a
 *  source that unregistered itself is visible here rather than only as
 *  emptier results. */
export function selectSearchSources(s: HealthState): string[] {
  return s.snapshot?.workspace_platform?.search_sources ?? [];
}

export function selectSourceStatus(sourceType: string) {
  return (s: HealthState): SubsystemStatus => {
    if (!s.snapshot) return "unknown";

    // "The `workspace_platform` collector is not reporting at all" is
    // not the same as "it is reporting, and this source is missing from
    // its list". The first is *unknown*; only the second is a genuine
    // degradation. Returning "degraded" for both made a backend running
    // without that collector -- the API-only runtime, for instance --
    // light up Memory and Knowledge Graph amber, which reads as a fault
    // where there is none. Found against a live backend in the M8
    // Phase 7 pass; `selectServiceStatus` already drew this distinction
    // correctly and this now matches it.
    const sources = s.snapshot.workspace_platform?.search_sources;
    if (sources === undefined) return "unknown";

    return sources.includes(sourceType) ? "healthy" : "degraded";
  };
}

export function selectAiWorkspaceStatus(s: HealthState): SubsystemStatus {
  const ai = s.snapshot?.workspace_platform?.ai_workspace;
  if (!s.snapshot || !ai) return "unknown";
  if (!ai.enabled) return "disabled";
  return ai.assist_enabled ? "healthy" : "degraded";
}

export function selectFilesStatus(s: HealthState): SubsystemStatus {
  const files = s.snapshot?.workspace_platform?.files;
  if (!s.snapshot || !files) return "unknown";
  // An unwritable storage root is the failure this collector exists to
  // surface; it used to be invisible everywhere.
  return files.storage_root_exists ? "healthy" : "degraded";
}

/** Outbound API call counters from the audited egress gateway.
 *  §22.12-restricted: this names what the backend called. */
export function selectEgressStats(s: HealthState): Record<string, number> | null {
  return s.snapshot?.workspace_platform?.egress ?? null;
}

/** §22.12-restricted — provider names. */
export function selectProviders(s: HealthState): Record<string, unknown> | null {
  return s.snapshot?.mcp?.providers ?? null;
}

export function formatBytes(bytes: number | undefined): string {
  if (bytes === undefined) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 && unit > 0 ? 1 : 0)} ${units[unit]}`;
}

export function formatUptime(seconds: number | undefined): string {
  if (seconds === undefined) return "—";
  const days = Math.floor(seconds / 86_400);
  const hours = Math.floor((seconds % 86_400) / 3_600);
  const minutes = Math.floor((seconds % 3_600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}
