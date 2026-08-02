import { motion, useReducedMotion, useTime, useTransform, type MotionValue } from "motion/react";
import { cn } from "@/lib/utils";
import type { VoiceState } from "@/core/voice-state-machine";

/** How bar heights are shaped across the row -- the actual per-frame
 *  numbers still come from `computeBarHeight()` below; this only picks
 *  which spatial pattern that function applies. */
type WaveformEnvelope = "flat" | "center" | "wave" | "random";

interface WaveformStateVisual {
  colorClassName: string;
  /** Rest amplitude, 0..1 -- how tall bars sit with zero real audio
   *  input and the procedural motion at its low point (the "floor"). */
  restAmplitude: number;
  /** How much the procedural ambient motion varies bar height, 0..1. */
  variance: number;
  /** Seconds per animation cycle -- lower reads as more urgent/energetic. */
  periodSeconds: number;
  envelope: WaveformEnvelope;
  glow: boolean;
}

/**
 * Per-state shape (Phase 4, Task Group H revision -- bar waveform,
 * replacing the original single sine-path string). `envelope` names
 * come straight from the voice-experience brief: `center` is Wake's
 * "center pulse, wave expands outward"; `wave` is Thinking's "calm
 * flowing... slow rhythmic motion... different from Listening";
 * `random` (still fully deterministic, see `computeBarHeight` below)
 * is Listening/Speaking's reactive look; `flat` is Idle's "almost
 * flat" breathing and Error's "soft pulse."
 */
const WAVEFORM_STATE_VISUALS: Record<VoiceState, WaveformStateVisual> = {
  idle: { colorClassName: "text-muted-foreground", restAmplitude: 0.06, variance: 0.03, periodSeconds: 4, envelope: "flat", glow: false },
  wake: { colorClassName: "text-accent", restAmplitude: 0.16, variance: 0.35, periodSeconds: 1.1, envelope: "center", glow: true },
  listening: { colorClassName: "text-accent", restAmplitude: 0.26, variance: 0.55, periodSeconds: 0.8, envelope: "random", glow: true },
  thinking: { colorClassName: "text-warning", restAmplitude: 0.2, variance: 0.3, periodSeconds: 2.6, envelope: "wave", glow: true },
  speaking: { colorClassName: "text-accent", restAmplitude: 0.35, variance: 0.6, periodSeconds: 0.5, envelope: "random", glow: true },
  success: { colorClassName: "text-success", restAmplitude: 0.2, variance: 0.4, periodSeconds: 0.7, envelope: "center", glow: true },
  error: { colorClassName: "text-destructive", restAmplitude: 0.12, variance: 0.18, periodSeconds: 0.9, envelope: "flat", glow: true },
};

/** Not shown visibly (the voice-experience brief's own "no state
 *  labels" rule) -- the renderer's accessible name only. */
const VOICE_STATE_LABELS: Record<VoiceState, string> = {
  idle: "Idle",
  wake: "Waking up",
  listening: "Listening",
  thinking: "Thinking",
  speaking: "Speaking",
  success: "Done",
  error: "Something went wrong",
};

const BAR_COUNT = 40;
const BAR_HEIGHT_PX = 56;

/** Deterministic per-bar phase seed in [0, 2π) -- gives each bar in a
 *  `"random"`-envelope state a distinct but *stable* phase, so bars
 *  don't move in lockstep, without reaching for actual `Math.random()`
 *  (which would reseed every render and break animation continuity;
 *  it would also read as jitter rather than the "smooth interpolation,
 *  no jitter" the brief asks for -- these are still pure sine curves,
 *  just offset differently per bar). */
function pseudoRandomSeed(index: number): number {
  return (((index * 9301 + 49297) % 233280) / 233280) * Math.PI * 2;
}

/**
 * The real per-frame height (0..1) for one bar. `restAmplitude` +
 * `variance` + the sine terms are procedural ambient motion -- an
 * honest, designed animation curve, not fabricated audio data (the
 * same category as the rest/hover/loading motion everywhere else in
 * this app). `microphoneLevel`/`ttsLevel` are the real integration
 * point: always `0` today (no audio pipeline exists --
 * `stores/voice-audio-levels.store.ts`), additively boosting the
 * procedural baseline once they're real. Bars nearer the center react
 * more strongly to real audio than edge bars, matching how a real
 * center-weighted level meter reads.
 */
function computeBarHeight(
  index: number,
  elapsedMs: number,
  visual: WaveformStateVisual,
  microphoneLevel: number,
  ttsLevel: number,
  intensity: number,
): number {
  const t = (elapsedMs / 1000 / visual.periodSeconds) * Math.PI * 2;
  const centerDistance = Math.abs(index - (BAR_COUNT - 1) / 2) / ((BAR_COUNT - 1) / 2);

  let oscillation: number;
  switch (visual.envelope) {
    case "flat":
      oscillation = Math.sin(t + index * 0.15);
      break;
    case "center": {
      const falloff = 1 - centerDistance * 0.7;
      oscillation = Math.sin(t - centerDistance * 3) * falloff;
      break;
    }
    case "wave":
      oscillation = Math.sin(t - index * 0.3);
      break;
    case "random": {
      const seed = pseudoRandomSeed(index);
      oscillation = Math.sin(t + seed) * 0.6 + Math.sin(t * 1.7 + seed * 2.1) * 0.4;
      break;
    }
  }

  const proceduralLevel = visual.restAmplitude + oscillation * visual.variance;
  const audioBoost = (microphoneLevel + ttsLevel) * (0.4 + centerDistance * 0.3);
  return Math.max(0.04, Math.min(1, (proceduralLevel + audioBoost) * intensity));
}

interface WaveformBarProps {
  index: number;
  visual: WaveformStateVisual;
  time: MotionValue<number>;
  microphoneLevel: number;
  ttsLevel: number;
  intensity: number;
  reducedMotion: boolean;
}

function WaveformBar({ index, visual, time, microphoneLevel, ttsLevel, intensity, reducedMotion }: WaveformBarProps) {
  const scaleY = useTransform(time, (elapsedMs) =>
    computeBarHeight(index, reducedMotion ? 0 : elapsedMs, visual, microphoneLevel, ttsLevel, intensity),
  );

  return (
    <motion.span
      aria-hidden="true"
      className={cn("inline-block w-[3px] shrink-0 rounded-full", visual.colorClassName)}
      style={{ height: BAR_HEIGHT_PX, scaleY, transformOrigin: "center", backgroundColor: "currentColor" }}
    />
  );
}

export interface VoiceWaveformRendererProps {
  /** The one required input -- everything else has a real, honest
   *  default (silence) until a real pipeline provides it. */
  voiceState: VoiceState;
  /** 0..1 real microphone input amplitude. Default `0` -- see
   *  `stores/voice-audio-levels.store.ts`. */
  microphoneLevel?: number;
  /** 0..1 real TTS output amplitude. Default `0`, same store. */
  ttsLevel?: number;
  /** 0..1 overall animation energy multiplier -- lets a caller (e.g.
   *  Developer Mode's Voice State Preview) turn the whole waveform up
   *  or down without touching per-state visual configs. */
  intensity?: number;
  className?: string;
}

/**
 * The pure waveform renderer (Phase 4, Task Group H revision) --
 * many independently-animating bars, replacing the original single
 * sine-path string, styled as a glass panel (blurred translucent
 * background, soft state-colored bloom) rather than a bare SVG.
 * Deliberately has NO store dependency of its own -- `VoiceString`
 * (`components/voice/voice-string.tsx`) is the thin layer that wires
 * real state in; this component is reusable and independently
 * testable with whatever props a caller (production, a test, or
 * Developer Mode's manual level sliders) supplies.
 *
 * Each bar derives its height from a single shared `useTime()` clock
 * via `useTransform` (one requestAnimationFrame loop feeding many
 * cheap derived values, not N independent RAF subscriptions), and
 * binds directly to the DOM through Motion's `style` prop -- no React
 * re-render per frame, `transform`-only (GPU-compositable), no layout
 * shifts.
 */
export function VoiceWaveformRenderer({
  voiceState,
  microphoneLevel = 0,
  ttsLevel = 0,
  intensity = 1,
  className,
}: VoiceWaveformRendererProps) {
  const visual = WAVEFORM_STATE_VISUALS[voiceState];
  // Motion's own reactive media-query hook, not `lib/motion.ts`'s
  // one-time `prefersReducedMotion()` -- this is a continuous
  // `useTime()`-driven loop, not a discrete `animate` transition, so
  // `MotionConfig`'s app-wide `reducedMotion="user"` doesn't cover it.
  const reducedMotion = useReducedMotion();
  const time = useTime();

  return (
    <div
      role="img"
      aria-label={VOICE_STATE_LABELS[voiceState]}
      className={cn(
        "relative flex w-full max-w-xs items-center justify-center gap-[3px] overflow-hidden rounded-2xl border border-border/60 bg-card/40 px-6 py-5 backdrop-blur-xl",
        className,
      )}
    >
      {visual.glow && (
        <div
          aria-hidden="true"
          className={cn("-z-10 absolute inset-4 rounded-full opacity-25 blur-2xl", visual.colorClassName)}
          style={{ backgroundColor: "currentColor" }}
        />
      )}
      {Array.from({ length: BAR_COUNT }, (_, index) => (
        <WaveformBar
          key={index}
          index={index}
          visual={visual}
          time={time}
          microphoneLevel={microphoneLevel}
          ttsLevel={ttsLevel}
          intensity={intensity}
          reducedMotion={reducedMotion ?? false}
        />
      ))}
    </div>
  );
}
