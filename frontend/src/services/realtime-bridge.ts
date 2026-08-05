/**
 * Where backend events become application state -- M8 Phase 2's Voice,
 * AI and Automation integration.
 *
 * Every subscription in the app lives here, in one function, for a
 * reason: a WebSocket handler registered inside a component effect fires
 * only while that component is mounted, which silently makes state
 * updates conditional on what the user happens to be looking at. Voice
 * state must be correct whether or not the voice orb is on screen. So the
 * bridge is installed once, at startup, and torn down once, at shutdown.
 *
 * It is also the only module that knows both vocabularies -- relay event
 * names on one side, store actions on the other. Nothing else imports
 * `websocketManager` to listen; components read stores.
 *
 * **Every handler here is registered against a name the backend really
 * relays**, checked against `event-contract.generated.json`. That file is
 * generated from `EVENT_TYPE_NAMES` and asserted current by both test
 * suites, so a typo or a renamed event fails a test instead of producing
 * a handler that never fires.
 */

import { websocketManager } from "@/services/websocket";
import type {
  AgentStepPayload,
  AutomationStepPayload,
  PluginNotificationPayload,
  VoiceStateChangedPayload,
} from "@/services/websocket";
import { useAgentActivityStore } from "@/stores/agent-activity.store";
import { useNotificationsStore } from "@/stores/notifications.store";
import { useVoiceStateStore } from "@/stores/voice-state.store";
import { VOICE_STATES, type VoiceState } from "@/core/voice-state-machine";

/**
 * The backend's `VoiceStateChangedEvent.state` is a plain `str`, so this
 * is a real boundary check rather than a formality: an unrecognised value
 * must not be forced into the state machine, which would throw inside a
 * WebSocket handler where nothing can catch it usefully.
 */
function toVoiceState(value: string): VoiceState | null {
  return (VOICE_STATES as readonly string[]).includes(value) ? (value as VoiceState) : null;
}

/**
 * Subscribe every store that is driven by a backend event. Returns the
 * teardown; calling it twice is harmless.
 */
export function installRealtimeBridge(): () => void {
  const unsubscribes: Array<() => void> = [];

  // --- Voice (replaces the PySide6 VoiceOrb's direct service calls) ---
  unsubscribes.push(
    websocketManager.on<VoiceStateChangedPayload>("voice.state_changed", (message) => {
      const next = toVoiceState(message.payload.state);
      if (!next) return;
      const store = useVoiceStateStore.getState();
      if (store.voiceState === next) return;
      try {
        store.transition(next);
      } catch {
        // The backend pipeline is the authority on what state it is in.
        // If it reports a jump this client's graph calls illegal, the
        // graph is the thing that is wrong, and dropping the update
        // would leave the UI showing a state the backend has left.
        useVoiceStateStore.setState({ voiceState: next });
      }
    }),
  );

  // --- AI (step-level agent progress; tokens are SSE, see the store) ---
  unsubscribes.push(
    websocketManager.on<AgentStepPayload>("agent.step", (message) => {
      useAgentActivityStore.getState().recordAgentStep(message.payload, message.occurred_at);
    }),
  );

  // --- Automation ----------------------------------------------------
  unsubscribes.push(
    websocketManager.on<AutomationStepPayload>("automation.step", (message) => {
      useAgentActivityStore.getState().recordAutomationStep(message.payload, message.occurred_at);
    }),
  );

  // --- Notification centre -------------------------------------------
  unsubscribes.push(
    websocketManager.on<PluginNotificationPayload>("notification.plugin", (message) => {
      useNotificationsStore.getState().add({
        id: message.id,
        title: message.payload.title,
        message: message.payload.message,
        severity: "info",
        createdAt: message.occurred_at,
        read: false,
      });
    }),
  );

  return () => {
    for (const unsubscribe of unsubscribes.splice(0)) unsubscribe();
  };
}

let installed: (() => void) | null = null;

/**
 * Install exactly once per app lifetime -- what the startup sequence
 * calls.
 *
 * Idempotent for the same reason `runStartupSequence` caches its promise:
 * React StrictMode deliberately double-invokes effects in development,
 * and a second `installRealtimeBridge()` would register a second handler
 * for every event, so each `agent.step` would be recorded twice. That is
 * a duplicate-data bug that only reproduces in development, which is the
 * worst kind to leave available.
 */
export function ensureRealtimeBridge(): void {
  installed ??= installRealtimeBridge();
}

/** Test seam -- uninstall and allow a fresh `ensureRealtimeBridge()`. */
export function resetRealtimeBridgeForTesting(): void {
  installed?.();
  installed = null;
}
