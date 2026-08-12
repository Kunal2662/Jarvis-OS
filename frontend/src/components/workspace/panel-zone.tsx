import { Fragment, useRef } from "react";
import { PanelFrame } from "@/components/workspace/panel-frame";
import { PanelSplitter } from "@/components/workspace/panel-splitter";
import { panelRegistry } from "@/core/panel-registry";
import {
  MIN_PANEL_FRACTION,
  useWorkspaceLayoutStore,
  type PanelInstance,
  type PanelPlacement,
} from "@/stores/workspace-layout.store";

/**
 * A stack of panels sharing one dock zone, with a splitter between each
 * adjacent pair.
 *
 * Panels stack along the zone's cross axis: the left and right rails
 * stack vertically (panels above/below each other), the bottom rail
 * stacks horizontally. That is not arbitrary — a rail is narrow in one
 * dimension, so splitting it further in that same dimension produces
 * panels too small to use.
 *
 * A collapsed panel keeps only its title bar and is removed from the
 * flex distribution entirely (`flex: 0 0 auto`), so collapsing one panel
 * genuinely gives its space to the others rather than leaving a gap.
 */

interface PanelZoneProps {
  zone: PanelPlacement;
  panels: PanelInstance[];
  /** Vertical stack (left/right rails) or horizontal (bottom rail). */
  direction: "vertical" | "horizontal";
  className?: string;
  /** The zone's own extent along the shell's axis, set by the container
   *  from the workspace's persisted `zoneSizes`. Inline rather than a
   *  class because it is a continuous, user-dragged value -- there is no
   *  Tailwind class for "20.4% wide". */
  style?: React.CSSProperties;
}

export function PanelZone({ zone, panels, direction, className, style }: PanelZoneProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const resizePanel = useWorkspaceLayoutStore((s) => s.resizePanel);

  if (panels.length === 0) return null;

  const vertical = direction === "vertical";

  return (
    <div
      ref={containerRef}
      data-zone={zone}
      style={style}
      className={`flex min-h-0 min-w-0 gap-0 ${vertical ? "flex-col" : "flex-row"} ${className ?? ""}`}
    >
      {panels.map((instance, index) => {
        const contribution = panelRegistry.get(instance.panelId);
        // A panel whose contribution vanished between releases: skipped
        // rather than rendered as a broken frame. The store's rehydrate
        // already drops these, so this only catches an unregister that
        // happens while mounted.
        if (!contribution) return null;

        const isLast = index === panels.length - 1;

        return (
          <Fragment key={instance.instanceId}>
            <div
              className="flex min-h-0 min-w-0 flex-col"
              style={
                instance.collapsed
                  ? { flex: "0 0 auto" }
                  : { flex: `${instance.size} 1 0%`, minHeight: 0, minWidth: 0 }
              }
            >
              <PanelFrame instance={instance} contribution={contribution} />
            </div>
            {/* Sibling of the panel, not a child: a splitter nested
                inside the flex item it resizes would be laid out along
                the item's own axis and would move with it. */}
            {!isLast && !instance.collapsed && (
              <PanelSplitter
                orientation={vertical ? "horizontal" : "vertical"}
                value={instance.size}
                min={MIN_PANEL_FRACTION}
                max={1 - MIN_PANEL_FRACTION}
                containerRef={containerRef}
                onChange={(next) => resizePanel(instance.instanceId, next)}
                label={`Resize ${contribution.title}`}
              />
            )}
          </Fragment>
        );
      })}
    </div>
  );
}
