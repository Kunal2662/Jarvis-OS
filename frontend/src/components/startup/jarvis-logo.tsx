import { motion } from "motion/react";
import { cn } from "@/lib/utils";

export type JarvisLogoPhase = "hidden" | "assembling" | "pulsing";

/**
 * An original abstract emblem for the startup sequence's "logo
 * assembles from light" / "logo emits an energy pulse" beats (Phase 4,
 * Task Group I) -- a hexagonal ring "drawn" via an animated
 * `pathLength` plus a center point, not a static image. Deliberately
 * not a reused/derived version of any reference material; JARVIS has
 * no existing logo asset in this codebase to reuse instead.
 */
export function JarvisLogo({ phase, className }: { phase: JarvisLogoPhase; className?: string }) {
  const visible = phase !== "hidden";

  return (
    <svg viewBox="0 0 120 120" className={cn("size-24 text-accent", className)} aria-hidden="true">
      <motion.circle
        cx={60}
        cy={60}
        r={6}
        fill="currentColor"
        initial={{ scale: 0, opacity: 0 }}
        animate={
          !visible
            ? { scale: 0, opacity: 0 }
            : phase === "pulsing"
              ? { scale: [1, 1.6, 1], opacity: 1 }
              : { scale: 1, opacity: 1 }
        }
        transition={phase === "pulsing" ? { duration: 0.6, ease: "easeOut" } : { duration: 0.5 }}
      />
      <motion.path
        d="M60 12 L100 36 L100 84 L60 108 L20 84 L20 36 Z"
        fill="none"
        stroke="currentColor"
        strokeWidth={2}
        strokeLinecap="round"
        strokeLinejoin="round"
        initial={{ pathLength: 0, opacity: 0 }}
        animate={visible ? { pathLength: 1, opacity: 0.9 } : { pathLength: 0, opacity: 0 }}
        transition={{ duration: 1.1, ease: "easeInOut" }}
      />
      {phase === "pulsing" && (
        <motion.circle
          cx={60}
          cy={60}
          r={10}
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          initial={{ scale: 1, opacity: 0.8 }}
          animate={{ scale: 6, opacity: 0 }}
          transition={{ duration: 0.7, ease: "easeOut" }}
        />
      )}
    </svg>
  );
}
