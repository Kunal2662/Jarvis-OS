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
 * per ARCHITECTURE.md section 6.
 *
 * **Now connected to a real route (M8 Phase 2).** Phase 1's version of
 * this docstring said "there is no backend WebSocket route to connect to
 * yet (confirmed: zero `@app.websocket` routes exist)". That stopped
 * being true when M9 Task Group B shipped `/api/v1/ws` and
 * `RuntimeWebSocketHub`; the note is corrected here rather than left to
 * mislead the next reader.
 *
 * The route authenticates with `?token=<session_id>` -- the same
 * credential the REST client sends as a Bearer header, because
 * `ARCHITECTURE.md` section 6 specifies one session concept across both
 * transports. A connection attempt without a token is refused by the
 * server, so `connect()` requires one rather than trying anonymously and
 * reporting a confusing close.
 */
export class WebSocketConnectionManager {
  private socket: WebSocket | null = null;
  private token: string | null = null;
  private status: ConnectionStatus = "not_configured";
  private lastMessageId: string | null = null;
  private reconnectAttempt = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly handlers = new Map<WebSocketEventType, Set<WebSocketEventHandler>>();
  private readonly statusHandlers = new Set<(status: ConnectionStatus) => void>();
  private readonly url: string;
  private intentionalClose = false;

  constructor(url: string) {
    this.url = url;
  }

  /**
   * Open the connection. *token* is a session id from
   * `services/api/session.ts`; the server closes an untokened socket, so
   * a caller with no session should establish one first rather than
   * calling this and reading the failure.
   */
  connect(token: string): void {
    if (this.socket) return;
    this.token = token;
    this.setStatus(this.reconnectAttempt > 0 ? "reconnecting" : "connecting");

    const socket = new WebSocket(`${this.url}?token=${encodeURIComponent(token)}`);
    this.socket = socket;

    socket.addEventListener("open", this.handleOpen);
    socket.addEventListener("message", this.handleMessage);
    socket.addEventListener("close", this.handleClose);
    socket.addEventListener("error", this.handleError);
  }

  disconnect(): void {
    this.intentionalClose = true;
    this.clearTimers();
    this.socket?.close();
    this.socket = null;
    this.token = null;
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
    if (this.intentionalClose) {
      this.intentionalClose = false;
      return;
    }
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
    // Reconnect with the same token. If the backend restarted, that
    // token is stale and the socket will close again -- which is what
    // `onStatusChange` reports, and what drives the app to establish a
    // fresh session rather than this class guessing at auth.
    const token = this.token;
    if (!token) return;
    const delay =
      RECONNECT_DELAYS_MS[Math.min(this.reconnectAttempt, RECONNECT_DELAYS_MS.length - 1)];
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => this.connect(token), delay);
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
