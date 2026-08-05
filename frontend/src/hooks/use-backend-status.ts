import { useConnectionStore, selectIsLive, selectIsOffline } from "@/stores/connection.store";
import type { BackendState } from "@/services/backend-connection";
import type { ConnectionStatus } from "@/services/websocket";

export interface BackendStatusView {
  state: BackendState;
  detail: string;
  socket: ConnectionStatus;
  authenticated: boolean;
  /** Real data can be fetched right now. */
  isLive: boolean;
  /** The app should render offline treatments -- an explicit
   *  "disconnected" state, never placeholder data. */
  isOffline: boolean;
  /** A connect attempt is in flight and has not yet concluded. */
  isConnecting: boolean;
}

/**
 * The React-facing read of backend connectivity -- M8 Phase 2's Offline
 * support, at the Hooks layer of the phase's Business Logic -> Service
 * Layer -> Hooks -> Store shape.
 *
 * Distinct from `use-connection-status.ts`, which reports the *socket*
 * alone and is what a transport indicator wants. This hook answers the
 * question a feature actually asks -- "can I show real data?" -- which
 * depends on reachability and authentication too, and which stays `true`
 * through a routine socket reconnect.
 */
export function useBackendStatus(): BackendStatusView {
  const state = useConnectionStore((s) => s.state);
  const detail = useConnectionStore((s) => s.detail);
  const socket = useConnectionStore((s) => s.socket);
  const authenticated = useConnectionStore((s) => s.authenticated);
  const isLive = useConnectionStore(selectIsLive);
  const isOffline = useConnectionStore(selectIsOffline);

  return {
    state,
    detail,
    socket,
    authenticated,
    isLive,
    isOffline,
    isConnecting: state === "connecting",
  };
}
