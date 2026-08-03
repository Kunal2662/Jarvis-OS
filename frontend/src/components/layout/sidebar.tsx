import { memo, useCallback, useMemo, useRef, useSyncExternalStore, type KeyboardEvent } from "react";
import { ChevronDown, ChevronRight, ChevronsLeft, ChevronsRight } from "lucide-react";
import { Link } from "react-router-dom";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { applicationRegistry, type RegisterableApplication } from "@/core/application-registry";
import { useGlassEffectsEnabled } from "@/hooks/use-glass-effects";
import { useMediaQuery } from "@/hooks/use-media-query";
import { resolveIcon } from "@/lib/icon-registry";
import { cn } from "@/lib/utils";
import { isModuleEnabled, useModuleEnablementStore } from "@/stores/module-enablement.store";
import { useSidebarStore } from "@/stores/sidebar.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

/** Matches Tailwind's default `md` breakpoint (768px) -- below it, the
 *  sidebar auto-collapses regardless of the user's stored preference. */
const COMPACT_VIEWPORT_QUERY = "(max-width: 767px)";

/** Human label + icon for a synthetic parent group. A module joins a
 *  group purely via its own `manifest.parentGroup` data (UI
 *  Architecture Update, Task Group C revision) -- this table only
 *  needs a new entry when a brand-new *group concept* is introduced,
 *  never when another module joins an existing one. */
const PARENT_GROUPS: Record<string, { label: string; icon: string }> = {
  ai: { label: "AI", icon: "sparkles" },
};

type SidebarNode =
  | { type: "item"; module: RegisterableApplication }
  | { type: "group"; groupId: string; label: string; icon: string; children: RegisterableApplication[] };

/** Builds the render tree from an already-filtered module list -- a
 *  module with `parentGroup` set joins (or creates) its group node at
 *  the position of its first-seen child; everything else preserves
 *  registration order. No hardcoded module list: any future module
 *  declaring an existing `parentGroup` value nests automatically. */
function buildNodes(modules: RegisterableApplication[]): SidebarNode[] {
  const nodes: SidebarNode[] = [];
  const groupNodeIndex = new Map<string, number>();

  for (const module of modules) {
    const groupId = module.manifest.parentGroup;
    if (!groupId) {
      nodes.push({ type: "item", module });
      continue;
    }
    const existingIndex = groupNodeIndex.get(groupId);
    if (existingIndex !== undefined) {
      const node = nodes[existingIndex];
      if (node.type === "group") node.children.push(module);
      continue;
    }
    const meta = PARENT_GROUPS[groupId] ?? { label: groupId, icon: "help-circle" };
    groupNodeIndex.set(groupId, nodes.length);
    nodes.push({ type: "group", groupId, label: meta.label, icon: meta.icon, children: [module] });
  }

  return nodes;
}

interface FocusableEntry {
  id: string;
  kind: "item" | "group";
  module?: RegisterableApplication;
  groupId?: string;
  label: string;
  icon: string;
}

/** The keyboard-navigable, currently-*visible* order -- a collapsed
 *  group contributes only its own header entry, not its hidden
 *  children, so ArrowDown/Up never lands on something the user can't
 *  see. */
function flattenVisible(nodes: SidebarNode[], isGroupExpanded: (groupId: string) => boolean): FocusableEntry[] {
  const entries: FocusableEntry[] = [];
  for (const node of nodes) {
    if (node.type === "item") {
      entries.push({
        id: node.module.manifest.name,
        kind: "item",
        module: node.module,
        label: node.module.manifest.displayName,
        icon: node.module.manifest.icon,
      });
      continue;
    }
    entries.push({ id: `group:${node.groupId}`, kind: "group", groupId: node.groupId, label: node.label, icon: node.icon });
    if (isGroupExpanded(node.groupId)) {
      for (const child of node.children) {
        entries.push({
          id: child.manifest.name,
          kind: "item",
          module: child,
          label: child.manifest.displayName,
          icon: child.manifest.icon,
        });
      }
    }
  }
  return entries;
}

/** Every leaf module in a node list, ignoring group boundaries --
 *  what collapsed (icon-only) sidebar mode renders: every real
 *  destination gets its own icon, since there's no visual room for a
 *  nested group distinction at that width. */
function flattenLeaves(nodes: SidebarNode[]): RegisterableApplication[] {
  return nodes.flatMap((node) => (node.type === "item" ? [node.module] : node.children));
}

/**
 * Layout component, registry- and enablement-driven (Phase 3, Dynamic
 * Sidebar revision) -- renders only modules that are both *registered*
 * (`ApplicationRegistry`) and *enabled* (`ModuleEnablementStore`). A
 * fixed core set (`manifest.isCore`) always renders; every other
 * module renders only once the user has enabled it. Modules sharing a
 * `manifest.parentGroup` nest under a synthesized, expandable parent
 * (e.g. "AI"). No hardcoded module list anywhere in this file.
 *
 * Active-item highlighting comes *only* from `WorkspaceManager`'s
 * `activeModuleId` (`stores/workspace.store.ts`), never derived
 * locally from the current route -- `Link` is used for navigation, not
 * `NavLink`, specifically so this component cannot silently fall back
 * to route-derived highlighting.
 */
export const Sidebar = memo(function Sidebar() {
  const isCollapsed = useSidebarStore((s) => s.isCollapsed);
  const toggle = useSidebarStore((s) => s.toggle);
  const expandedGroupIds = useSidebarStore((s) => s.expandedGroupIds);
  const toggleGroup = useSidebarStore((s) => s.toggleGroup);
  const enabledModuleIds = useModuleEnablementStore((s) => s.enabledModuleIds);
  const activeModuleId = useWorkspaceStore((s) => s.activeModuleId);
  const isCompactViewport = useMediaQuery(COMPACT_VIEWPORT_QUERY);
  const effectiveCollapsed = isCollapsed || isCompactViewport;
  const glassEffectsEnabled = useGlassEffectsEnabled();

  // Same "re-render on demand" pattern as module-state-inspector.tsx --
  // ApplicationRegistry.getAll() (core/application-registry.ts)
  // returns a referentially-stable array, so this doesn't loop.
  const modules = useSyncExternalStore(
    () => () => {},
    () => applicationRegistry.getAll(),
  );

  const coreModules = useMemo(() => modules.filter((m) => m.manifest.isCore), [modules]);
  const installedModules = useMemo(
    () => modules.filter((m) => !m.manifest.isCore && isModuleEnabled(false, m.manifest.name, enabledModuleIds)),
    [modules, enabledModuleIds],
  );

  const coreNodes = useMemo(() => buildNodes(coreModules), [coreModules]);
  const installedNodes = useMemo(() => buildNodes(installedModules), [installedModules]);

  const isGroupExpanded = useCallback(
    (groupId: string): boolean => {
      if (expandedGroupIds.includes(groupId)) return true;
      // A group containing the active module is always visible,
      // regardless of the user's persisted collapse preference --
      // navigating there (e.g. via Command Palette) should never hide it.
      const node = [...coreNodes, ...installedNodes].find((n) => n.type === "group" && n.groupId === groupId);
      return node?.type === "group" && node.children.some((c) => c.manifest.name === activeModuleId);
    },
    [expandedGroupIds, activeModuleId, coreNodes, installedNodes],
  );

  const visibleCoreEntries = useMemo(() => flattenVisible(coreNodes, isGroupExpanded), [coreNodes, isGroupExpanded]);
  const visibleInstalledEntries = useMemo(
    () => flattenVisible(installedNodes, isGroupExpanded),
    [installedNodes, isGroupExpanded],
  );
  const orderedIds = useMemo(
    () => [...visibleCoreEntries, ...visibleInstalledEntries].map((e) => e.id),
    [visibleCoreEntries, visibleInstalledEntries],
  );
  const rovingId = activeModuleId && orderedIds.includes(activeModuleId) ? activeModuleId : orderedIds[0];

  const itemRefs = useRef(new Map<string, HTMLElement>());

  function setItemRef(id: string, el: HTMLElement | null): void {
    if (el) itemRefs.current.set(id, el);
    else itemRefs.current.delete(id);
  }

  function focusEntry(id: string | undefined): void {
    if (!id) return;
    itemRefs.current.get(id)?.focus();
  }

  /** Roving-tabindex keyboard navigation over the currently *visible*
   *  entries (collapsed groups' hidden children are skipped, per
   *  `flattenVisible`). Space activates the focused entry -- a link
   *  navigates (native `<a>` already does this on Enter), a group
   *  header toggles expand/collapse. */
  function handleKeyDown(event: KeyboardEvent<HTMLElement>): void {
    const currentId = (document.activeElement as HTMLElement | null)?.dataset.entryId;
    const currentIndex = currentId ? orderedIds.indexOf(currentId) : -1;

    switch (event.key) {
      case "ArrowDown":
      case "ArrowRight":
        event.preventDefault();
        focusEntry(orderedIds[Math.min(currentIndex + 1, orderedIds.length - 1)]);
        break;
      case "ArrowUp":
      case "ArrowLeft":
        event.preventDefault();
        focusEntry(orderedIds[Math.max(currentIndex - 1, 0)]);
        break;
      case "Home":
        event.preventDefault();
        focusEntry(orderedIds[0]);
        break;
      case "End":
        event.preventDefault();
        focusEntry(orderedIds[orderedIds.length - 1]);
        break;
      case " ":
      case "Spacebar":
        event.preventDefault();
        (document.activeElement as HTMLElement | null)?.click();
        break;
      default:
        break;
    }
  }

  function renderLink(module: RegisterableApplication, indented: boolean) {
    const moduleId = module.manifest.name;
    const isActive = moduleId === activeModuleId;
    const Icon = resolveIcon(module.manifest.icon);
    const route = module.manifest.routes[0] ?? "/";

    const link = (
      <Link
        ref={(el) => setItemRef(moduleId, el)}
        data-entry-id={moduleId}
        to={route}
        aria-current={isActive ? "page" : undefined}
        aria-label={module.manifest.displayName}
        tabIndex={moduleId === rovingId ? 0 : -1}
        className={cn(
          "flex items-center gap-3 rounded-md px-3 py-2 text-secondary transition-colors duration-fast",
          "hover:bg-accent/10 hover:text-accent focus-visible:outline-2 focus-visible:outline-ring",
          isActive ? "bg-accent/15 font-medium text-accent" : "text-muted-foreground",
          indented && !effectiveCollapsed && "ml-4",
        )}
      >
        <Icon className="size-icon-md shrink-0" aria-hidden="true" />
        {!effectiveCollapsed && <span>{module.manifest.displayName}</span>}
      </Link>
    );

    if (!effectiveCollapsed) return link;
    return (
      <Tooltip>
        <TooltipTrigger asChild>{link}</TooltipTrigger>
        <TooltipContent side="right">{module.manifest.displayName}</TooltipContent>
      </Tooltip>
    );
  }

  function renderGroupHeader(node: Extract<SidebarNode, { type: "group" }>) {
    const expanded = isGroupExpanded(node.groupId);
    const Icon = resolveIcon(node.icon);
    const Chevron = expanded ? ChevronDown : ChevronRight;

    return (
      <button
        ref={(el) => setItemRef(`group:${node.groupId}`, el)}
        type="button"
        data-entry-id={`group:${node.groupId}`}
        onClick={() => toggleGroup(node.groupId)}
        aria-expanded={expanded}
        tabIndex={`group:${node.groupId}` === rovingId ? 0 : -1}
        className={cn(
          "flex w-full items-center gap-3 rounded-md px-3 py-2 text-secondary transition-colors duration-fast",
          "hover:bg-accent/10 hover:text-accent focus-visible:outline-2 focus-visible:outline-ring text-muted-foreground",
        )}
      >
        <Icon className="size-icon-md shrink-0" aria-hidden="true" />
        {!effectiveCollapsed && (
          <>
            <span className="flex-1 text-left">{node.label}</span>
            <Chevron className="size-icon-sm shrink-0" aria-hidden="true" />
          </>
        )}
      </button>
    );
  }

  function renderNodes(nodes: SidebarNode[]) {
    if (effectiveCollapsed) {
      // Collapsed sidebar: every leaf gets its own icon; group
      // structure has no room to render at this width.
      return flattenLeaves(nodes).map((module) => <li key={module.manifest.name}>{renderLink(module, false)}</li>);
    }
    return nodes.map((node) => {
      if (node.type === "item") {
        return <li key={node.module.manifest.name}>{renderLink(node.module, false)}</li>;
      }
      const expanded = isGroupExpanded(node.groupId);
      return (
        <li key={node.groupId}>
          {renderGroupHeader(node)}
          {expanded && (
            <ul className="mt-1 space-y-1">
              {node.children.map((child) => (
                <li key={child.manifest.name}>{renderLink(child, true)}</li>
              ))}
            </ul>
          )}
        </li>
      );
    });
  }

  return (
    <TooltipProvider>
      <aside
        className={cn(
          "flex h-full flex-col border-border border-r transition-[width] duration-base",
          glassEffectsEnabled ? "bg-card/70 backdrop-blur-xl" : "bg-card",
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
          <ul className="space-y-1">{renderNodes(coreNodes)}</ul>

          {installedNodes.length > 0 && (
            <div role="group" aria-labelledby="sidebar-group-installed">
              <p
                id="sidebar-group-installed"
                className={cn(
                  "px-3 pb-1 text-caption text-muted-foreground uppercase tracking-wide",
                  effectiveCollapsed && "sr-only",
                )}
              >
                Installed Modules
              </p>
              <ul className="space-y-1">{renderNodes(installedNodes)}</ul>
            </div>
          )}
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
