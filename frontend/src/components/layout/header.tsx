import { Bell, Command, LayoutGrid } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { applicationRegistry } from "@/core/application-registry";
import { useCommandPaletteStore } from "@/stores/command-palette.store";
import { useNotificationsStore } from "@/stores/notifications.store";
import { useWorkspaceLayoutStore } from "@/stores/workspace-layout.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

/**
 * Layout component only -- shows the current module's title plus the
 * Command Palette trigger and notification bell. The Search button now
 * opens the real Command Palette (`components/layout/command-palette-
 * layer.tsx`, Phase 3 Task Group G) via `command-palette.store.ts`,
 * the same store the global `Ctrl+K`/`Ctrl+Shift+P` shortcut
 * (`providers/command-palette-provider.tsx`) toggles -- one open/close
 * source of truth, not a second one this button invents.
 *
 * The notification bell got its handler in M8 Phase 3: it opens the
 * Notification Center panel in the workspace and navigates there. That
 * is the whole reason the bell had none before -- there was nowhere for
 * it to go. It opens the panel rather than a popover so there is one
 * Notification Center, in one place, rather than a second rendering of
 * the same list that could scroll and mark-as-read independently.
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
  const openCommandPalette = useCommandPaletteStore((s) => s.open);
  const openPanel = useWorkspaceLayoutStore((s) => s.openPanel);
  const navigate = useNavigate();

  function showPanel(panelId: string) {
    openPanel(panelId);
    navigate("/workspace");
  }

  return (
    <header className="flex h-14 shrink-0 items-center justify-between border-border border-b bg-background px-6">
      <h1 className="text-widget-title font-semibold">{activeModule?.manifest.displayName ?? "JARVIS"}</h1>

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          className="gap-2 text-muted-foreground"
          onClick={openCommandPalette}
        >
          <Command className="size-icon-sm" aria-hidden="true" />
          <span>Search</span>
          <kbd className="rounded border border-border px-1.5 text-caption">Ctrl+K</kbd>
        </Button>

        <Button
          variant="ghost"
          size="icon"
          aria-label="Open workspace"
          onClick={() => navigate("/workspace")}
        >
          <LayoutGrid className="size-icon-md" aria-hidden="true" />
        </Button>

        <Button
          variant="ghost"
          size="icon"
          aria-label="Notifications"
          className="relative"
          onClick={() => showPanel("core.notifications")}
        >
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
