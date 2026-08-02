import { useMemo, useSyncExternalStore } from "react";
import { statusBarRegistry, type StatusBarContribution, type StatusBarPosition } from "@/core/interfaces/status-bar-interface";

/** Sorted ascending by `priority` within a `category` -- lower renders
 *  first, matching every other priority-ordered surface's convention. */
function sortByPriority(items: StatusBarContribution[]): StatusBarContribution[] {
  return [...items].sort((a, b) => a.priority - b.priority);
}

/**
 * Layout component, registry-driven (Phase 3, Task Group E) -- renders
 * whatever `statusBarRegistry` (`core/interfaces/status-bar-interface.ts`)
 * has registered, grouped into left/center/right and sorted by
 * priority. No hardcoded status items: Core JARVIS's own 9 built-ins
 * (`status-bar-contributions.tsx`) register through the exact same path
 * a future plugin's own status item would. This component doesn't know
 * -- and doesn't need to know -- which contributions are core and which
 * would eventually come from a plugin.
 *
 * Each contribution renders as its own `<contribution.render />`
 * element (not a value read and interpolated here), so each one
 * subscribes to whatever store or state it needs independently --
 * calling hooks inside this component's own `.map()` would violate
 * React's Rules of Hooks over a variable-length list; this doesn't,
 * because React tracks each rendered component's hooks separately.
 */
export function StatusBar() {
  // Same "re-render on demand" pattern as Sidebar/Dock/module-state-
  // inspector.tsx -- ContributionRegistry.getAll() (core/contribution-registry.ts)
  // returns a referentially-stable array, so this doesn't loop.
  const items = useSyncExternalStore(
    () => () => {},
    () => statusBarRegistry.getAll(),
  );

  const left = useMemo(() => sortByPriority(items.filter((item) => item.category === "left")), [items]);
  const center = useMemo(() => sortByPriority(items.filter((item) => item.category === "center")), [items]);
  const right = useMemo(() => sortByPriority(items.filter((item) => item.category === "right")), [items]);

  return (
    <footer className="flex h-8 shrink-0 items-center justify-between gap-4 border-border border-t bg-card px-4 text-caption text-muted-foreground">
      <StatusBarGroup label="Workspace status" position="left" items={left} />
      <StatusBarGroup label="Task status" position="center" items={center} />
      <StatusBarGroup label="System status" position="right" items={right} />
    </footer>
  );
}

function StatusBarGroup({
  label,
  position,
  items,
}: {
  label: string;
  position: StatusBarPosition;
  items: StatusBarContribution[];
}) {
  return (
    <div
      aria-label={label}
      className={
        position === "center"
          ? "flex flex-1 items-center justify-center gap-4"
          : "flex items-center gap-4"
      }
    >
      {items.map((item) => (
        <span key={item.id} aria-label={item.displayName}>
          <item.render />
        </span>
      ))}
    </div>
  );
}
