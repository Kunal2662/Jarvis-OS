import { useEffect } from "react";
import { CommandPaletteLayer } from "@/components/layout/command-palette-layer";
import { ContextMenuLayer } from "@/components/layout/context-menu-layer";
import { Dock } from "@/components/layout/dock";
import { Header } from "@/components/layout/header";
import { NotificationLayer } from "@/components/layout/notification-layer";
import { Sidebar } from "@/components/layout/sidebar";
import { StatusBar } from "@/components/layout/status-bar";
import { WindowLayer } from "@/components/layout/window-layer";
import { Workspace } from "@/components/layout/workspace";
import { DeveloperPanel } from "@/features/developer/developer-panel";
import { windowService } from "@/services/window/window-service";

/**
 * The root layout every route renders inside (see routes/router.tsx).
 * Owns 8 dedicated regions per MASTER_ROADMAP.md M8 Phase 3: Sidebar,
 * Dock, Workspace, Status Bar, Window Layer, Notification Layer, Context
 * Menu Layer, Command Palette Layer -- so a future task group fills in
 * an already-named slot instead of restructuring this component again.
 * Developer Panel is a ninth, pre-existing region from Phase 1/2, kept
 * as-is; it isn't one of the 8 named regions but has always lived here.
 * Pure composition -- the one piece of real logic (subscribing to native
 * window state) is unchanged from Phase 1. Sidebar/Dock's own internals
 * are untouched in this task group -- they still render from
 * `routes/nav-items.ts`, not the registry (that's a later task group).
 */
export function DesktopShell() {
  useEffect(() => {
    let unsubscribe: (() => void) | undefined;
    windowService.subscribeToWindowState().then((unsub) => {
      unsubscribe = unsub;
    });
    return () => unsubscribe?.();
  }, []);

  return (
    <div className="flex h-svh flex-col overflow-hidden bg-background text-foreground">
      <div className="flex min-h-0 flex-1">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Header />
          <Workspace />
        </div>
      </div>
      <StatusBar />
      <Dock />
      <DeveloperPanel />
      <WindowLayer />
      <NotificationLayer />
      <ContextMenuLayer />
      <CommandPaletteLayer />
    </div>
  );
}
