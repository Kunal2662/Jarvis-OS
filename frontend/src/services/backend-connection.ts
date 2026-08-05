/**
 * Backend connection lifecycle -- M8 Phase 2's "Authentication flow",
 * "Offline support" and the wiring that makes the WebSocket carry a real
 * session.
 *
 * One place owns the order of operations, because the order matters and
 * getting it wrong is subtle:
 *
 *   1. reach the backend at all (`/health`, unauthenticated)
 *   2. obtain a session (`POST /sessions`)
 *   3. open the WebSocket with that session's token
 *
 * Doing (3) before (2) produces a socket the server immediately closes;
 * doing (2) before (1) produces a confusing auth error when the real
 * problem is that the Python process is not running. The phase's rule is
 * "never fake data -- an explicit *disconnected* state", and telling
 * those two failures apart is what makes the disconnected state
 * *explicit* rather than a shrug.
 *
 * **This module holds no React.** It is a service; `useBackendStatus`
 * (hooks) is the React-facing read, matching the phase's mandated
 * Business Logic -> Service Layer -> Hooks -> Store direction.
 */

import { getApiBaseUrl, ApiError } from "@/services/api/client";
import { ensureSession, endSession, getSessionToken } from "@/services/api/session";
import { websocketManager } from "@/services/websocket";
import type { ConnectionStatus } from "@/services/websocket";

/**
 * What the application knows about the backend right now.
 *
 * Deliberately distinct from `ConnectionStatus`, which describes the
 * *socket*. A backend can be reachable and authenticated while the
 * socket is mid-reconnect; conflating them would make the UI flash
 * "offline" during a routine reconnect.
 */
export type BackendState =
  | "idle"
  | "connecting"
  | "ready"
  | "unreachable"
  | "unauthenticated"
  | "error";

export interface BackendStatus {
  state: BackendState;
  /** Human-readable reason, empty when `state` is `ready`. */
  detail: string;
  socket: ConnectionStatus;
  /** Whether a session token is currently installed. */
  authenticated: boolean;
}

/** Long enough for a busy local process, short enough that a wrong
 *  `VITE_API_BASE_URL` shows an error instead of hanging the splash. */
const PING_TIMEOUT_MS = 3_000;

type Listener = (status: BackendStatus) => void;

const listeners = new Set<Listener>();

let status: BackendStatus = {
  state: "idle",
  detail: "",
  socket: websocketManager.getStatus(),
  authenticated: false,
};

websocketManager.onStatusChange((socket) => {
  publish({ ...status, socket });
});

function publish(next: BackendStatus): void {
  status = next;
  for (const listener of listeners) listener(status);
}

export function getBackendStatus(): BackendStatus {
  return status;
}

export function subscribeToBackendStatus(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/**
 * Is the Python process answering at all?
 *
 * `/health` rather than any authenticated route, because this question
 * must be answerable *before* a session exists. It also bypasses
 * `apiRequest`: `/health` is one of the three routes that deliberately
 * returns a flat body instead of the `{data, meta}` envelope
 * (`ARCHITECTURE.md` section 5), so unwrapping `data` would read
 * `undefined` from a perfectly healthy backend.
 */
export async function pingBackend(signal?: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch(`${getApiBaseUrl()}/health`, {
      // A refused connection rejects immediately, but a backend that is
      // *starting* accepts the socket and then thinks for a while. This
      // call runs inside the startup sequence, so an unbounded wait there
      // is a hung splash screen; a bounded one is an honest "not
      // reachable yet" that the retry path can correct.
      signal: signal ?? AbortSignal.timeout(PING_TIMEOUT_MS),
    });
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Bring the backend connection up, or report precisely why it did not
 * come up. Safe to call again -- it is the reconnect path too.
 */
export async function connectBackend(): Promise<BackendStatus> {
  publish({ ...status, state: "connecting", detail: "" });

  if (!(await pingBackend())) {
    publish({
      ...status,
      state: "unreachable",
      detail: "The JARVIS backend is not running.",
      authenticated: false,
    });
    return status;
  }

  try {
    await ensureSession();
  } catch (error) {
    const message = error instanceof ApiError ? error.message : String(error);
    publish({
      ...status,
      state: error instanceof ApiError && error.isOffline ? "unreachable" : "unauthenticated",
      detail: message,
      authenticated: false,
    });
    return status;
  }

  const token = getSessionToken();
  if (!token) {
    publish({
      ...status,
      state: "unauthenticated",
      detail: "No session token was issued.",
      authenticated: false,
    });
    return status;
  }

  websocketManager.connect(token);
  publish({ ...status, state: "ready", detail: "", authenticated: true });
  return status;
}

/** Tear everything down -- socket first, then the session it used. */
export async function disconnectBackend(): Promise<void> {
  websocketManager.disconnect();
  await endSession();
  publish({
    state: "idle",
    detail: "",
    socket: websocketManager.getStatus(),
    authenticated: false,
  });
}

/** Test seam -- resets observable state without touching the network. */
export function resetBackendStatusForTesting(): void {
  status = {
    state: "idle",
    detail: "",
    socket: websocketManager.getStatus(),
    authenticated: false,
  };
}
