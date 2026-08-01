/**
 * The API Interface (Task 12) -- formalizes `services/api/client.ts`
 * and `services/websocket/` (both built in Phase 1) as the ONLY path a
 * module may use to reach the backend, per this phase's explicit rule:
 * "Never direct database access. Never direct backend calls." This file
 * adds no new transport -- it scopes the existing one to a module id, so
 * a module never constructs its own `fetch`/`WebSocket` call and never
 * bypasses the shared REST/WebSocket client.
 */

import { apiRequest } from "@/services/api/client";
import { websocketManager } from "@/services/websocket";
import type { WebSocketEventHandler, WebSocketEventType } from "@/services/websocket";

export interface ModuleApiClient {
  /** Scoped under `/api/v1/<moduleId>/...` -- a module never supplies
   *  its own base path. */
  get<T>(path: string, signal?: AbortSignal): Promise<T>;
  post<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T>;
  put<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T>;
  patch<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T>;
  delete<T>(path: string, signal?: AbortSignal): Promise<T>;
  /** Subscribes to a WebSocket event category, auto-unsubscribed by the
   *  caller's own returned function -- the single shared connection
   *  (services/websocket), never a module-owned socket. */
  onEvent<TPayload = unknown>(
    type: WebSocketEventType,
    handler: WebSocketEventHandler<TPayload>,
  ): () => void;
}

/**
 * The only place a `ModuleApiClient` is constructed -- `BaseApplication`
 * (Task 1) calls this once per module and hands the result to that
 * module's Service Layer; nothing else in `core/` or a future module
 * imports `services/api/client.ts` or `services/websocket` directly.
 */
export function createModuleApiClient(moduleId: string): ModuleApiClient {
  const scopedPath = (path: string) => `/${moduleId}${path.startsWith("/") ? path : `/${path}`}`;
  return {
    get: (path, signal) => apiRequest(scopedPath(path), { method: "GET", signal }),
    post: (path, body, signal) => apiRequest(scopedPath(path), { method: "POST", body, signal }),
    put: (path, body, signal) => apiRequest(scopedPath(path), { method: "PUT", body, signal }),
    patch: (path, body, signal) => apiRequest(scopedPath(path), { method: "PATCH", body, signal }),
    delete: (path, signal) => apiRequest(scopedPath(path), { method: "DELETE", signal }),
    onEvent: (type, handler) => websocketManager.on(type, handler),
  };
}
