/**
 * The Voice Integration Interface (Task 10) -- every module MAY
 * implement this to participate in JARVIS's voice pipeline. Pure
 * interface: no speech recognition, no TTS synthesis, no audio
 * processing lives here -- that is entirely M2's existing Voice
 * Platform (backend) scope, reached only through the API/WebSocket
 * layer (`voice.*` events, ARCHITECTURE.md section 6) once a module
 * implements this.
 */

import type { VoiceCommandBinding } from "@/core/module-manifest";

export interface VoiceAction {
  id: string;
  /** What actually runs -- the automation action id (see
   *  automation-integration.ts) this voice action triggers. A voice
   *  action is never its own separate execution path. */
  automationActionId: string;
}

export interface VoiceFeedback {
  /** Spoken back to the user via M2's existing TTS pipeline -- this
   *  interface only supplies the text, never synthesizes audio itself. */
  spokenText: string;
  /** Optional, shorter text shown in the Live Transcript view
   *  (IMPLEMENTATION_ROADMAP.md Phase 4) alongside the spoken feedback. */
  displayText?: string;
}

/** Implemented by a module that wants voice-command participation. */
export interface VoiceIntegration {
  /** The phrase -> command bindings this module contributes, matching
   *  its manifest's own `voiceCommands` (module-manifest.ts) --
   *  duplicated here as a live method (not just static manifest data)
   *  so a module can register bindings that depend on its current
   *  state (e.g. only "archive this email" while an email is open). */
  getVoiceCommands(): VoiceCommandBinding[];
  /** The actions behind each command id above. */
  getVoiceActions(): VoiceAction[];
  /** What to say back after a voice command completes -- success or
   *  failure both produce feedback, never silence. */
  getVoiceFeedback(commandId: string, result: "success" | "failure"): VoiceFeedback;
  /** Optional hotkey-style shortcuts this module wants active while
   *  the voice pipeline is listening (distinct from global hotkeys,
   *  which are HotkeySettings' existing backend concern). */
  getVoiceShortcuts(): { phrase: string; description: string }[];
}
