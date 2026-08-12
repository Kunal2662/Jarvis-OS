import { useCallback, useRef } from "react";
import { PanelFrame } from "@/components/workspace/panel-frame";
import { panelRegistry } from "@/core/panel-registry";
import { useWorkspaceLayoutStore, type PanelInstance } from "@/stores/workspace-layout.store";

/**
 * Floating panels -- the "Detach" operation of M8 Phase 3's panel
 * system.
 *
 * **In-app floating windows, not OS windows.** A real second OS window
 * needs Tauri's multi-window API, which is `IMPLEMENTATION_ROADMAP.md`
 * §2 Phase 3's separate "Window management (Tauri window APIs)" item and
 * is still open — and an OS window would need its own React root, its
 * own store bridge and its own IPC. Detaching within the viewport is the
 * honest thing this phase can deliver completely, and it keeps the
 * store's `frame` geometry in exactly the shape a future Tauri window
 * would need.
 *
 * Rendered above the docked layout but below the shell's own overlays
 * (command palette, toasts), so detaching a panel can never bury the
 * thing that lets the user undo it.
 */

const MIN_WIDTH = 240;
const MIN_HEIGHT = 160;

function DetachedPanel({ instance }: { instance: PanelInstance }) {
  const moveDetached = useWorkspaceLayoutStore((s) => s.moveDetached);
  const contribution = panelRegistry.get(instance.panelId);

  // Offset between the pointer and the panel's own origin, captured on
  // grab. Without it the panel jumps so its corner meets the pointer.
  const grabOffset = useRef({ x: 0, y: 0 });
  const draggingRef = useRef(false);
  const resizingRef = useRef(false);

  const onDragStart = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!instance.frame) return;
      const target = event.target as HTMLElement;
      // Drag only from the panel's own header, and never from a control
      // inside it -- a pointerdown on Close is a click, not a grab.
      // `PanelFrame` renders that header, so this reuses it rather than
      // stacking a second title bar on top for dragging.
      if (!target.closest("header") || target.closest("button")) return;

      draggingRef.current = true;
      grabOffset.current = {
        x: event.clientX - instance.frame.x,
        y: event.clientY - instance.frame.y,
      };
      event.currentTarget.setPointerCapture(event.pointerId);
    },
    [instance.frame],
  );

  const onResizeStart = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    event.stopPropagation();
    resizingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
  }, []);

  const onPointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!instance.frame) return;
      if (draggingRef.current) {
        moveDetached(instance.instanceId, {
          // Clamped to the viewport so a panel cannot be dragged
          // somewhere it can never be grabbed again.
          x: Math.max(0, Math.min(window.innerWidth - 80, event.clientX - grabOffset.current.x)),
          y: Math.max(0, Math.min(window.innerHeight - 40, event.clientY - grabOffset.current.y)),
        });
      } else if (resizingRef.current) {
        moveDetached(instance.instanceId, {
          width: Math.max(MIN_WIDTH, event.clientX - instance.frame.x),
          height: Math.max(MIN_HEIGHT, event.clientY - instance.frame.y),
        });
      }
    },
    [instance.frame, instance.instanceId, moveDetached],
  );

  const onPointerUp = useCallback((event: React.PointerEvent<HTMLDivElement>) => {
    draggingRef.current = false;
    resizingRef.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
  }, []);

  if (!contribution || !instance.frame) return null;

  return (
    <div
      className="pointer-events-auto absolute flex flex-col rounded-lg shadow-2xl"
      style={{
        left: instance.frame.x,
        top: instance.frame.y,
        width: instance.frame.width,
        height: instance.frame.height,
      }}
      onPointerDown={onDragStart}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerCancel={onPointerUp}
    >
      <div className="flex min-h-0 flex-1 flex-col [&_header]:cursor-grab [&_header]:active:cursor-grabbing">
        <PanelFrame instance={instance} contribution={contribution} />
      </div>
      <div
        role="separator"
        aria-label={`Resize ${contribution.title}`}
        aria-orientation="vertical"
        className="absolute right-0 bottom-0 size-4 cursor-nwse-resize rounded-br-lg bg-border/60"
        onPointerDown={onResizeStart}
      />
    </div>
  );
}

export function DetachedPanelLayer({ panels }: { panels: PanelInstance[] }) {
  if (panels.length === 0) return null;

  return (
    // `pointer-events-none` on the layer, re-enabled per panel: an empty
    // region of this layer must not swallow clicks meant for the docked
    // layout underneath.
    <div className="pointer-events-none fixed inset-0 z-30" aria-label="Detached panels">
      {panels.map((instance) => (
        <DetachedPanel key={instance.instanceId} instance={instance} />
      ))}
    </div>
  );
}
