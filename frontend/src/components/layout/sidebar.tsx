import { memo, useMemo, useRef, useSyncExternalStore, type KeyboardEvent } from "react";
import { ChevronsLeft, ChevronsRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { applicationRegistry, type RegisterableApplication } from "@/core/application-registry";
import { useMediaQuery } from "@/hooks/use-media-query";
import { resolveIcon } from "@/lib/icon-registry";
import { cn } from "@/lib/utils";
import { useSidebarStore } from "@/stores/sidebar.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

/** Matches Tailwind's default `md` breakpoint (768px) -- below it, the
 *  sidebar auto-collapses regardless of the user's stored preference. */
const COMPACT_VIEWPORT_QUERY = "(max-width: 767px)";

interface SidebarGroup {
  id: string;
  label: string;
  modules: RegisterableApplication[];
}

/** Groups by `ModuleManifest.category` -- an already-existing field, not
 *  an invented taxonomy. Order within each group preserves registration
 *  order (`modules/module-definitions.ts`), not re-sorted. */
function groupModules(modules: RegisterableApplication[]): SidebarGroup[] {
  const local = modules.filter((m) => m.manifest.category === "local");
  const connected = modules.filter((m) => m.manifest.category === "connected");
  const groups: SidebarGroup[] = [];
  if (local.length > 0) groups.push({ id: "workspace", label: "Workspace", modules: local });
  if (connected.length > 0) groups.push({ id: "connected", label: "Connected", modules: connected });
  return groups;
}

/**
 * Layout component, registry-driven (Phase 3, Task Group C) -- renders
 * every module `ApplicationRegistry` (Task 3) actually has registered,
 * grouped by `manifest.category`, with icons resolved from
 * `manifest.icon` (`lib/icon-registry.ts`). No hardcoded module list:
 * `routes/nav-items.ts` is no longer read here at all.
 *
 * Active-item highlighting comes *only* from `WorkspaceManager`'s
 * `activeModuleId` (`stores/workspace.store.ts`), never derived locally
 * from the current route -- `Link` is used for navigation, not `NavLink`,
 * specifically so this component cannot silently fall back to
 * route-derived highlighting.
 *
 * Wrapped in `memo()`: this component takes no props, so the only
 * legitimate reason for it to re-render is its own store subscriptions
 * changing -- memoizing it avoids a wasted re-invocation whenever a
 * sibling (Header, Workspace) re-renders for an unrelated reason.
 */
export const Sidebar = memo(function Sidebar() {
  const isCollapsed = useSidebarStore((s) => s.isCollapsed);
  const toggle = useSidebarStore((s) => s.toggle);
  const activeModuleId = useWorkspaceStore((s) => s.activeModuleId);
  const isCompactViewport = useMediaQuery(COMPACT_VIEWPORT_QUERY);
  const effectiveCollapsed = isCollapsed || isCompactViewport;

  // No registry-level change events exist yet (module list is fixed
  // after app bootstrap) -- same "re-render on demand" pattern as
  // features/developer/module-state-inspector.tsx, now that
  // ApplicationRegistry.getAll() (core/application-registry.ts) returns
  // a referentially-stable array so this doesn't loop.
  const modules = useSyncExternalStore(
    () => () => {},
    () => applicationRegistry.getAll(),
  );
  const groups = useMemo(() => groupModules(modules), [modules]);
  const orderedIds = useMemo(() => groups.flatMap((g) => g.modules.map((m) => m.manifest.name)), [groups]);
  const rovingId =
    activeModuleId && orderedIds.includes(activeModuleId) ? activeModuleId : orderedIds[0];

  const itemRefs = useRef(new Map<string, HTMLAnchorElement>());

  function setItemRef(moduleId: string, el: HTMLAnchorElement | null): void {
    if (el) itemRefs.current.set(moduleId, el);
    else itemRefs.current.delete(moduleId);
  }

  function focusItem(moduleId: string | undefined): void {
    if (!moduleId) return;
    itemRefs.current.get(moduleId)?.focus();
  }

  /** Roving-tabindex keyboard navigation: arrow keys move focus among
   *  items, Home/End jump to the ends, Space activates the focused item
   *  (Enter needs no handling -- native `<a>` already activates on
   *  Enter). Only the roving item has `tabIndex={0}` (below), so Tab
   *  enters/exits the whole widget as one stop while arrows move within
   *  it -- the standard composite-widget keyboard pattern. */
  function handleKeyDown(event: KeyboardEvent<HTMLElement>): void {
    const currentId = (document.activeElement as HTMLElement | null)?.dataset.moduleId;
    const currentIndex = currentId ? orderedIds.indexOf(currentId) : -1;

    switch (event.key) {
      case "ArrowDown":
      case "ArrowRight":
        event.preventDefault();
        focusItem(orderedIds[Math.min(currentIndex + 1, orderedIds.length - 1)]);
        break;
      case "ArrowUp":
      case "ArrowLeft":
        event.preventDefault();
        focusItem(orderedIds[Math.max(currentIndex - 1, 0)]);
        break;
      case "Home":
        event.preventDefault();
        focusItem(orderedIds[0]);
        break;
      case "End":
        event.preventDefault();
        focusItem(orderedIds[orderedIds.length - 1]);
        break;
      case " ":
      case "Spacebar":
        event.preventDefault();
        (document.activeElement as HTMLAnchorElement | null)?.click();
        break;
      default:
        break;
    }
  }

  return (
    <TooltipProvider>
      <aside
        className={cn(
          "flex h-full flex-col border-border border-r bg-card transition-[width] duration-base",
          effectiveCollapsed ? "w-16" : "w-60",
        )}
      >
        <div className="flex items-center gap-2 px-4 py-4">
          <div className="size-icon-lg shrink-0 rounded-md bg-primary" aria-hidden="true" />
          {!effectiveCollapsed && <span className="text-widget-title font-semibold">JARVIS</span>}
        </div>

        <nav
          aria-label="Primary"
          onKeyDown={handleKeyDown}
          className="flex-1 space-y-4 overflow-y-auto px-2"
        >
          {groups.map((group) => (
            <div key={group.id} role="group" aria-labelledby={`sidebar-group-${group.id}`}>
              <p
                id={`sidebar-group-${group.id}`}
                className={cn(
                  "px-3 pb-1 text-caption text-muted-foreground uppercase tracking-wide",
                  effectiveCollapsed && "sr-only",
                )}
              >
                {group.label}
              </p>
              <ul className="space-y-1">
                {group.modules.map((module) => {
                  const moduleId = module.manifest.name;
                  const isActive = moduleId === activeModuleId;
                  const Icon = resolveIcon(module.manifest.icon);
                  const route = module.manifest.routes[0] ?? "/";

                  const link = (
                    <Link
                      ref={(el) => setItemRef(moduleId, el)}
                      data-module-id={moduleId}
                      to={route}
                      aria-current={isActive ? "page" : undefined}
                      tabIndex={moduleId === rovingId ? 0 : -1}
                      className={cn(
                        "flex items-center gap-3 rounded-md px-3 py-2 text-secondary transition-colors duration-fast",
                        "hover:bg-accent/10 hover:text-accent focus-visible:outline-2 focus-visible:outline-ring",
                        isActive ? "bg-accent/15 font-medium text-accent" : "text-muted-foreground",
                      )}
                    >
                      <Icon className="size-icon-md shrink-0" aria-hidden="true" />
                      {!effectiveCollapsed && <span>{module.manifest.displayName}</span>}
                    </Link>
                  );

                  return (
                    <li key={moduleId}>
                      {effectiveCollapsed ? (
                        <Tooltip>
                          <TooltipTrigger asChild>{link}</TooltipTrigger>
                          <TooltipContent side="right">{module.manifest.displayName}</TooltipContent>
                        </Tooltip>
                      ) : (
                        link
                      )}
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>

        <button
          type="button"
          onClick={toggle}
          disabled={isCompactViewport}
          aria-label={effectiveCollapsed ? "Expand sidebar" : "Collapse sidebar"}
          className="m-2 flex items-center justify-center rounded-md p-2 text-muted-foreground hover:bg-accent/10 hover:text-accent focus-visible:outline-2 focus-visible:outline-ring disabled:pointer-events-none disabled:opacity-50"
        >
          {effectiveCollapsed ? (
            <ChevronsRight className="size-icon-sm" aria-hidden="true" />
          ) : (
            <ChevronsLeft className="size-icon-sm" aria-hidden="true" />
          )}
        </button>
      </aside>
    </TooltipProvider>
  );
});
