import { memo, Suspense } from "react";
import {
  ChevronDown,
  ChevronRight,
  PictureInPicture2,
  PanelBottom,
  PanelLeft,
  PanelRight,
  Square,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingState } from "@/components/common/loading-spinner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { PanelContribution } from "@/core/panel-registry";
import {
  useWorkspaceLayoutStore,
  type PanelInstance,
  type PanelPlacement,
} from "@/stores/workspace-layout.store";

/**
 * One panel's chrome -- title bar plus the seven operations every panel
 * supports (M8 Phase 3's Panel System): open, close, resize, collapse,
 * detach, move, restore.
 *
 * "Open" is the panel menu's job (`workspace-toolbar.tsx`) and "resize"
 * is the splitter's (`panel-splitter.tsx`); this component owns the
 * other five, because they are per-panel and belong on the panel.
 *
 * `memo`'d deliberately: a workspace re-renders on any layout change,
 * and a panel whose own instance did not change should not re-render its
 * (potentially expensive, lazily-loaded) content. This is M8 Phase 3's
 * "Component Memoization" requirement applied where it actually pays —
 * memoising a leaf button would be noise.
 *
 * The content is wrapped in `<Suspense>` because every registered panel
 * is a `React.lazy` import; the fallback is the same `LoadingState` the
 * router uses, so a panel loading and a route loading look identical.
 */

const MOVE_TARGETS: Array<{ placement: PanelPlacement; label: string; icon: typeof PanelLeft }> = [
  { placement: "left", label: "Move to left", icon: PanelLeft },
  { placement: "main", label: "Move to centre", icon: Square },
  { placement: "right", label: "Move to right", icon: PanelRight },
  { placement: "bottom", label: "Move to bottom", icon: PanelBottom },
];

interface PanelFrameProps {
  instance: PanelInstance;
  contribution: PanelContribution;
}

function PanelFrameImpl({ instance, contribution }: PanelFrameProps) {
  const closePanel = useWorkspaceLayoutStore((s) => s.closePanel);
  const toggleCollapsed = useWorkspaceLayoutStore((s) => s.toggleCollapsed);
  const movePanel = useWorkspaceLayoutStore((s) => s.movePanel);
  const detachPanel = useWorkspaceLayoutStore((s) => s.detachPanel);
  const restorePanel = useWorkspaceLayoutStore((s) => s.restorePanel);

  const detached = instance.placement === "detached";
  const Content = contribution.render;

  return (
    <section
      className="flex min-h-0 min-w-0 flex-col overflow-hidden rounded-lg border border-border/60 bg-card"
      aria-label={contribution.title}
      data-panel-id={contribution.id}
      data-placement={instance.placement}
    >
      <header className="flex shrink-0 items-center gap-1 border-border/60 border-b bg-muted/30 px-1.5 py-1">
        {!detached && (
          <Button
            variant="ghost"
            size="icon"
            className="size-6"
            aria-label={instance.collapsed ? `Expand ${contribution.title}` : `Collapse ${contribution.title}`}
            aria-expanded={!instance.collapsed}
            onClick={() => toggleCollapsed(instance.instanceId)}
          >
            {instance.collapsed ? (
              <ChevronRight className="size-3.5" aria-hidden="true" />
            ) : (
              <ChevronDown className="size-3.5" aria-hidden="true" />
            )}
          </Button>
        )}

        <h2 className="min-w-0 flex-1 truncate font-medium text-xs">{contribution.title}</h2>

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="size-6"
              aria-label={`${contribution.title} panel options`}
            >
              <PictureInPicture2 className="size-3.5" aria-hidden="true" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            {detached ? (
              <DropdownMenuItem onSelect={() => restorePanel(instance.instanceId)}>
                <Square className="size-3.5" aria-hidden="true" />
                Restore to layout
              </DropdownMenuItem>
            ) : (
              <>
                {MOVE_TARGETS.filter((target) => target.placement !== instance.placement).map(
                  (target) => (
                    <DropdownMenuItem
                      key={target.placement}
                      onSelect={() => movePanel(instance.instanceId, target.placement)}
                    >
                      <target.icon className="size-3.5" aria-hidden="true" />
                      {target.label}
                    </DropdownMenuItem>
                  ),
                )}
                <DropdownMenuSeparator />
                <DropdownMenuItem onSelect={() => detachPanel(instance.instanceId)}>
                  <PictureInPicture2 className="size-3.5" aria-hidden="true" />
                  Detach
                </DropdownMenuItem>
              </>
            )}
          </DropdownMenuContent>
        </DropdownMenu>

        {!contribution.permanent && (
          <Button
            variant="ghost"
            size="icon"
            className="size-6"
            aria-label={`Close ${contribution.title}`}
            onClick={() => closePanel(instance.instanceId)}
          >
            <X className="size-3.5" aria-hidden="true" />
          </Button>
        )}
      </header>

      {!instance.collapsed && (
        <div className="min-h-0 flex-1 overflow-auto">
          <Suspense fallback={<LoadingState label={`Loading ${contribution.title}`} />}>
            <Content />
          </Suspense>
        </div>
      )}
    </section>
  );
}

export const PanelFrame = memo(PanelFrameImpl);
