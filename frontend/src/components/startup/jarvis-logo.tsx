import { motion } from "motion/react";
import { cn } from "@/lib/utils";

export type JarvisLogoPhase = "hidden" | "assembling" | "pulsing";

/**
 * The JARVIS OS brand mark, animated for the startup sequence's
 * "logo assembles from light" / "logo emits an energy pulse" beats
 * (Phase 4, Task Group I) -- recreated as SVG paths (M22 Task Group E)
 * from the approved master logo (`src-tauri/icons/master-logo.png`): a
 * vertical center blade flanked by two hook-shaped "side blades" with a
 * glowing inner channel. The same geometry `src-tauri/icons/small-icon-
 * source.svg` uses for the taskbar/tray icon variant, so the startup
 * mark and the icon the user sees in Explorer are visibly the same
 * identity, not two different logos that happen to share a name.
 *
 * **Phase API is unchanged from the previous design.** `startup-
 * sequence.tsx` owns an already-choreographed ~4.2s, 8-phase sequence
 * (`point` -> `ripple` -> `logo-assemble` -> `logo-pulse` -> `voice-
 * morph` -> ...) and mounts this component for exactly two of those
 * phases, ~1.3s total. Widening this component's own phase model would
 * mean changing that separate, already-tuned choreography too -- out of
 * scope for a branding task group and not something this file's own
 * animation richness needs. Everything the brief asked for (the ring
 * drawing, the outer ring fading in, the blade rising, the side blades
 * sliding, the glow igniting, the pulse travelling, the breathing glow)
 * happens *within* the existing `assembling`/`pulsing` window via
 * staggered, overlapping animations, timed to that window rather than
 * inventing a longer one.
 *
 * **Every animated property is `opacity`, `scale`, a `transform`
 * translate, or SVG `pathLength`** -- never a layout-triggering
 * property (width/height/top/left) -- so this composites on the GPU
 * without forcing layout, the brief's own "60 FPS, GPU accelerated, no
 * layout shifts" requirement satisfied by which properties are touched,
 * not asserted separately.
 */
export function JarvisLogo({ phase, className }: { phase: JarvisLogoPhase; className?: string }) {
  const visible = phase !== "hidden";
  const assembling = phase === "assembling";
  const pulsing = phase === "pulsing";

  return (
    <svg viewBox="0 0 128 128" className={cn("size-24", className)} aria-hidden="true">
      {/* Side blades -- outer dark stroke first (beat 3: "metallic
          outer ring fades into view"), inner cyan channel drawn on top
          (beat 2: "cyan energy ring begins drawing"). Both slide
          upward together once drawn (beat 5), inside a `motion.g` so
          the translate is one GPU-composited transform per side rather
          than per path. */}
      {(["left", "right"] as const).map((side) => {
        const mirror = side === "right";
        const outerPath = mirror ? "M79,18 Q118,64 81,96" : "M49,18 Q10,64 47,96";
        const innerPath = mirror ? "M77,25 Q106,64 79,90" : "M51,25 Q22,64 49,90";

        return (
          // Owns only the shared upward slide (beat 5) -- opacity is
          // each child path's own, driven by its `pathLength` draw-on.
          // A group-level opacity here would multiply against the
          // children's, compounding two independent fades into a
          // slower, muddier one instead of the single clean fade each
          // path already animates.
          <motion.g
            key={side}
            initial={{ y: 0 }}
            animate={!visible ? { y: 0 } : assembling ? { y: [10, 0] } : { y: 0 }}
            transition={assembling ? { duration: 0.5, delay: 0.35, ease: "easeOut" } : { duration: 0.3 }}
          >
            <motion.path
              d={outerPath}
              fill="none"
              stroke="#1b222c"
              strokeWidth={11}
              strokeLinecap="round"
              className="dark:stroke-[#e2e8f0]"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={
                !visible
                  ? { pathLength: 0, opacity: 0 }
                  : { pathLength: 1, opacity: 1 }
              }
              transition={{ duration: 0.5, delay: assembling ? 0.15 : 0, ease: "easeInOut" }}
            />
            <motion.path
              d={innerPath}
              fill="none"
              stroke="currentColor"
              strokeWidth={5}
              strokeLinecap="round"
              className="text-accent"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={!visible ? { pathLength: 0, opacity: 0 } : { pathLength: 1, opacity: 1 }}
              transition={{ duration: 0.45, ease: "easeInOut" }}
            />
          </motion.g>
        );
      })}

      {/* Center blade -- rises from below (beat 4), arriving as the
          side blades finish their own motion so the mark reads as one
          assembled whole rather than three independent pieces. */}
      <motion.path
        d="M64,10 L72,58 L72,104 L64,120 L56,104 L56,58 Z"
        fill="#f2f5f8"
        stroke="#1b222c"
        strokeWidth={1.5}
        className="dark:fill-[#f8fafc] dark:stroke-[#94a3b8]"
        initial={{ y: 24, opacity: 0 }}
        animate={
          !visible
            ? { y: 24, opacity: 0 }
            : assembling
              ? { y: [24, 0], opacity: 1 }
              : { y: 0, opacity: 1 }
        }
        transition={
          assembling
            ? { duration: 0.45, delay: 0.4, ease: "easeOut" }
            : { duration: 0.2 }
        }
      />

      {/* Glow ignition (beat 6) -- a soft blurred halo behind the mark,
          faded in last so it reads as energy the assembled shape
          switches on, not a background element that was always there. */}
      <motion.circle
        cx={64}
        cy={64}
        r={30}
        fill="currentColor"
        className="text-accent"
        style={{ filter: "blur(14px)" }}
        initial={{ opacity: 0 }}
        animate={!visible ? { opacity: 0 } : assembling ? { opacity: [0, 0.35] } : { opacity: 0.3 }}
        transition={assembling ? { duration: 0.4, delay: 0.55 } : { duration: 0.3 }}
      />

      {/* Pulse burst (beat 7) -- an expanding, fading ring, only during
          the pulsing phase. */}
      {pulsing && (
        <motion.circle
          cx={64}
          cy={64}
          r={20}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          className="text-accent"
          initial={{ scale: 1, opacity: 0.8 }}
          animate={{ scale: 3.4, opacity: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
        />
      )}

      {/* Breathing glow (beat 8) -- one slow, soft cycle rather than a
          longer loop: the phase this lives in is ~400ms, and animating
          a rhythm that visibly cuts off mid-breath would look broken.
          One gentle inhale reads as "alive" without promising a loop
          the mount window cannot deliver. */}
      {pulsing && (
        <motion.g
          initial={{ opacity: 1 }}
          animate={{ opacity: [1, 0.85, 1] }}
          transition={{ duration: 0.4, ease: "easeInOut" }}
        >
          <circle cx={64} cy={64} r={4} fill="currentColor" className="text-accent" />
        </motion.g>
      )}
    </svg>
  );
}
