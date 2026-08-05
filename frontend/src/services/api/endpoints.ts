/**
 * Typed endpoint helpers -- M8 Phase 2's "API layer".
 *
 * One module rather than a file per feature. The alternative was
 * `services/api/{workspaces,tasks,files,...}.ts`, which is the right
 * shape once a feature owns enough surface to justify a file; today
 * these are two-line wrappers over `apiRequest`/`apiList`, and eleven
 * files of two lines each is filing rather than structure. A feature
 * that grows its own client (chat streaming, say) takes its own module
 * at that point.
 *
 * **Every path here exists.** They were checked against the running
 * application's OpenAPI schema, not against the roadmap's intentions --
 * which is how Phase 1's WebSocket vocabulary drifted. `api-contract.
 * test.ts` re-checks the shapes this module depends on.
 *
 * **No endpoint invents a response shape.** Collections return the
 * backend's real `{count, limit, offset, has_more}` page meta (M11 Task
 * Group F); single resources return `data` unwrapped.
 */

import { apiList, apiRequest, apiVoid, type Page } from "@/services/api/client";

// --- Shared query shapes ----------------------------------------------

/**
 * Declared as a `type` rather than an `interface` deliberately: only type
 * aliases get TypeScript's implicit index signature, and without one
 * these query objects are not assignable to `RequestOptions["query"]`
 * (`Record<string, ...>`). An `interface` here compiles everywhere except
 * the one place it is used.
 */
export type PageQuery = {
  limit?: number;
  offset?: number;
};

// --- Workspace platform (M11 Task Group A) ----------------------------

export interface Workspace {
  id: string;
  name: string;
  description: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  description: string;
  status: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface Note {
  id: string;
  workspace_id: string;
  project_id: string | null;
  title: string;
  content: string;
  content_format: string;
  pinned: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export const workspacesApi = {
  list: (query: PageQuery & { status?: string } = {}): Promise<Page<Workspace>> =>
    apiList<Workspace>("/workspaces", { query }),
  get: (id: string): Promise<Workspace> => apiRequest<Workspace>(`/workspaces/${id}`),
  overview: (id: string): Promise<Record<string, unknown>> =>
    apiRequest(`/workspaces/${id}/overview`),
  context: (id: string): Promise<Record<string, unknown>> =>
    apiRequest(`/workspaces/${id}/context`),
};

export const projectsApi = {
  list: (query: PageQuery & { workspace_id?: string; status?: string } = {}): Promise<Page<Project>> =>
    apiList<Project>("/projects", { query }),
};

export const notesApi = {
  list: (query: PageQuery & { workspace_id?: string; project_id?: string } = {}): Promise<Page<Note>> =>
    apiList<Note>("/notes", { query }),
  get: (id: string): Promise<Note> => apiRequest<Note>(`/notes/${id}`),
};

// --- Productivity (M11 Task Group B) ----------------------------------

export interface Task {
  id: string;
  workspace_id: string;
  project_id: string | null;
  title: string;
  description: string;
  status: string;
  priority: string;
  due_at: string | null;
  tags: string[];
}

export interface Reminder {
  id: string;
  workspace_id: string;
  title: string;
  notes: string;
  status: string;
  remind_at: string | null;
}

export const tasksApi = {
  list: (
    query: PageQuery & {
      workspace_id?: string;
      project_id?: string;
      status?: string;
      priority?: string;
      tag?: string;
    } = {},
  ): Promise<Page<Task>> => apiList<Task>("/tasks", { query }),
  agenda: (workspace_id: string, horizon_days?: number): Promise<Record<string, unknown>> =>
    apiRequest("/tasks/agenda", { query: { workspace_id, horizon_days } }),
};

export const remindersApi = {
  list: (
    query: PageQuery & { workspace_id?: string; status?: string } = {},
  ): Promise<Page<Reminder>> => apiList<Reminder>("/reminders", { query }),
  due: (workspace_id?: string): Promise<Record<string, unknown>> =>
    apiRequest("/reminders/due", { query: { workspace_id } }),
};

// --- Files (M11 Task Group C) -----------------------------------------

export interface FileRecord {
  id: string;
  filename: string;
  workspace_id: string;
  folder_id: string | null;
  relative_path: string;
  extension: string;
  mime_type: string;
  size_bytes: number;
  description: string;
}

export const filesApi = {
  list: (
    query: PageQuery & { workspace_id?: string; folder_id?: string; tag?: string } = {},
  ): Promise<Page<FileRecord>> => apiList<FileRecord>("/files", { query }),
  stats: (workspace_id: string): Promise<Record<string, unknown>> =>
    apiRequest("/files/stats", { query: { workspace_id } }),
};

// --- Universal search (M10A) ------------------------------------------

export interface SearchResult {
  id: string;
  title: string;
  content: string;
  source: string;
  score: number;
  uri: string;
  metadata: Record<string, unknown>;
}

export const searchApi = {
  /** `POST` because the query travels in a body, matching the backend
   *  route -- not a REST-purity choice this client gets to make. */
  query: (query: string, options: { top_k?: number; source_types?: string[] } = {}) =>
    apiRequest<SearchResult[]>("/search", {
      method: "POST",
      body: { query, top_k: options.top_k ?? 20, source_types: options.source_types },
    }),
};

// --- Settings (M8 Phase 2's own backend addition) ---------------------

export interface SettingsTree {
  [section: string]: unknown;
}

export const settingsApi = {
  /** The whole tree, secrets redacted server-side. */
  all: (): Promise<SettingsTree> => apiRequest<SettingsTree>("/settings"),
  one: (dottedKey: string): Promise<{ key: string; value: unknown }> =>
    apiRequest(`/settings/${dottedKey}`),
};

// --- Health (M0/M9) ---------------------------------------------------

export interface HealthResponse {
  status: string;
  version: string;
}

export const healthApi = {
  /** Deliberately *not* enveloped -- `/health` is a flat liveness probe
   *  by design (`ARCHITECTURE.md` section 5), so it bypasses
   *  `apiRequest`'s envelope unwrapping via a direct fetch in
   *  `connection.store.ts`. Declared here only for its type. */
  path: "/health" as const,
};

// --- Calendar (M11 Task Group B) --------------------------------------

export interface CalendarEvent {
  id: string;
  calendar_id: string;
  workspace_id: string;
  title: string;
  description: string;
  location: string;
  starts_at: string | null;
  ends_at: string | null;
  all_day: boolean;
}

export const calendarApi = {
  /** The backend's own agenda view, not a client-side date filter over
   *  every event — the server already knows how to answer this. */
  agenda: (workspace_id: string, horizon_days?: number): Promise<Record<string, unknown>> =>
    apiRequest("/calendar/agenda", { query: { workspace_id, horizon_days } }),
  occurrences: (query: {
    workspace_id?: string;
    start?: string;
    end?: string;
  }): Promise<CalendarEvent[]> => apiRequest<CalendarEvent[]>("/calendar/occurrences", { query }),
  events: (query: PageQuery & { workspace_id?: string; calendar_id?: string } = {}) =>
    apiList<CalendarEvent>("/calendar/events", { query }),
};

// --- Knowledge graph (M10A) -------------------------------------------

export const knowledgeApi = {
  ask: (question: string): Promise<Record<string, unknown>> =>
    apiRequest("/knowledge/ask", { query: { question } }),
  entity: (name: string): Promise<Record<string, unknown>> =>
    apiRequest(`/knowledge/entities/${encodeURIComponent(name)}`),
  /** The whole graph. Used by the Knowledge Graph status widget for a
   *  real entity/relation count — there is no dedicated stats route, and
   *  the backend is frozen, so this is the honest source. */
  export: (): Promise<Record<string, unknown>> => apiRequest("/knowledge/export"),
};

// --- Intelligence layer (M10B) ----------------------------------------

export interface Suggestion {
  id: string;
  title: string;
  detail: string;
  kind: string;
  score: number;
}

export const intelligenceApi = {
  briefing: (): Promise<Record<string, unknown>> => apiRequest("/intelligence/briefing"),
  suggestions: (): Promise<Suggestion[]> => apiRequest<Suggestion[]>("/intelligence/suggestions"),
  context: (): Promise<Record<string, unknown>> => apiRequest("/intelligence/context"),
};

// --- Plugins (M9 Task Group D) ----------------------------------------

export interface PluginSummary {
  plugin_id: string;
  name: string;
  version: string;
  state: string;
  enabled: boolean;
  permissions: string[];
}

export const pluginsApi = {
  list: (): Promise<PluginSummary[]> => apiRequest<PluginSummary[]>("/plugins"),
  get: (id: string): Promise<PluginSummary> => apiRequest<PluginSummary>(`/plugins/${id}`),
  enable: (id: string): Promise<Record<string, unknown>> =>
    apiRequest(`/plugins/${id}/enable`, { method: "POST" }),
  disable: (id: string): Promise<Record<string, unknown>> =>
    apiRequest(`/plugins/${id}/disable`, { method: "POST" }),
};

// --- Developer platform tools (M9 Task Group E) -----------------------
//
// §22.12-restricted, every one of them: these name backend services,
// API calls and internal state. `core/user-mode.ts` gates the surfaces
// that call them; the client functions themselves are unguarded because
// a gate in two places is a gate that can disagree with itself.

export interface ApiCallRecord {
  method: string;
  path: string;
  status_code: number;
  duration_ms: number;
  at: string;
}

export interface PerformanceMetric {
  name: string;
  value: number;
  unit: string;
}

export const devtoolsApi = {
  apiCalls: (limit?: number): Promise<ApiCallRecord[]> =>
    apiRequest<ApiCallRecord[]>("/devtools/api-calls", { query: { limit } }),
  logs: (limit?: number): Promise<Record<string, unknown>[]> =>
    apiRequest<Record<string, unknown>[]>("/devtools/logs", { query: { limit } }),
  performance: (): Promise<Record<string, unknown>> => apiRequest("/devtools/performance"),
  performanceMetrics: (): Promise<PerformanceMetric[]> =>
    apiRequest<PerformanceMetric[]>("/devtools/performance/metrics"),
  state: (): Promise<Record<string, unknown>> => apiRequest("/devtools/state"),
};

// --- MCP platform (M10.5) ---------------------------------------------
//
// §22.12-restricted -- provider names and routing.

export interface McpProvider {
  provider_id: string;
  name: string;
  state: string;
  transport: string;
}

export const mcpApi = {
  status: (): Promise<Record<string, unknown>> => apiRequest("/mcp/status"),
  providers: (): Promise<McpProvider[]> => apiRequest<McpProvider[]>("/mcp/providers"),
  providerHealth: (id: string): Promise<Record<string, unknown>> =>
    apiRequest(`/mcp/providers/${id}/health`),
  diagnostics: (): Promise<Record<string, unknown>> => apiRequest("/mcp/diagnostics"),
  connections: (): Promise<Record<string, unknown>[]> =>
    apiRequest<Record<string, unknown>[]>("/mcp/connections"),
  auth: (): Promise<Record<string, unknown>[]> =>
    apiRequest<Record<string, unknown>[]>("/mcp/auth"),
};

// --- Permissions (M9 Plugin Platform's PermissionModel) ---------------
//
// The roadmap files this under "the backend's Authorization Engine
// (M14)". M14 does not exist and is not this phase's to build; the
// Authorization Engine that *does* exist is M9's `PermissionModel`, which
// owns the same ten-scope vocabulary `core/permission-framework.ts`
// mirrors and is reachable through the routes below. Phase 2 surfaces
// that one. If M14 later supersedes it, this block is the single place
// that repoints.

export type PermissionState = "granted" | "denied" | "pending";

export interface PermissionEntry {
  plugin_id: string;
  scope: string;
  state: PermissionState;
}

export interface PermissionAuditEntry {
  plugin_id: string;
  scope: string;
  action: string;
  at: string;
}

export const permissionsApi = {
  forPlugin: (pluginId: string): Promise<PermissionEntry[]> =>
    apiRequest<PermissionEntry[]>(`/plugins/${pluginId}/permissions`),
  pending: (): Promise<PermissionEntry[]> =>
    apiRequest<PermissionEntry[]>("/permissions/pending"),
  auditLog: (): Promise<PermissionAuditEntry[]> =>
    apiRequest<PermissionAuditEntry[]>("/permissions/audit-log"),
  grant: (pluginId: string, scope: string): Promise<Record<string, unknown>> =>
    apiRequest(`/plugins/${pluginId}/permissions/${scope}/grant`, { method: "POST" }),
  deny: (pluginId: string, scope: string): Promise<Record<string, unknown>> =>
    apiRequest(`/plugins/${pluginId}/permissions/${scope}/deny`, { method: "POST" }),
  revoke: (pluginId: string, scope: string): Promise<Record<string, unknown>> =>
    apiRequest(`/plugins/${pluginId}/permissions/${scope}/revoke`, { method: "POST" }),
};

// --- Integrations (M11 Task Group E) ----------------------------------

export interface IntegrationSummary {
  integration_id: string;
  name: string;
  vendor: string;
  description: string;
  tags: string[];
  operation_count: number;
  auth_method: string;
  availability_note: string;
}

export const integrationsApi = {
  catalogue: (): Promise<IntegrationSummary[]> =>
    apiRequest<IntegrationSummary[]>("/integrations/catalogue"),
  installed: (): Promise<Record<string, unknown>[]> =>
    apiRequest<Record<string, unknown>[]>("/integrations"),
  disconnect: (id: string): Promise<void> =>
    apiVoid(`/integrations/${id}/disconnect`, { method: "POST" }),
  /** The audited egress point's own counters — the closest thing the
   *  frozen backend has to "API usage". Real call/failure counts, not a
   *  budget: budgets are `ARCHITECTURE.md` §22.2's Calibration Engine,
   *  which is approved and not built. §22.12-restricted. */
  gatewayStats: (): Promise<Record<string, number>> =>
    apiRequest<Record<string, number>>("/integrations/gateway/stats"),
};

// --- Permission audit log (M9) ----------------------------------------
//
// The only audit trail the frozen backend keeps. The Administrator
// Dashboard's "Audit Logs" requirement maps onto this and nothing wider;
// there is no general-purpose audit store to read.
export const auditApi = {
  permissionLog: (): Promise<PermissionAuditEntry[]> =>
    apiRequest<PermissionAuditEntry[]>("/permissions/audit-log"),
};
