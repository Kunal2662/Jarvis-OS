import { useEffect, useRef, useState } from "react";
import { animate, motion, useMotionTemplate, useMotionValue } from "motion/react";
import { JarvisLogo } from "@/components/startup/jarvis-logo";
import { VoiceString } from "@/components/voice/voice-string";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";
import { useVoiceStateStore } from "@/stores/voice-state.store";

type Phase =
  | "point"
  | "ripple"
  | "logo-assemble"
  | "logo-pulse"
  | "voice-morph"
  | "voice-activate"
  | "voice-expand"
  | "reveal";

const PHASE_ORDER: Phase[] = [
  "point",
  "ripple",
  "logo-assemble",
  "logo-pulse",
  "voice-morph",
  "voice-activate",
  "voice-expand",
  "reveal",
];

/** Milliseconds per phase -- an original, deliberately-choreographed
 *  timeline (~4.2s total), within the brief's "3-5 seconds maximum."
 *  This is a real design decision, not a fake loading delay: the real
 *  initialization work this sequence hides
 *  (`core/startup-orchestrator.ts`) finishes in well under 100ms today
 *  (no real backend exists for most of what a full boot would
 *  eventually do), so a purely work-driven duration would be too short
 *  to render the sequence at all -- `components/startup/startup-
 *  gate.tsx` awaits both this choreography AND the real work,
 *  whichever takes longer. */
const PHASE_DURATIONS_MS: Record<Phase, number> = {
  point: 400,
  ripple: 600,
  "logo-assemble": 900,
  "logo-pulse": 400,
  "voice-morph": 400,
  "voice-activate": 500,
  "voice-expand": 400,
  reveal: 600,
};

export interface StartupSequenceProps {
  onComplete: () => void;
}

/**
 * The cinematic startup sequence (Phase 4, Task Group I) -- an
 * original choreography (energy point → ripple → logo assembles from
 * light → energy pulse → morphs into the real, unmodified
 * `VoiceString` → brief activation → expands → reveals the real app
 * beneath it) with no visible text at any point; state is
 * communicated purely through motion, exactly like `VoiceString`
 * itself. During the voice-morph/voice-expand beats it drives the
 * *real* `useVoiceStateStore` (idle → wake → idle) -- a genuine
 * "JARVIS waking up" gesture through the same mechanism a real voice
 * pipeline will use later, not a cosmetic copy of it.
 */
export function StartupSequence({ onComplete }: StartupSequenceProps) {
  const disableGlassEffects = useAccessibilityPreferencesStore((s) => s.disableGlassEffects);
  const [phase, setPhase] = useState<Phase>("point");
  const onCompleteRef = useRef(onComplete);
  onCompleteRef.current = onComplete;

  // Grows from 0% to well past full-screen coverage during the final
  // "reveal" beat -- an animated CSS mask, not React state per frame,
  // so the center-outward iris reveal costs nothing but a single
  // Motion-driven DOM mutation per frame (useMotionTemplate builds the
  // mask-image string from the MotionValue without re-rendering React).
  const revealRadius = useMotionValue(0);
  const maskImage = useMotionTemplate`radial-gradient(circle at 50% 50%, transparent ${revealRadius}%, black calc(${revealRadius}% + 15%))`;

  useEffect(() => {
    let cancelled = false;
    let activeTimeout: ReturnType<typeof setTimeout> | undefined;

    function runPhase(index: number) {
      if (cancelled) return;
      const current = PHASE_ORDER[index];
      setPhase(current);

      // The one real integration point: the startup sequence drives
      // the actual voice state machine, not a look-alike animation --
      // `wake` at the morph beat (the logo "waking up" into the voice
      // identity), settling back to `idle` once the expand beat
      // begins, so the app starts in its normal at-rest state.
      if (current === "voice-morph") {
        useVoiceStateStore.getState().transition("wake");
      } else if (current === "voice-expand") {
        useVoiceStateStore.getState().transition("idle");
      } else if (current === "reveal") {
        void animate(revealRadius, 150, { duration: 0.6, ease: "easeInOut" });
      }

      activeTimeout = setTimeout(() => {
        if (index + 1 < PHASE_ORDER.length) {
          runPhase(index + 1);
        } else {
          onCompleteRef.current();
        }
      }, PHASE_DURATIONS_MS[current]);
    }

    runPhase(0);
    return () => {
      cancelled = true;
      clearTimeout(activeTimeout);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once; onComplete is read via the ref above.
  }, []);

  const phaseIndex = PHASE_ORDER.indexOf(phase);
  const showLogo = phaseIndex >= PHASE_ORDER.indexOf("logo-assemble") && phaseIndex < PHASE_ORDER.indexOf("voice-morph");
  const showVoice = phaseIndex >= PHASE_ORDER.indexOf("voice-morph");

  return (
    <motion.div
      role="presentation"
      className="fixed inset-0 z-100 flex items-center justify-center overflow-hidden bg-black"
      style={{ WebkitMaskImage: maskImage, maskImage }}
    >
      <span className="sr-only" role="status">
        JARVIS is starting up.
      </span>

      {!disableGlassEffects && phaseIndex >= PHASE_ORDER.indexOf("logo-assemble") && (
        <div aria-hidden="true" className="absolute size-64 rounded-full bg-accent/10 blur-3xl" />
      )}

      {/* Energy point */}
      <motion.div
        aria-hidden="true"
        className="absolute size-1.5 rounded-full bg-accent"
        initial={{ opacity: 0, scale: 0 }}
        animate={phaseIndex >= 0 ? { opacity: showLogo || showVoice ? 0 : 1, scale: 1 } : undefined}
        transition={{ duration: 0.4 }}
      />

      {/* Ripple */}
      {phaseIndex === PHASE_ORDER.indexOf("ripple") && (
        <motion.div
          aria-hidden="true"
          className="absolute rounded-full border border-accent"
          initial={{ width: 4, height: 4, opacity: 0.8 }}
          animate={{ width: 240, height: 240, opacity: 0 }}
          transition={{ duration: 0.6, ease: "easeOut" }}
        />
      )}

      {showLogo && <JarvisLogo phase={phase === "logo-pulse" ? "pulsing" : "assembling"} />}

      {showVoice && (
        <motion.div
          initial={{ opacity: 0, scale: 0.55 }}
          animate={{ opacity: 1, scale: phase === "voice-expand" || phase === "reveal" ? 1.2 : 1 }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        >
          <VoiceString />
        </motion.div>
      )}
    </motion.div>
  );
}
