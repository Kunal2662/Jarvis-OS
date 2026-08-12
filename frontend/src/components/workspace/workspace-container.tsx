import { useMemo, useRef } from "react";
import { LayoutGrid } from "lucide-react";
import { DetachedPanelLayer } from "@/components/workspace/detached-panel-layer";
import { PanelSplitter } from "@/components/workspace/panel-splitter";
import { PanelZone } from "@/components/workspace/panel-zone";
import { WorkspaceToolbar } from "@/components/workspace/workspace-toolbar";
import { panelRegistry } from "@/core/panel-registry";
import { useCompactLayout } from "@/hooks/use-responsive-layout";
import {
  MAX_ZONE_FRACTION,
  MIN_ZONE_FRACTION,
  panelsInZone,
  selectActiveWorkspace,
  useWorkspaceLayoutStore,
} from "@/stores/workspace-layout.store";

/**
 * The Universal Workspace Layout -- M8 Phase 3.
 *
 * Four dock zones around a centre: `left` and `right` rails, a `bottom`
 * rail, and `main`. Every zone is optional and collapses out of the
 * layout entirely when it holds no panels, so a workspace with one
 * panel looks like a single-pane app rather than a grid with three empty
 * cells.
 *
 * **Responsive by dropping rails, not by shrinking them.** Below the
 * compact breakpoint the rails would be too narrow to hold anything
 * legible, so `main` takes the full width and rail panels are reachable
 * through the toolbar instead. Squeezing a three-rail desktop layout
 * onto a phone is how a layout ends up technically responsive and
 * practically unusable.
 *
 * Nothing here talks to the backend. Layout is device-local state
 * (`stores/workspace-layout.store.ts` explains why); the panels
 * themselves fetch their own real data.
 */
export function WorkspaceContainer() {
  const containerRef = useRef<HTMLDivElement>(null);
  const rowRef = useRef<HTMLDivElement>(null);

  const workspace = useWorkspaceLayoutStore(selectActiveWorkspace);
  const resizeZone = useWorkspaceLayoutStore((s) => s.resizeZone);
  const compact = useCompactLayout();

  const zones = useMemo(() => {
    const visible = (zone: "left" | "main" | "right" | "bottom") =>
      panelsInZone(workspace, zone).filter((instance) => {
        const contribution = panelRegistry.get(instance.panelId);
        if (!contribution) return false;
        return !(compact && contribution.hideOnCompact);
      });

    return {
      left: compact ? [] : visible("left"),
      main: visible("main"),
      right: compact ? [] : visible("right"),
      bottom: compact ? [] : visible("bottom"),
      detached: panelsInZone(workspace, "detached"),
    };
  }, [workspace, compact]);

  const hasAnyPanel =
    zones.left.length + zones.main.length + zones.right.length + zones.bottom.length > 0;

  return (
    <div ref={containerRef} className="flex min-h-0 flex-1 flex-col">
      <WorkspaceToolbar />

      <div ref={rowRef} className="flex min-h-0 flex-1 gap-0 p-2">
        {zones.left.length > 0 && (
          <>
            <PanelZone
              zone="left"
              panels={zones.left}
              direction="vertical"
              className="shrink-0"
              style={{ width: `${workspace.zoneSizes.left * 100}%` }}
            />
            <PanelSplitter
              orientation="vertical"
              value={workspace.zoneSizes.left}
              min={MIN_ZONE_FRACTION}
              max={MAX_ZONE_FRACTION}
              containerRef={rowRef}
              onChange={(next) => resizeZone("left", next)}
              label="Resize left panels"
            />
          </>
        )}

        <div className="flex min-h-0 min-w-0 flex-1 flex-col">
          {zones.main.length > 0 ? (
            <PanelZone zone="main" panels={zones.main} direction="vertical" className="flex-1" />
          ) : (
            <EmptyWorkspace hasAnyPanel={hasAnyPanel} />
          )}

          {zones.bottom.length > 0 && (
            <>
              <PanelSplitter
                orientation="horizontal"
                value={workspace.zoneSizes.bottom}
                min={MIN_ZONE_FRACTION}
                max={MAX_ZONE_FRACTION}
                containerRef={rowRef}
                inverted
                onChange={(next) => resizeZone("bottom", next)}
                label="Resize bottom panels"
              />
              <PanelZone
                zone="bottom"
                panels={zones.bottom}
                direction="horizontal"
                className="shrink-0"
                style={{ height: `${workspace.zoneSizes.bottom * 100}%` }}
              />
            </>
          )}
        </div>

        {zones.right.length > 0 && (
          <>
            <PanelSplitter
              orientation="vertical"
              value={workspace.zoneSizes.right}
              min={MIN_ZONE_FRACTION}
              max={MAX_ZONE_FRACTION}
              containerRef={rowRef}
              inverted
              onChange={(next) => resizeZone("right", next)}
              label="Resize right panels"
            />
            <PanelZone
              zone="right"
              panels={zones.right}
              direction="vertical"
              className="shrink-0"
              style={{ width: `${workspace.zoneSizes.right * 100}%` }}
            />
          </>
        )}
      </div>

      <DetachedPanelLayer panels={zones.detached} />
    </div>
  );
}

/** Empty state for a workspace whose centre holds nothing. Distinguishes
 *  "you closed everything" from "everything you have is in a rail",
 *  because the useful next action differs. */
function EmptyWorkspace({ hasAnyPanel }: { hasAnyPanel: boolean }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-2 text-center">
      <LayoutGrid className="size-icon-xl text-muted-foreground" aria-hidden="true" />
      <p className="text-card-title font-bold">
        {hasAnyPanel ? "Nothing in the centre" : "Empty workspace"}
      </p>
      <p className="max-w-sm text-secondary text-muted-foreground">
        Add a panel from the toolbar above to start building this workspace.
      </p>
    </div>
  );
}
