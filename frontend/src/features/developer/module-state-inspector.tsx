import { useSyncExternalStore } from "react";
import { Inbox } from "lucide-react";
import { applicationRegistry } from "@/core/application-registry";
import { permissionFramework } from "@/core/permission-framework";

/**
 * Task 16's "State" + "Permissions" Developer Mode items, made real
 * (unlike the other five panel sections, which still honestly show
 * "not built yet" -- see panel-sections.ts): `ApplicationRegistry` and
 * `PermissionFramework` are pure frontend concepts with no backend
 * dependency, so this can query them for real today. Shows every
 * currently-registered module's live state (module-lifecycle.ts) and
 * permission grants. Currently empty by design -- no concrete module
 * has been built yet (Phase 3+ scope) -- and shows that honestly rather
 * than seeding fake modules to have something to display.
 */
export function ModuleStateInspector() {
  // No registry-level change events exist yet (nothing calls register()
  // outside a test today) -- re-render on demand rather than adding a
  // speculative pub/sub mechanism to a registry with zero real
  // consumers so far.
  const modules = useSyncExternalStore(
    () => () => {},
    () => applicationRegistry.getAll(),
  );

  if (modules.length === 0) {
    return (
      <div className="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
        <Inbox className="size-icon-lg text-muted-foreground" aria-hidden="true" />
        <p className="text-secondary text-muted-foreground">
          No modules registered yet. Every future module (Gmail, Calendar, ...) will appear here
          once it registers with the Application Registry.
        </p>
      </div>
    );
  }

  return (
    <div className="flex-1 space-y-3 overflow-y-auto p-4">
      {modules.map((module) => {
        const health = module.health();
        const status = module.status();
        const grants = permissionFramework.getGrantsFor(module.manifest.name);
        return (
          <div key={module.manifest.name} className="rounded-md border border-border p-3">
            <div className="flex items-center justify-between">
              <p className="text-secondary font-medium">{module.manifest.name}</p>
              <span
                className={
                  health.healthy
                    ? "text-caption text-success"
                    : "text-caption text-destructive"
                }
              >
                {status.state.state}
              </span>
            </div>
            <p className="text-caption text-muted-foreground">v{module.manifest.version}</p>
            <p className="mt-1 text-caption text-muted-foreground">
              {grants.length} permission{grants.length === 1 ? "" : "s"} granted ·{" "}
              {status.history.length} transition{status.history.length === 1 ? "" : "s"} recorded
            </p>
          </div>
        );
      })}
    </div>
  );
}
