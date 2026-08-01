import { useSyncExternalStore } from "react";
import { websocketManager } from "@/services/websocket";
import type { ConnectionStatus } from "@/services/websocket";

/**
 * The real, current WebSocket connection status -- `useSyncExternalStore`
 * so components re-render exactly when the manager's status actually
 * changes, never a polled or assumed value.
 */
export function useConnectionStatus(): ConnectionStatus {
  return useSyncExternalStore(
    (onChange) => websocketManager.onStatusChange(() => onChange()),
    () => websocketManager.getStatus(),
  );
}
