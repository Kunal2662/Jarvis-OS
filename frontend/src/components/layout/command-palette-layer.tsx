import { useMemo, useSyncExternalStore } from "react";
import { useNavigate } from "react-router-dom";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { applicationRegistry } from "@/core/application-registry";
import { getAllCommandPaletteEntries } from "@/core/interfaces/navigation-interface";
import { resolveIcon } from "@/lib/icon-registry";
import { useCommandPaletteStore } from "@/stores/command-palette.store";
import { isModuleEnabled, useModuleEnablementStore } from "@/stores/module-enablement.store";

/**
 * Fills the reserved DesktopShell "Command Palette Layer" region
 * (Phase 3, Task Group G) -- Ctrl+K / Ctrl+Shift+P
 * (`providers/command-palette-provider.tsx`), built on the already-
 * scaffolded `CommandDialog` primitive (`components/ui/command.tsx`,
 * Phase 1) rather than a bespoke overlay.
 *
 * "Navigate" entries come from the same registry+enablement data
 * Sidebar/Dock already read (`ApplicationRegistry` +
 * `ModuleEnablementStore`) -- no separate nav-item list to keep in
 * sync. "Commands" entries come from `getAllCommandPaletteEntries()`
 * (`core/interfaces/navigation-interface.ts`), the real, already-
 * existing per-module command mechanism (M8 Phase 2) -- not a new
 * `ContributionRegistry` instance: one already exists for exactly this
 * purpose (`MASTER_ROADMAP.md`'s Plugin Registration System calls it
 * "already real, not new"), and duplicating it would repeat the
 * "multiple unrelated registries" mistake this project's rules warn
 * against. It renders no "Commands" group today because no module
 * overrides `getNavigationContribution()` yet
 * (`modules/placeholder-module.ts` deliberately doesn't, per its own
 * "no fake business logic" rule) -- honest emptiness, not a missing
 * feature.
 */
export function CommandPaletteLayer() {
  const isOpen = useCommandPaletteStore((s) => s.isOpen);
  const close = useCommandPaletteStore((s) => s.close);
  const navigate = useNavigate();
  const enabledModuleIds = useModuleEnablementStore((s) => s.enabledModuleIds);

  // Same "re-render on demand" pattern as Sidebar/Dock/DashboardGrid --
  // ApplicationRegistry.getAll() returns a referentially-stable array.
  const modules = useSyncExternalStore(
    () => () => {},
    () => applicationRegistry.getAll(),
  );

  const navigableModules = useMemo(
    () => modules.filter((m) => isModuleEnabled(m.manifest.isCore, m.manifest.name, enabledModuleIds)),
    [modules, enabledModuleIds],
  );

  // Not `useSyncExternalStore` -- `getAllCommandPaletteEntries()` builds
  // a fresh array via `flatMap()` on every call, so unlike
  // `ContributionRegistry.getAll()` it isn't referentially stable
  // between calls. Recomputing it during a normal render (triggered by
  // `isOpen`/query changes) is correct and cheap; it just wouldn't
  // reactively update while the palette sits open AND a module mounts
  // in the background with nothing else forcing a re-render here -- an
  // edge case nothing in the app can currently trigger.
  const commandEntries = getAllCommandPaletteEntries();

  return (
    <CommandDialog open={isOpen} onOpenChange={(open) => !open && close()}>
      <CommandInput placeholder="Type a command or search..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Navigate">
          {navigableModules.map((module) => {
            const Icon = resolveIcon(module.manifest.icon);
            return (
              <CommandItem
                key={module.manifest.name}
                value={module.manifest.displayName}
                onSelect={() => {
                  navigate(module.manifest.routes[0] ?? "/");
                  close();
                }}
              >
                <Icon aria-hidden="true" />
                {module.manifest.displayName}
              </CommandItem>
            );
          })}
        </CommandGroup>
        {commandEntries.length > 0 && (
          <CommandGroup heading="Commands">
            {commandEntries.map((entry) => (
              <CommandItem
                key={entry.id}
                value={entry.label}
                onSelect={() => {
                  entry.action();
                  close();
                }}
              >
                {entry.label}
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
