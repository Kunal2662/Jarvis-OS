import { useMediaQuery } from "@/hooks/use-media-query";

/**
 * The app's responsive breakpoints -- M8 Phase 3's "Responsive Layout".
 *
 * Named, shared constants rather than a raw media-query string at each
 * call site: the Sidebar already collapses at 768px and the workspace
 * must drop its rails at the same width, or the two disagree by a few
 * pixels and the layout visibly stutters mid-resize.
 *
 * Built on `use-media-query.ts` (Phase 3, Task Group C), which already
 * handles the `MediaQueryList`-vs-`resize` reliability problem this
 * would otherwise have to solve again.
 */

/** Tailwind's `md`. Below this, rails are dropped and `main` fills. */
export const COMPACT_MAX_WIDTH = 768;
/** Tailwind's `xl`. Below this, three simultaneous rails are too tight. */
export const WIDE_MIN_WIDTH = 1280;

/** Phone and small-tablet widths: the workspace shows `main` only. */
export function useCompactLayout(): boolean {
  return useMediaQuery(`(max-width: ${COMPACT_MAX_WIDTH - 1}px)`);
}

/** Enough room for left and right rails at once. */
export function useWideLayout(): boolean {
  return useMediaQuery(`(min-width: ${WIDE_MIN_WIDTH}px)`);
}
