import type { ConnectionStatus } from "@/services/websocket";

/**
 * The one shared label/color mapping for `ConnectionStatus`
 * (`services/websocket`) -- originally declared only inside
 * `components/layout/status-bar-contributions.tsx`'s Connection Status
 * item; extracted here once the Dashboard's System Status widget
 * (`features/dashboard/dashboard-widgets.tsx`) needed the exact same
 * mapping, so both consumers read one table instead of two copies
 * drifting apart.
 */
export const CONNECTION_STATUS_LABEL: Record<ConnectionStatus, string> = {
  not_configured: "Not connected",
  connecting: "Connecting…",
  connected: "Connected",
  reconnecting: "Reconnecting…",
  offline: "Offline",
  error: "Connection error",
};

export const CONNECTION_STATUS_DOT_CLASS: Record<ConnectionStatus, string> = {
  not_configured: "bg-muted-foreground",
  connecting: "bg-warning animate-pulse",
  connected: "bg-success",
  reconnecting: "bg-warning animate-pulse",
  offline: "bg-muted-foreground",
  error: "bg-destructive",
};
