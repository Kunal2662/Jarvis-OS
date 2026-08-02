import { memo, useMemo, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import { applicationRegistry } from "@/core/application-registry";
import { resolveIcon } from "@/lib/icon-registry";
import { cn } from "@/lib/utils";
import { isModuleEnabled, useModuleEnablementStore } from "@/stores/module-enablement.store";
import { useDockStore } from "@/stores/dock.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

/**
 * Layout component, registry- and enablement-driven (Phase 3, Task
 * Group D) -- renders whichever registered, enabled modules the user
 * has pinned (`stores/dock.store.ts`). Starts empty on a fresh install;
 * nothing is pre-pinned, per this phase's "no fake data" rule. No
 * hardcoded module list: `routes/nav-items.ts` is no longer read here.
 *
 * A module that's pinned but later disabled (Settings -> Plugins)
 * disappears from the Dock too -- pinning doesn't override enablement,
 * it only remembers a preference for *if* the module is shown.
 *
 * Active-item highlighting comes *only* from `WorkspaceManager`'s
 * `activeModuleId` (`stores/workspace.store.ts`), the same single
 * source of truth Sidebar uses -- `Link`, not `NavLink`, for the same
 * reason Sidebar uses it.
 */
export const Dock = memo(function Dock() {
  const pinnedItemIds = useDockStore((s) => s.pinnedItemIds);
  const enabledModuleIds = useModuleEnablementStore((s) => s.enabledModuleIds);
  const activeModuleId = useWorkspaceStore((s) => s.activeModuleId);

  // Same "re-render on demand" pattern as Sidebar/module-state-inspector.tsx
  // -- ApplicationRegistry.getAll() (core/application-registry.ts) returns
  // a referentially-stable array, so this doesn't loop.
  const modules = useSyncExternalStore(
    () => () => {},
    () => applicationRegistry.getAll(),
  );

  const pinnedModules = useMemo(
    () =>
      pinnedItemIds
        .map((id) => modules.find((module) => module.manifest.name === id))
        .filter((module) => module !== undefined)
        .filter((module) => isModuleEnabled(module.manifest.isCore, module.manifest.name, enabledModuleIds)),
    [modules, pinnedItemIds, enabledModuleIds],
  );

  if (pinnedModules.length === 0) {
    return null;
  }

  return (
    <div aria-label="Pinned shortcuts" className="fixed inset-x-0 bottom-14 z-10 flex justify-center">
      <div className="flex items-center gap-1 rounded-xl border border-border bg-card/95 p-1.5 shadow-elevation-medium backdrop-blur">
        {pinnedModules.map((module) => {
          const isActive = module.manifest.name === activeModuleId;
          const Icon = resolveIcon(module.manifest.icon);
          const route = module.manifest.routes[0] ?? "/";

          return (
            <Link
              key={module.manifest.name}
              to={route}
              aria-current={isActive ? "page" : undefined}
              aria-label={module.manifest.displayName}
              className={cn(
                "flex size-10 items-center justify-center rounded-lg text-muted-foreground transition-colors duration-fast",
                "hover:bg-accent/10 hover:text-accent focus-visible:outline-2 focus-visible:outline-ring",
                isActive && "bg-accent/15 text-accent",
              )}
            >
              <Icon className="size-icon-md" aria-hidden="true" />
            </Link>
          );
        })}
      </div>
    </div>
  );
});
