/**
 * Message shape and event-name vocabulary, per ARCHITECTURE.md section 6.
 * Every field here mirrors the standard exactly -- this file has no
 * authority to invent a different shape.
 */

export type ConnectionStatus =
  | "not_configured"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "offline"
  | "error";

/** `<category>.<event>`, per ARCHITECTURE.md section 6's naming rule. */
export type WebSocketEventType =
  | "heartbeat"
  | "resume"
  | "voice.state_changed"
  | "voice.transcript_partial"
  | "voice.transcript_final"
  | "ai.token"
  | "ai.step"
  | "ai.complete"
  | "automation.step_started"
  | "automation.step_completed"
  | "automation.workflow_finished"
  | "memory.updated"
  | "memory.recalled"
  | "progress.update"
  | "notification.created"
  | "runtime.module_state_changed";

export interface WebSocketMessage<TPayload = unknown> {
  type: WebSocketEventType;
  id: string;
  occurred_at: string;
  payload: TPayload;
}

export type WebSocketEventHandler<TPayload = unknown> = (
  message: WebSocketMessage<TPayload>,
) => void;
