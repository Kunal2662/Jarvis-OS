import type {
  ConnectionStatus,
  WebSocketEventHandler,
  WebSocketEventType,
  WebSocketMessage,
} from "./types";

const HEARTBEAT_INTERVAL_MS = 30_000;
const HEARTBEAT_TIMEOUT_MS = HEARTBEAT_INTERVAL_MS * 3; // miss 2 consecutive, per ARCHITECTURE.md section 6
const RECONNECT_DELAYS_MS = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000];

/**
 * The single WebSocket connection every event category multiplexes over,
 * per ARCHITECTURE.md section 6. This is real, working connection logic
 * (heartbeat monitoring, exponential-backoff reconnect, an event
 * dispatcher) -- but there is no backend WebSocket route to connect to
 * yet (confirmed: zero `@app.websocket` routes exist in
 * `infrastructure/api/` as of this phase). Pointed at a real URL, it
 * will genuinely try, genuinely fail, and honestly report
 * `"error"`/`"offline"` -- never a faked `"connected"` state.
 */
export class WebSocketConnectionManager {
  private socket: WebSocket | null = null;
  private status: ConnectionStatus = "not_configured";
  private lastMessageId: string | null = null;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly handlers = new Map<WebSocketEventType, Set<WebSocketEventHandler>>();
  private readonly statusHandlers = new Set<(status: ConnectionStatus) => void>();
  private readonly url: string;

  constructor(url: string) {
    this.url = url;
  }

  connect(token?: string): void {
    if (this.socket) return;
    this.setStatus(this.reconnectAttempt > 0 ? "reconnecting" : "connecting");

    const target = token ? `${this.url}?token=${encodeURIComponent(token)}` : this.url;
    const socket = new WebSocket(target);
    this.socket = socket;

    socket.addEventListener("open", this.handleOpen);
    socket.addEventListener("message", this.handleMessage);
    socket.addEventListener("close", this.handleClose);
    socket.addEventListener("error", this.handleError);
  }

  disconnect(): void {
    this.clearTimers();
    this.socket?.close();
    this.socket = null;
    this.reconnectAttempt = 0;
    this.setStatus("not_configured");
  }

  on<TPayload = unknown>(
    type: WebSocketEventType,
    handler: WebSocketEventHandler<TPayload>,
  ): () => void {
    const set = this.handlers.get(type) ?? new Set();
    set.add(handler as WebSocketEventHandler);
    this.handlers.set(type, set);
    return () => set.delete(handler as WebSocketEventHandler);
  }

  onStatusChange(handler: (status: ConnectionStatus) => void): () => void {
    this.statusHandlers.add(handler);
    handler(this.status);
    return () => this.statusHandlers.delete(handler);
  }

  getStatus(): ConnectionStatus {
    return this.status;
  }

  private handleOpen = (): void => {
    this.reconnectAttempt = 0;
    this.setStatus("connected");
    if (this.lastMessageId) {
      this.send({ type: "resume", last_id: this.lastMessageId });
    }
    this.armHeartbeatWatchdog();
  };

  private handleMessage = (event: MessageEvent<string>): void => {
    let message: WebSocketMessage;
    try {
      message = JSON.parse(event.data) as WebSocketMessage;
    } catch {
      return;
    }

    this.armHeartbeatWatchdog();
    if (message.type === "heartbeat") return;

    this.lastMessageId = message.id;
    for (const handler of this.handlers.get(message.type) ?? []) {
      handler(message);
    }
  };

  private handleClose = (): void => {
    this.socket = null;
    this.clearTimers();
    this.setStatus("offline");
    this.scheduleReconnect();
  };

  private handleError = (): void => {
    this.setStatus("error");
  };

  private send(payload: unknown): void {
    if (this.socket?.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify(payload));
    }
  }

  private scheduleReconnect(): void {
    const delay = RECONNECT_DELAYS_MS[Math.min(this.reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)];
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  private armHeartbeatWatchdog(): void {
    if (this.heartbeatTimer) clearTimeout(this.heartbeatTimer);
    this.heartbeatTimer = setTimeout(() => {
      this.socket?.close();
    }, HEARTBEAT_TIMEOUT_MS);
  }

  private clearTimers(): void {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.heartbeatTimer) clearTimeout(this.heartbeatTimer);
    this.reconnectTimer = null;
    this.heartbeatTimer = null;
  }

  private setStatus(status: ConnectionStatus): void {
    this.status = status;
    for (const handler of this.statusHandlers) handler(status);
  }
}
