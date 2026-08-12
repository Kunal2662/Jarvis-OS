/**
 * The authentication flow -- M8 Phase 2's "Authentication flow against
 * the FastAPI backend".
 *
 * A JARVIS session is not a user login. There are no accounts: the
 * backend issues a runtime session id (`POST /api/v1/sessions`) which is
 * the Bearer token for every other REST route *and* the `?token=` query
 * parameter the WebSocket expects. One credential, two transports --
 * `ARCHITECTURE.md` section 5/6's rule, and the reason this module is
 * the only place that talks to `/sessions`.
 *
 * **Why the token is not persisted.** It would be tempting to keep it in
 * `localStorage` so a reload skips a round trip. Two reasons not to:
 * the backend's session table does not survive a backend restart, so a
 * persisted token is usually stale by the time it is read; and M11 Task
 * Group F tightened `/sessions/{id}` precisely because a session id
 * leaking is a real problem, which argues for keeping it in memory for
 * one page lifetime rather than on disk indefinitely. Establishing a
 * session costs one request at startup.
 */

import { apiRequest, apiVoid, setAuthToken } from "@/services/api/client";

export interface SessionInfo {
  session_id: string;
  conversation_id: string | null;
  thread_id: string | null;
  created_at: string;
  last_active_at: string;
}

let current: SessionInfo | null = null;

export function getSession(): SessionInfo | null {
  return current;
}

export function getSessionToken(): string | null {
  return current?.session_id ?? null;
}

/**
 * Obtain a session and install its token on the REST client.
 *
 * Anonymous by necessity: this is the call that *produces* the
 * credential every other call needs, which is why `POST /sessions` is
 * one of the backend's few deliberately unauthenticated routes.
 */
export async function createSession(
  options: { conversationId?: string; threadId?: string; metadata?: Record<string, unknown> } = {},
): Promise<SessionInfo> {
  const session = await apiRequest<SessionInfo>("/sessions", {
    method: "POST",
    anonymous: true,
    body: {
      conversation_id: options.conversationId ?? null,
      thread_id: options.threadId ?? null,
      metadata: options.metadata ?? { client: "jarvis-desktop" },
    },
  });
  current = session;
  setAuthToken(session.session_id);
  return session;
}

/**
 * Re-establish a session, reusing the existing one when it is still
 * live. Called at startup and again after the backend comes back from
 * an outage -- a reconnect must not silently keep presenting a token the
 * backend has forgotten.
 */
export async function ensureSession(): Promise<SessionInfo> {
  if (current) {
    try {
      // Requires the session's own token, which is already installed --
      // M11 Task Group F made this route reject anyone else's.
      const live = await apiRequest<SessionInfo>(`/sessions/${current.session_id}`);
      current = live;
      return live;
    } catch {
      // Expired, closed, or the backend restarted. Fall through and get
      // a fresh one rather than reporting a failure the caller cannot
      // act on.
      current = null;
      setAuthToken(null);
    }
  }
  return createSession();
}

/** Close the session server-side and forget it locally. */
export async function endSession(): Promise<void> {
  const session = current;
  current = null;
  if (!session) {
    setAuthToken(null);
    return;
  }
  try {
    await apiVoid(`/sessions/${session.session_id}`, { method: "DELETE" });
  } finally {
    // The local token is cleared whether or not the server accepted the
    // close: a token this client will not present again cannot be
    // misused from here, and leaving it installed after an intentional
    // sign-out would be the worse failure.
    setAuthToken(null);
  }
}

/** Test seam: drop in-memory session state without touching the network. */
export function resetSessionForTesting(): void {
  current = null;
  setAuthToken(null);
}
