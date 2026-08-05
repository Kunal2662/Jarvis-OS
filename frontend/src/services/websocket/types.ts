/**
 * The WebSocket event vocabulary -- M8 Phase 2.
 *
 * **Every name here is one the backend actually relays.** Phase 1 wrote
 * this vocabulary from `ARCHITECTURE.md` section 6's *illustrative*
 * examples before any relay existed, and it drifted: of the fourteen
 * domain events it listed, eleven were never emitted by anything --
 * `ai.token`, `ai.step`, `ai.complete`, `voice.transcript_partial`,
 * `voice.transcript_final`, `automation.step_started`,
 * `automation.step_completed`, `automation.workflow_finished`,
 * `progress.update`, `notification.created`,
 * `runtime.module_state_changed`. A handler registered for any of them
 * would simply never fire, silently, forever.
 *
 * The list below is `EVENT_TYPE_NAMES` from
 * `core/lifecycle/runtime_ws_hub.py` -- the single map the relay
 * dispatches through. `websocket-contract.test.ts` pins the count so
 * that a backend event added without a client counterpart is a failing
 * test rather than a dead handler.
 *
 * `heartbeat` and `resume` are transport-level frames rather than
 * relayed domain events, so they are declared separately.
 */

export type ConnectionStatus =
  | "not_configured"
  | "connecting"
  | "connected"
  | "reconnecting"
  | "offline"
  | "error";

/** Frames the transport itself exchanges; never published on the EventBus. */
export const TRANSPORT_FRAMES = ["heartbeat", "resume"] as const;
export type TransportFrame = (typeof TRANSPORT_FRAMES)[number];

/**
 * Every `<category>.<event>` the backend relay can send, grouped the way
 * `runtime_ws_hub.py` groups them so the two can be diffed by eye.
 */
export const RELAYED_EVENTS = [
  // Runtime lifecycle (M9 Task Group B/C)
  "runtime.started",
  "runtime.ready",
  "runtime.stopping",
  "runtime.shutdown",
  "runtime.crash_recovered",
  "service.started",
  "service.stopped",
  "service.failed",
  "configuration.updated",
  "session.created",
  "session.closed",
  "health.updated",
  "task.started",
  "task.completed",
  "task.failed",
  "resource.budget_exceeded",
  // Plugin platform (M9 Task Group D)
  "plugin.discovered",
  "plugin.loaded",
  "plugin.load_failed",
  "plugin.unloaded",
  "plugin.enabled",
  "plugin.disabled",
  "plugin.installed",
  "plugin.uninstalled",
  "plugin.updated",
  "plugin.permission_granted",
  "plugin.permission_denied",
  "plugin.custom",
  "notification.plugin",
  // Agent runtime (M10)
  "agent.step",
  // Knowledge and memory (M10A)
  "memory.updated",
  "memory.recalled",
  "knowledge.entity_updated",
  "knowledge.correction_applied",
  // Intelligence layer (M10B)
  "goal.updated",
  "briefing.generated",
  // MCP platform (M10.5)
  "mcp.connection_changed",
  "mcp.capabilities_changed",
  "mcp.permission_denied",
  "mcp.handshake_completed",
  "mcp.negotiation_completed",
  "mcp.transport_failed",
  "mcp.heartbeat",
  "mcp.provider_changed",
  "mcp.auth_changed",
  // Voice and automation
  "voice.state_changed",
  "automation.step",
  "progress.update_phase",
  // Workspace platform (M11 Task Groups A-E)
  "workspace.updated",
  "project.updated",
  "note.updated",
  "task.updated",
  "calendar.updated",
  "calendar.event_updated",
  "reminder.updated",
  "file.updated",
  "folder.updated",
  "attachment.updated",
  "workspace.knowledge_linked",
  "workspace.assisted",
  "integration.call_completed",
] as const;

export type RelayedEvent = (typeof RELAYED_EVENTS)[number];
export type WebSocketEventType = RelayedEvent | TransportFrame;

const RELAYED_EVENT_SET: ReadonlySet<string> = new Set(RELAYED_EVENTS);

export function isRelayedEvent(name: string): name is RelayedEvent {
  return RELAYED_EVENT_SET.has(name);
}

/**
 * The envelope `runtime_ws_hub.envelope()` builds: the relay name, the
 * event's own id and timestamp, and the dataclass fields as `payload`.
 */
export interface WebSocketMessage<TPayload = unknown> {
  type: WebSocketEventType;
  id: string;
  occurred_at: string;
  payload: TPayload;
}

export type WebSocketEventHandler<TPayload = unknown> = (
  message: WebSocketMessage<TPayload>,
) => void;

// --- Payload shapes for the events this phase consumes ----------------
// Only the events Phase 2 actually wires are typed. An untyped event is
// still deliverable (handlers receive `unknown`); adding a shape here is
// how a later phase opts into type safety for the ones it uses.

/** `voice.state_changed` -- `VoiceStateChangedEvent`. */
export interface VoiceStateChangedPayload {
  state: string;
  detail: string;
}

/** `agent.step` -- `AgentStepEvent`. */
export interface AgentStepPayload {
  thread_id: string;
  step: number;
  node: string;
  status: string;
  detail: string;
}

/** `automation.step` -- `AutomationStepEvent`. */
export interface AutomationStepPayload {
  step_id: string;
  action: string;
  status: string;
}

/** `progress.update_phase` -- `UpdatePhaseEvent`. */
export interface UpdatePhasePayload {
  session_id: string;
  phase: string;
  progress_percent: number;
  message: string;
}

/** `notification.plugin` -- `PluginNotificationEvent`. */
export interface PluginNotificationPayload {
  plugin_id: string;
  title: string;
  message: string;
}

/** `health.updated` -- `HealthUpdatedEvent`. */
export interface HealthUpdatedPayload {
  snapshot: Record<string, unknown>;
}
