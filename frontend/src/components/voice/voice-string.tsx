import { motion, useReducedMotion, useTime, useTransform } from "motion/react";
import { cn } from "@/lib/utils";
import { useVoiceStateStore } from "@/stores/voice-state.store";
import type { VoiceState } from "@/core/voice-state-machine";

interface VoiceStringVisual {
  colorClassName: string;
  /** Peak wave height, px -- idle is nearly flat (a "breathing" line),
   *  active states are progressively louder. */
  amplitude: number;
  /** How many full sine cycles span the string's width. */
  frequency: number;
  /** Seconds per animation loop -- lower reads as more urgent/energetic. */
  periodSeconds: number;
  /** Whether a soft blurred duplicate renders behind the string for a
   *  glow -- idle deliberately has none, matching "minimal by default." */
  glow: boolean;
}

/**
 * JARVIS's voice identity (Phase 4, Task Group H) -- no Orb, no visible
 * state label ("Listening...", "Thinking...") -- the wave's own shape,
 * speed, and color communicate state. Driven purely by
 * `useVoiceStateStore`; this component has no opinion about how the
 * store's value changes, only how to render whatever it currently is.
 */
const VOICE_STRING_VISUALS: Record<VoiceState, VoiceStringVisual> = {
  idle: { colorClassName: "text-muted-foreground", amplitude: 2, frequency: 1, periodSeconds: 6, glow: false },
  wake: { colorClassName: "text-accent", amplitude: 6, frequency: 1, periodSeconds: 1.4, glow: true },
  listening: { colorClassName: "text-accent", amplitude: 16, frequency: 3, periodSeconds: 0.9, glow: true },
  thinking: { colorClassName: "text-warning", amplitude: 10, frequency: 2, periodSeconds: 2.2, glow: true },
  speaking: { colorClassName: "text-accent", amplitude: 20, frequency: 4, periodSeconds: 0.6, glow: true },
  success: { colorClassName: "text-success", amplitude: 9, frequency: 2, periodSeconds: 0.9, glow: true },
  error: { colorClassName: "text-destructive", amplitude: 9, frequency: 5, periodSeconds: 0.35, glow: true },
};

/** Not shown visibly (the brief's own "no state labels" rule) -- this is
 *  the string's accessible name only, for screen reader users who can't
 *  perceive an animation's shape/speed/color. */
const VOICE_STATE_LABELS: Record<VoiceState, string> = {
  idle: "Idle",
  wake: "Waking up",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  success: "Done",
  error: "Something went wrong",
};

const VIEWBOX_WIDTH = 320;
const VIEWBOX_HEIGHT = 64;
const WAVE_POINTS = 48;

function buildWavePath(elapsedMs: number, visual: VoiceStringVisual): string {
  const midY = VIEWBOX_HEIGHT / 2;
  const phase = (elapsedMs / 1000 / visual.periodSeconds) * Math.PI * 2;
  const segments: string[] = [];
  for (let i = 0; i <= WAVE_POINTS; i++) {
    const x = (i / WAVE_POINTS) * VIEWBOX_WIDTH;
    const y = midY + Math.sin((i / WAVE_POINTS) * Math.PI * 2 * visual.frequency + phase) * visual.amplitude;
    segments.push(`${i === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`);
  }
  return segments.join(" ");
}

export function VoiceString({ className }: { className?: string }) {
  const voiceState = useVoiceStateStore((s) => s.voiceState);
  const visual = VOICE_STRING_VISUALS[voiceState];
  // Motion's own reactive media-query hook (unlike `lib/motion.ts`'s
  // `prefersReducedMotion()`, a one-time check) -- this component's wave
  // is a continuous `useTime()`-driven loop, not a discrete `animate`
  // transition, so `MotionConfig`'s app-wide `reducedMotion="user"`
  // (providers/app-providers.tsx) doesn't automatically cover it; it
  // must branch here itself.
  const reducedMotion = useReducedMotion();
  const time = useTime();
  const path = useTransform(time, (elapsedMs) => buildWavePath(reducedMotion ? 0 : elapsedMs, visual));

  return (
    <svg
      viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`}
      role="img"
      aria-label={VOICE_STATE_LABELS[voiceState]}
      className={cn("h-16 w-full max-w-xs", visual.colorClassName, className)}
    >
      {visual.glow && (
        <motion.path
          d={path}
          fill="none"
          stroke="currentColor"
          strokeWidth={6}
          strokeLinecap="round"
          className="opacity-30 blur-md"
          aria-hidden="true"
        />
      )}
      <motion.path d={path} fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" />
    </svg>
  );
}
