/**
 * The Workspace Manager (Phase 3, Task Group B) -- the one place a route
 * change becomes a real module lifecycle transition. Resolves the module
 * owning the current path purely from `ApplicationRegistry` (never a
 * hardcoded module list), then drives that module's real `mount()`/
 * `unmount()` (`BaseApplication`, Task 1) through the registry alone --
 * this file never imports a concrete module class. Framework layer, no
 * React import, matching every other `core/` file's own rule; the React
 * Router integration is a separate, thin hook (`hooks/use-workspace-sync.ts`).
 *
 * Flow this file completes: React Router (pathname) -> WorkspaceManager
 * (this file) -> ApplicationRegistry (lookup) -> BaseApplication
 * (mount/unmount) -> DesktopShell (the already-mounted tree the module's
 * navigation contribution registers into).
 */

import { applicationRegistry, type RegisterableApplication } from "@/core/application-registry";
import { useWorkspaceStore } from "@/stores/workspace.store";

function routeMatches(route: string, pathname: string): boolean {
  if (route === "/") return pathname === "/";
  return pathname === route || pathname.startsWith(`${route}/`);
}

export class WorkspaceManager {
  private activeModuleId: string | null = null;

  /** The currently-mounted module's id, or `null` if the current route
   *  doesn't resolve to any registered module. */
  get activeModule(): string | null {
    return this.activeModuleId;
  }

  /** The registered module whose manifest declares a route matching
   *  `pathname` -- resolved by scanning `ApplicationRegistry.getAll()`,
   *  never a hardcoded id/path table. */
  resolveModuleForPath(pathname: string): RegisterableApplication | undefined {
    return applicationRegistry
      .getAll()
      .find((module) => module.manifest.routes.some((route) => routeMatches(route, pathname)));
  }

  /**
   * Call on every route change. Unmounts the previously-active module
   * (if any), mounts the module owning the new path (if one is
   * registered), and is a no-op if the resolved module hasn't actually
   * changed -- prevents a duplicate mount when the same path is reported
   * more than once (e.g. React re-renders for an unrelated reason).
   */
  switchTo(pathname: string): void {
    const nextModule = this.resolveModuleForPath(pathname);
    const nextModuleId = nextModule?.manifest.name ?? null;

    if (nextModuleId === this.activeModuleId) return;

    if (this.activeModuleId) {
      applicationRegistry.get(this.activeModuleId)?.unmount();
    }
    nextModule?.mount();

    this.activeModuleId = nextModuleId;
    useWorkspaceStore.getState().setActiveModuleId(nextModuleId);
  }

  /** Unmounts whatever's currently active without mounting a
   *  replacement -- used when the workspace itself tears down (app
   *  shutdown, test cleanup), not on a normal route change, so no
   *  module is ever left mounted with nothing driving it. */
  unmountActive(): void {
    if (!this.activeModuleId) return;
    applicationRegistry.get(this.activeModuleId)?.unmount();
    this.activeModuleId = null;
    useWorkspaceStore.getState().setActiveModuleId(null);
  }
}

/** One shared instance -- the active workspace is process-wide, matching
 *  `applicationRegistry`'s own singleton pattern. */
export const workspaceManager = new WorkspaceManager();
