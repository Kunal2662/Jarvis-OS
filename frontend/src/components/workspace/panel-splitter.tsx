import { useCallback, useEffect, useRef } from "react";

/**
 * A draggable divider -- the "Resizable Panels" half of M8 Phase 3's
 * panel system.
 *
 * Pointer events rather than mouse events, so a trackpad, a pen and a
 * touchscreen all work from one code path; `setPointerCapture` keeps the
 * drag alive when the pointer leaves the 4px handle, which it does
 * immediately on any real drag.
 *
 * **Keyboard-operable, not just draggable.** A splitter that can only be
 * dragged makes the entire layout unreachable without a pointer. Arrow
 * keys nudge, Home/End jump to the extremes, matching the WAI-ARIA
 * `separator` pattern this element declares.
 *
 * It reports a *fraction*, not pixels: the store persists fractions so a
 * layout saved on one display restores sensibly on another.
 */

interface PanelSplitterProps {
  orientation: "vertical" | "horizontal";
  /** Current position, 0–1. */
  value: number;
  onChange: (value: number) => void;
  min: number;
  max: number;
  /** The element the fraction is measured against — the zone's container. */
  containerRef: React.RefObject<HTMLElement | null>;
  /** `true` when growing the panel means *decreasing* the pointer
   *  coordinate — a right-hand zone whose width grows as the pointer
   *  moves left. */
  inverted?: boolean;
  label: string;
}

const KEYBOARD_STEP = 0.02;

export function PanelSplitter({
  orientation,
  value,
  onChange,
  min,
  max,
  containerRef,
  inverted = false,
  label,
}: PanelSplitterProps) {
  const draggingRef = useRef(false);

  const clamp = useCallback((next: number) => Math.min(max, Math.max(min, next)), [min, max]);

  const fractionFromEvent = useCallback(
    (clientX: number, clientY: number): number | null => {
      const container = containerRef.current;
      if (!container) return null;
      const rect = container.getBoundingClientRect();

      if (orientation === "vertical") {
        if (rect.width === 0) return null;
        const raw = (clientX - rect.left) / rect.width;
        return clamp(inverted ? 1 - raw : raw);
      }
      if (rect.height === 0) return null;
      const raw = (clientY - rect.top) / rect.height;
      return clamp(inverted ? 1 - raw : raw);
    },
    [containerRef, orientation, inverted, clamp],
  );

  const onPointerDown = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    draggingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!draggingRef.current) return;
      const next = fractionFromEvent(event.clientX, event.clientY);
      if (next !== null) onChange(next);
    },
    [fractionFromEvent, onChange],
  );

  const endDrag = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    draggingRef.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  const onKeyDown = useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      const grow = orientation === "vertical" ? "ArrowRight" : "ArrowDown";
      const shrink = orientation === "vertical" ? "ArrowLeft" : "ArrowUp";
      const direction = inverted ? -1 : 1;

      if (event.key === grow) onChange(clamp(value + KEYBOARD_STEP * direction));
      else if (event.key === shrink) onChange(clamp(value - KEYBOARD_STEP * direction));
      else if (event.key === "Home") onChange(min);
      else if (event.key === "End") onChange(max);
      else return;

      event.preventDefault();
    },
    [orientation, inverted, value, onChange, clamp, min, max],
  );

  // A drag that ends outside the window never fires pointerup on the
  // handle; without this the splitter stays "held" and follows the
  // pointer on the next unrelated move.
  useEffect(() => {
    const cancel = () => {
      draggingRef.current = false;
    };
    window.addEventListener("blur", cancel);
    return () => window.removeEventListener("blur", cancel);
  }, []);

  const vertical = orientation === "vertical";

  return (
    <div
      role="separator"
      aria-orientation={vertical ? "vertical" : "horizontal"}
      aria-label={label}
      aria-valuenow={Math.round(value * 100)}
      aria-valuemin={Math.round(min * 100)}
      aria-valuemax={Math.round(max * 100)}
      tabIndex={0}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onKeyDown={onKeyDown}
      className={
        vertical
          ? "group relative w-1 shrink-0 cursor-col-resize outline-none"
          : "group relative h-1 shrink-0 cursor-row-resize outline-none"
      }
    >
      {/* The visible hairline is 1px but the hit area is the whole
          element plus this padded overlay -- a 1px drag target is a
          usability failure on any display. */}
      <span
        aria-hidden="true"
        className={
          vertical
            ? "-inset-x-1 absolute inset-y-0 transition-colors group-hover:bg-primary/30 group-focus-visible:bg-primary/50"
            : "-inset-y-1 absolute inset-x-0 transition-colors group-hover:bg-primary/30 group-focus-visible:bg-primary/50"
        }
      />
      <span aria-hidden="true" className="absolute inset-0 bg-border/60" />
    </div>
  );
}
