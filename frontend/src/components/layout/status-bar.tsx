import { cn } from "@/lib/utils";
import { useConnectionStatus } from "@/hooks/use-connection-status";
import type { ConnectionStatus } from "@/services/websocket";

const STATUS_LABEL: Record<ConnectionStatus, string> = {
  not_configured: "Not connected",
  connecting: "Connecting…",
  connected: "Connected",
  reconnecting: "Reconnecting…",
  offline: "Offline",
  error: "Connection error",
};

const STATUS_DOT_CLASS: Record<ConnectionStatus, string> = {
  not_configured: "bg-muted-foreground",
  connecting: "bg-warning animate-pulse",
  connected: "bg-success",
  reconnecting: "bg-warning animate-pulse",
  offline: "bg-muted-foreground",
  error: "bg-destructive",
};

/**
 * Layout component only -- reports the *real* WebSocket connection state
 * from `services/websocket` (useConnectionStatus), never a hardcoded
 * "Connected". Until a backend WebSocket route exists, this will
 * honestly show "Not connected" / "Connection error", not fake data.
 */
export function StatusBar() {
  const status = useConnectionStatus();

  return (
    <footer className="flex h-8 shrink-0 items-center justify-between border-border border-t bg-card px-4 text-caption text-muted-foreground">
      <div className="flex items-center gap-2">
        <span className={cn("size-2 rounded-full", STATUS_DOT_CLASS[status])} aria-hidden="true" />
        <span>{STATUS_LABEL[status]}</span>
      </div>
      <span>JARVIS OS · v0.7.0-dev</span>
    </footer>
  );
}
