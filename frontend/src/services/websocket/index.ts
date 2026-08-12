import { getApiBaseUrl } from "@/services/api/client";

import { WebSocketConnectionManager } from "./connection-manager";

/**
 * `/api/v1/ws`, per ARCHITECTURE.md section 6.
 *
 * Derived from the REST base URL rather than hardcoded (M8 Phase 2), so
 * the two transports cannot end up pointed at different backends -- the
 * REST client became configurable this phase (`VITE_API_BASE_URL`, for
 * the Tauri shell and `vite dev` reaching the Python process
 * differently), and a second hardcoded host here would have silently
 * ignored that. `http` becomes `ws`, `https` becomes `wss`.
 */
export function resolveWebSocketUrl(apiBaseUrl: string = getApiBaseUrl()): string {
  return `${apiBaseUrl.replace(/^http/, "ws")}/ws`;
}

export const websocketManager = new WebSocketConnectionManager(resolveWebSocketUrl());

export { isRelayedEvent, RELAYED_EVENTS, TRANSPORT_FRAMES } from "./types";
export type {
  AgentStepPayload,
  AutomationStepPayload,
  ConnectionStatus,
  HealthUpdatedPayload,
  PluginNotificationPayload,
  RelayedEvent,
  UpdatePhasePayload,
  VoiceStateChangedPayload,
  WebSocketEventHandler,
  WebSocketEventType,
  WebSocketMessage,
} from "./types";
export { WebSocketConnectionManager } from "./connection-manager";
