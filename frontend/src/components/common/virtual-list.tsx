import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

/**
 * A windowed list -- M8 Phase 3's "Virtual Lists" performance
 * requirement.
 *
 * Hand-rolled rather than pulled from a library: `docs/TECH_STACK.md`
 * fixes this project's dependency set, adding one is an architecture
 * decision this phase has no mandate to make, and the two lists that
 * actually need windowing here (notifications, activity) are flat,
 * uniform-height and append-only -- the case a full virtualiser's
 * variable-size and dynamic-measurement machinery is not needed for.
 *
 * **It degrades to a plain list.** Below `threshold` items every row is
 * rendered, so short lists keep native find-in-page, focus order and
 * scroll-into-view behaviour rather than paying windowing's costs for no
 * benefit. Windowing only engages once the list is long enough for it to
 * matter.
 *
 * Rows must be a uniform `estimatedItemHeight`; a row taller than that
 * would drift out of alignment. Both current callers are fixed-height,
 * and the prop is named for what it is.
 */

interface VirtualListProps<T> {
  items: readonly T[];
  /** Pixel height of one row. Must match what `renderItem` produces. */
  estimatedItemHeight: number;
  renderItem: (item: T, index: number) => ReactNode;
  className?: string;
  /** Rows kept mounted above and below the viewport, so a fast scroll
   *  does not reveal blank space before React catches up. */
  overscan?: number;
  /** Below this many items, render everything. */
  threshold?: number;
}

export function VirtualList<T>({
  items,
  estimatedItemHeight,
  renderItem,
  className,
  overscan = 6,
  threshold = 40,
}: VirtualListProps<T>) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportHeight, setViewportHeight] = useState(0);

  const windowed = items.length >= threshold;

  useEffect(() => {
    const element = containerRef.current;
    if (!element || !windowed) return;

    const measure = () => setViewportHeight(element.clientHeight);
    measure();

    // ResizeObserver rather than a window resize listener: a panel can
    // change height because its *zone* was dragged, which never fires a
    // window resize.
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [windowed]);

  const onScroll = useCallback((event: React.UIEvent<HTMLDivElement>) => {
    setScrollTop(event.currentTarget.scrollTop);
  }, []);

  const { offsetY, visible, totalHeight } = useMemo(() => {
    if (!windowed) {
      return { offsetY: 0, visible: items.map((item, index) => [item, index] as const), totalHeight: 0 };
    }
    const first = Math.max(0, Math.floor(scrollTop / estimatedItemHeight) - overscan);
    const count = Math.ceil(viewportHeight / estimatedItemHeight) + overscan * 2;
    const last = Math.min(items.length, first + count);
    return {
      offsetY: first * estimatedItemHeight,
      visible: items.slice(first, last).map((item, index) => [item, first + index] as const),
      totalHeight: items.length * estimatedItemHeight,
    };
  }, [windowed, items, scrollTop, viewportHeight, estimatedItemHeight, overscan]);

  return (
    <div ref={containerRef} className={`overflow-y-auto ${className ?? ""}`} onScroll={onScroll}>
      {windowed ? (
        // The outer element holds the full scroll height so the
        // scrollbar is honest about how much list there is; the inner
        // one is translated to where the rendered window belongs.
        <div style={{ height: totalHeight, position: "relative" }}>
          <ul style={{ transform: `translateY(${offsetY}px)`, position: "absolute", inset: "0 0 auto 0" }}>
            {visible.map(([item, index]) => renderItem(item, index))}
          </ul>
        </div>
      ) : (
        <ul>{visible.map(([item, index]) => renderItem(item, index))}</ul>
      )}
    </div>
  );
}
