import { Bell, Command } from "lucide-react";
import { Button } from "@/components/ui/button";
import { applicationRegistry } from "@/core/application-registry";
import { useNotificationsStore } from "@/stores/notifications.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

/**
 * Layout component only -- shows the current module's title plus the
 * Command Palette trigger and notification bell. Neither button does
 * anything yet beyond what its own foundation (services/, providers/)
 * already wires -- no module-specific actions live here.
 *
 * Reads the active module from `WorkspaceManager`'s own state
 * (`stores/workspace.store.ts`), the same single source of truth
 * Sidebar uses -- previously this component re-derived "current
 * module" from the route independently, which could in principle
 * disagree with Sidebar's own answer; now there is exactly one place
 * that decision is made.
 */
export function Header() {
  const activeModuleId = useWorkspaceStore((s) => s.activeModuleId);
  const unreadCount = useNotificationsStore((s) => s.unreadCount());
  const activeModule = activeModuleId ? applicationRegistry.get(activeModuleId) : undefined;

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-border border-b bg-background px-6">
      <h1 className="text-widget-title font-semibold">{activeModule?.manifest.displayName ?? "JARVIS"}</h1>

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
