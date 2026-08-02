/**
 * The Voice State Machine (Phase 4, Task Group H) -- mirrors
 * `core/module-lifecycle.ts`'s pattern exactly: a fixed set of states, a
 * validated transition graph, and a typed error for an illegal jump,
 * rather than a bare mutable field any caller can set to anything.
 * There is exactly one voice state for the whole app (unlike module
 * state, which is per-module), so this is a set of pure functions over
 * a `VoiceState` value, not a per-instance class -- `stores/voice-
 * state.store.ts` is the one place that owns the current value.
 *
 * No real voice backend exists yet (`core/interfaces/voice-integration.ts`
 * only covers command bindings, not a live state; there is no
 * WebSocket voice event relay). The graph below is built now, in full,
 * so that when that backend ships it only needs to call
 * `useVoiceStateStore.getState().transition(nextState)` -- the exact
 * same entry point Developer Mode's Voice State Preview panel already
 * uses -- never a UI refactor.
 */

export type VoiceState = "idle" | "wake" | "listening" | "thinking" | "speaking" | "success" | "error";

export const VOICE_STATES: readonly VoiceState[] = [
  "idle",
  "wake",
  "listening",
  "thinking",
  "speaking",
  "success",
  "error",
];

export class InvalidVoiceStateTransitionError extends Error {
  constructor(from: VoiceState, to: VoiceState) {
    super(`Cannot move from voice state "${from}" to "${to}"`);
    this.name = "InvalidVoiceStateTransitionError";
  }
}

/**
 * Legal next states per current state, matching the real voice pipeline
 * lifecycle: a wake word that times out returns to idle without ever
 * having listened; listening can be cancelled or fail (e.g. a
 * microphone-permission error); thinking and speaking can each fail
 * independently (the AI errors, or TTS synthesis fails); success and
 * error both settle back to idle rather than staying terminal.
 */
const TRANSITIONS: Record<VoiceState, readonly VoiceState[]> = {
  idle: ["wake"],
  wake: ["listening", "idle", "error"],
  listening: ["thinking", "idle", "error"],
  thinking: ["speaking", "error"],
  speaking: ["success", "error"],
  success: ["idle"],
  error: ["idle"],
};

export function canTransitionVoiceState(from: VoiceState, to: VoiceState): boolean {
  if (from === to) return true;
  return TRANSITIONS[from].includes(to);
}

export function assertValidVoiceStateTransition(from: VoiceState, to: VoiceState): void {
  if (!canTransitionVoiceState(from, to)) {
    throw new InvalidVoiceStateTransitionError(from, to);
  }
}

/** Every state reachable from `from` in one step -- Developer Mode's
 *  Voice State Preview panel uses this so it only ever offers buttons
 *  for legal transitions, rather than needing to catch a thrown error
 *  from a state a human clicked that the machine would have rejected. */
export function reachableVoiceStates(from: VoiceState): readonly VoiceState[] {
  return TRANSITIONS[from];
}
