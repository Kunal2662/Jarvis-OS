/**
 * The Navigation Interface (Task 15) -- formalizes how a module
 * participates in Sidebar, Dock, Command Palette, Search, Deep Linking,
 * and Keyboard Shortcuts, all of which already have real infrastructure
 * from Phase 1 (`routes/nav-items.ts`, `stores/dock.store.ts`,
 * `components/ui/command.tsx`, React Router itself, and the
 * `Ctrl+Shift+D` pattern in `providers/developer-provider.tsx`). This
 * file is the single registration point every module goes through
 * instead of each one reaching into those pieces directly.
 *
 * Deep Linking needs no separate mechanism here: React Router's own
 * URL-based routing (`routes/router.tsx`) already *is* deep linking --
 * every module's route is a real, bookmarkable, shareable URL from the
 * moment it's registered.
 */

export interface CommandPaletteEntry {
  id: string;
  label: string;
  action: () => void;
}

export interface KeyboardShortcut {
  /** e.g. `"ctrl+shift+d"`, matching the pattern already used in
   *  `providers/developer-provider.tsx`. */
  keys: string;
  description: string;
  action: () => void;
}

export interface NavigationContribution {
  moduleId: string;
  /** `true` once this module wants to appear in the Sidebar -- the
   *  actual label/icon/path for the 14 existing nav items still comes
   *  from `routes/nav-items.ts` (unchanged); this flag is for future
   *  modules beyond that fixed set to opt in. */
  sidebarVisible: boolean;
  dockEligible: boolean;
  commandPaletteEntries: CommandPaletteEntry[];
  /** Whether this module's data participates in Universal Search
   *  (M10A) once that exists -- a capability flag only, no search
   *  implementation lives here. */
  searchable: boolean;
  keyboardShortcuts: KeyboardShortcut[];
}

const contributions = new Map<string, NavigationContribution>();
const shortcutListeners = new Map<string, (event: KeyboardEvent) => void>();

function matchesShortcut(event: KeyboardEvent, keys: string): boolean {
  const parts = keys.toLowerCase().split("+");
  const key = parts.at(-1);
  return (
    event.key.toLowerCase() === key &&
    parts.includes("ctrl") === event.ctrlKey &&
    parts.includes("shift") === event.shiftKey &&
    parts.includes("alt") === event.altKey
  );
}

/**
 * Registers a module's navigation surface. Returns an unregister
 * function -- called from `BaseApplication.mount()`/`unmount()` (Task 1)
 * so a module's shortcuts and Command Palette entries only exist while
 * it's actually mounted, never leaking after the user navigates away.
 */
export function registerNavigation(contribution: NavigationContribution): () => void {
  contributions.set(contribution.moduleId, contribution);

  const listener = (event: KeyboardEvent) => {
    for (const shortcut of contribution.keyboardShortcuts) {
      if (matchesShortcut(event, shortcut.keys)) {
        event.preventDefault();
        shortcut.action();
      }
    }
  };
  window.addEventListener("keydown", listener);
  shortcutListeners.set(contribution.moduleId, listener);

  return () => {
    contributions.delete(contribution.moduleId);
    const registeredListener = shortcutListeners.get(contribution.moduleId);
    if (registeredListener) window.removeEventListener("keydown", registeredListener);
    shortcutListeners.delete(contribution.moduleId);
  };
}

export function getAllCommandPaletteEntries(): CommandPaletteEntry[] {
  return [...contributions.values()].flatMap((c) => c.commandPaletteEntries);
}

export function getSearchableModuleIds(): string[] {
  return [...contributions.values()].filter((c) => c.searchable).map((c) => c.moduleId);
}
