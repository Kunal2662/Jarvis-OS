import { create } from "zustand";
import {
  connectBackend,
  disconnectBackend,
  getBackendStatus,
  subscribeToBackendStatus,
  type BackendState,
} from "@/services/backend-connection";
import type { ConnectionStatus } from "@/services/websocket";

/**
 * The app's view of "is JARVIS there?" -- M8 Phase 2's Offline support.
 *
 * A thin mirror of `services/backend-connection.ts`, deliberately. The
 * service owns the logic and the ordering; this store exists only because
 * React components subscribe to Zustand and not to an ad-hoc listener
 * set. Putting the connect/ping/session sequence *in* the store would put
 * business logic in the state layer, which is the exact inversion of the
 * phase's mandated Business Logic -> Service Layer -> Hooks -> Store
 * direction.
 *
 * **Nothing here fabricates a value.** `state` starts `"idle"` -- not
 * `"ready"`, not an optimistic guess -- and only ever becomes something
 * else because the service observed it.
 */
interface ConnectionStoreShape {
  /** Reachability + authentication, from the service. */
  state: BackendState;
  /** Why, when `state` is not `ready`. Empty otherwise. */
  detail: string;
  /** The WebSocket's own status, which moves independently: a routine
   *  reconnect leaves `state` at `ready` while this says `reconnecting`. */
  socket: ConnectionStatus;
  authenticated: boolean;
  /** True while the very first connect attempt is in flight, so the UI
   *  can distinguish "still starting up" from "tried and failed". */
  hasAttempted: boolean;

  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
}

export const useConnectionStore = create<ConnectionStoreShape>()((set) => {
  const initial = getBackendStatus();

  // Subscribed once at module scope rather than in a component effect:
  // the connection outlives any particular mount, and a re-subscribing
  // effect would drop status changes that land between unmount and
  // remount.
  subscribeToBackendStatus((status) => {
    set({
      state: status.state,
      detail: status.detail,
      socket: status.socket,
      authenticated: status.authenticated,
    });
  });

  return {
    state: initial.state,
    detail: initial.detail,
    socket: initial.socket,
    authenticated: initial.authenticated,
    hasAttempted: false,

    connect: async () => {
      await connectBackend();
      set({ hasAttempted: true });
    },
    disconnect: async () => {
      await disconnectBackend();
    },
  };
});

/** Whether the app should render offline treatments. `connecting` is
 *  deliberately not offline -- it is "not yet known", and showing an
 *  offline banner during startup would be wrong for the ~100ms it takes
 *  to answer. */
export function selectIsOffline(s: ConnectionStoreShape): boolean {
  return s.hasAttempted && (s.state === "unreachable" || s.state === "error");
}

/** Whether real data can be requested right now. */
export function selectIsLive(s: ConnectionStoreShape): boolean {
  return s.state === "ready";
}
