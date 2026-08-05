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
};
