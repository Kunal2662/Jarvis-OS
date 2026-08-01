import { Bell, Command } from "lucide-react";
import { useLocation } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { NAV_ITEMS } from "@/routes/nav-items";
import { useNotificationsStore } from "@/stores/notifications.store";

/**
 * Layout component only -- shows the current module's title (derived from
 * the active route, not tracked separately) plus the Command Palette
 * trigger and notification bell. Neither button does anything yet beyond
 * what its own foundation (services/, providers/) already wires -- no
 * module-specific actions live here.
 */
export function Header() {
  const location = useLocation();
  const unreadCount = useNotificationsStore((s) => s.unreadCount());
  const activeItem = NAV_ITEMS.find((item) =>
    item.path === "/" ? location.pathname === "/" : location.pathname.startsWith(item.path),
  );

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-border border-b bg-background px-6">
      <h1 className="text-widget-title font-semibold">{activeItem?.label ?? "JARVIS"}</h1>

      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="gap-2 text-muted-foreground">
          <Command className="size-icon-sm" aria-hidden="true" />
          <span>Search</span>
          <kbd className="rounded border border-border px-1.5 text-caption">Ctrl+K</kbd>
        </Button>

        <Button variant="ghost" size="icon" aria-label="Notifications" className="relative">
          <Bell className="size-icon-md" aria-hidden="true" />
          {unreadCount > 0 && (
            <span
              className="-right-0.5 -top-0.5 absolute flex size-4 items-center justify-center rounded-full bg-destructive text-[10px] text-destructive-foreground"
              aria-hidden="true"
            >
              {unreadCount > 9 ? "9+" : unreadCount}
            </span>
          )}
        </Button>
      </div>
    </header>
  );
}
