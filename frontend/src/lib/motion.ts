import type { Transition, Variants } from "motion/react";

/**
 * Motion foundation (Task 15). Duration values match `styles/tokens.css`'s
 * `--duration-fast/base/slow` exactly -- one number, two places (a CSS
 * custom property for plain-CSS transitions, this constant for Motion's
 * JS-driven ones) rather than three tiers invented twice. Do not add a
 * fourth tier without updating both files, per ARCHITECTURE.md section 14.
 */
export const MOTION_DURATIONS = {
  fast: 100,
  base: 200,
  slow: 350,
} as const;

export const EASE_STANDARD = [0.4, 0, 0.2, 1] as const;

/** Route/page-level transition -- a subtle fade + rise, not a slide (a
 *  slide reads as "navigating sideways," which doesn't match a
 *  single-window desktop app's mental model). */
export const pageTransitionVariants: Variants = {
  initial: { opacity: 0, y: 8 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
};

export const pageTransition: Transition = {
  duration: MOTION_DURATIONS.base / 1000,
  ease: EASE_STANDARD,
};

/** Generic component enter/exit (dropdowns, popovers, cards appearing). */
export const componentTransitionVariants: Variants = {
  initial: { opacity: 0, scale: 0.98 },
  animate: { opacity: 1, scale: 1 },
  exit: { opacity: 0, scale: 0.98 },
};

export const componentTransition: Transition = {
  duration: MOTION_DURATIONS.fast / 1000,
  ease: EASE_STANDARD,
};

/** Whether the user has requested reduced motion at the OS level --
 *  Motion components should branch on this (or rely on the CSS-level
 *  `prefers-reduced-motion` override in index.css for plain CSS
 *  transitions) rather than always animating. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}
