import { useEffect, useState } from "react";
import { Play, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { VoiceWaveformRenderer } from "@/components/voice/voice-waveform-renderer";
import { canTransitionVoiceState, reachableVoiceStates, type VoiceState } from "@/core/voice-state-machine";
import { useVoiceAudioLevelsStore } from "@/stores/voice-audio-levels.store";
import { useVoiceStateStore } from "@/stores/voice-state.store";

const VOICE_STATE_LABELS: Record<VoiceState, string> = {
  idle: "Idle",
  wake: "Wake",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  success: "Success",
  error: "Error",
};

/** The realistic end-to-end flow auto-cycle steps through, one state
 *  per tick -- matches the real pipeline's own expected sequence
 *  (`core/voice-state-machine.ts`'s header comment), not an arbitrary
 *  order. */
const AUTO_CYCLE_SEQUENCE: VoiceState[] = ["wake", "listening", "thinking", "speaking", "success", "idle"];
const AUTO_CYCLE_STEP_MS = 1800;

/**
 * Developer Mode's Voice State Preview (Phase 4, Task Group H) -- the
 * one panel section allowed to actually drive the real
 * `useVoiceStateStore`, since manually forcing a voice state has no
 * legitimate end-user surface, only an animation-QA one. Disabled by
 * default (`stores/developer-mode.store.ts`'s existing lock), never
 * visible to end users. Manual buttons only ever offer legal next
 * states (`reachableVoiceStates`), so a click can never hit the store's
 * own transition validation and throw.
 */
export function VoiceStatePreview() {
  const voiceState = useVoiceStateStore((s) => s.voiceState);
  const transition = useVoiceStateStore((s) => s.transition);
  const microphoneLevel = useVoiceAudioLevelsStore((s) => s.microphoneLevel);
  const setMicrophoneLevel = useVoiceAudioLevelsStore((s) => s.setMicrophoneLevel);
  const ttsLevel = useVoiceAudioLevelsStore((s) => s.ttsLevel);
  const setTtsLevel = useVoiceAudioLevelsStore((s) => s.setTtsLevel);
  const [intensity, setIntensity] = useState(1);
  const [autoCycling, setAutoCycling] = useState(false);

  useEffect(() => {
    if (!autoCycling) return;
    let index = 0;
    const interval = setInterval(() => {
      const next = AUTO_CYCLE_SEQUENCE[index % AUTO_CYCLE_SEQUENCE.length];
      // Skip (don't throw) a tick that isn't legal from wherever the
      // state currently is -- e.g. auto-cycle got toggled on mid-way
      // through a manual sequence. The next tick tries the following
      // step in the list, which is legal again soon enough.
      if (canTransitionVoiceState(useVoiceStateStore.getState().voiceState, next)) {
        transition(next);
      }
      index += 1;
    }, AUTO_CYCLE_STEP_MS);
    return () => clearInterval(interval);
  }, [autoCycling, transition]);

  const nextStates = reachableVoiceStates(voiceState);

  return (
    <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4">
      <div className="flex items-center justify-center rounded-md border border-border bg-background p-6">
        {/* The raw renderer, not <VoiceString>, driven manually here --
            this panel needs full control over every input the renderer
            accepts (mic/TTS level, intensity), not just voice state.
            microphoneLevel/ttsLevel still write through the real
            useVoiceAudioLevelsStore below, the same store a real audio
            pipeline will publish to -- no separate fake preview path. */}
        <VoiceWaveformRenderer
          voiceState={voiceState}
          microphoneLevel={microphoneLevel}
          ttsLevel={ttsLevel}
          intensity={intensity}
        />
      </div>

      <div>
        <p className="mb-1 text-caption font-medium text-muted-foreground">Current state</p>
        <p className="text-secondary font-medium">{VOICE_STATE_LABELS[voiceState]}</p>
      </div>

      <div>
        <p className="mb-2 text-caption font-medium text-muted-foreground">Manual transition</p>
        <div className="flex flex-wrap gap-1.5">
          {nextStates.map((state) => (
            <Button
              key={state}
              variant="outline"
              size="sm"
              disabled={autoCycling}
              onClick={() => transition(state)}
            >
              {VOICE_STATE_LABELS[state]}
            </Button>
          ))}
        </div>
      </div>

      <Button variant={autoCycling ? "destructive" : "secondary"} size="sm" onClick={() => setAutoCycling((c) => !c)}>
        {autoCycling ? <Square aria-hidden="true" /> : <Play aria-hidden="true" />}
        {autoCycling ? "Stop auto-cycle" : "Auto-cycle for QA"}
      </Button>

      <div className="flex flex-col gap-3 border-border border-t pt-4">
        <p className="text-caption font-medium text-muted-foreground">
          Renderer inputs (real store fields -- what a real audio pipeline will publish to)
        </p>
        <LevelSlider label="Microphone level" value={microphoneLevel} onChange={setMicrophoneLevel} />
        <LevelSlider label="TTS level" value={ttsLevel} onChange={setTtsLevel} />
        <LevelSlider label="Intensity" value={intensity} onChange={setIntensity} />
      </div>
    </div>
  );
}

function LevelSlider({ label, value, onChange }: { label: string; value: number; onChange: (value: number) => void }) {
  const id = `voice-preview-${label.toLowerCase().replace(/\s+/g, "-")}`;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="flex justify-between text-caption text-muted-foreground">
        <span>{label}</span>
        <span>{Math.round(value * 100)}%</span>
      </label>
      <input
        id={id}
        aria-label={label}
        type="range"
        min={0}
        max={1}
        step={0.01}
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
        className="accent-accent"
      />
    </div>
  );
}
