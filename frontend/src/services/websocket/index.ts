import { WebSocketConnectionManager } from "./connection-manager";

/**
 * `/api/v1/ws`, per ARCHITECTURE.md section 6 -- not configurable per
 * environment yet since there's exactly one backend target (localhost,
 * Tauri-hosted) until a real deployment story exists.
 */
const WEBSOCKET_URL = "ws://127.0.0.1:8000/api/v1/ws";

export const websocketManager = new WebSocketConnectionManager(WEBSOCKET_URL);

export type {
  ConnectionStatus,
  WebSocketEventHandler,
  WebSocketEventType,
  WebSocketMessage,
} from "./types";
export { WebSocketConnectionManager } from "./connection-manager";
