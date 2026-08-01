import { NavLink } from "react-router-dom";
import { NAV_ITEMS } from "@/routes/nav-items";
import { useDockStore } from "@/stores/dock.store";

/**
 * Layout component only -- renders whichever nav items the user has
 * pinned (stores/dock.store.ts). Starts empty on a fresh install; nothing
 * is pre-pinned, per this phase's "no fake data" rule.
 */
export function Dock() {
  const pinnedItemIds = useDockStore((s) => s.pinnedItemIds);
  const pinnedItems = NAV_ITEMS.filter((item) => pinnedItemIds.includes(item.id));

  if (pinnedItems.length === 0) {
    return null;
  }

  return (
    <div
      aria-label="Pinned shortcuts"
      className="fixed inset-x-0 bottom-14 z-10 flex justify-center"
    >
      <div className="flex items-center gap-1 rounded-xl border border-border bg-card/95 p-1.5 shadow-elevation-medium backdrop-blur">
        {pinnedItems.map((item) => (
          <NavLink
            key={item.id}
            to={item.path}
            aria-label={item.label}
            className="flex size-10 items-center justify-center rounded-lg text-muted-foreground transition-colors duration-fast hover:bg-accent/10 hover:text-accent"
          >
            <item.icon className="size-icon-md" aria-hidden="true" />
          </NavLink>
        ))}
      </div>
    </div>
  );
}
