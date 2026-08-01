import { MODULE_DEFINITIONS } from "@/modules/module-definitions";
import { PlaceholderModule } from "@/modules/placeholder-module";

/**
 * Builds one `PlaceholderModule` per `MODULE_DEFINITIONS` entry and calls
 * `initialize()` on each, which is what actually registers it with the
 * shared `applicationRegistry` (`BaseApplication.initialize()`, Task 1) --
 * this function never calls `applicationRegistry.register()` directly.
 *
 * Called in array order, not via `ApplicationRegistry.resolveInitializationOrder()`:
 * every one of these 14 modules has an empty `dependencies` list, so
 * ordering doesn't matter for them, and `resolveInitializationOrder()`
 * sorts modules already present in the registry map -- these aren't yet,
 * since registration is itself a side effect of the `initialize()` call
 * this function is making for the first time. (Noted for whoever wires up
 * a module with real dependencies later: a true cold-start, nothing-
 * registered-yet bulk `initializeAll()` call has this same ordering gap.)
 *
 * Not called from application bootstrap yet -- deciding when module
 * initialization runs relative to routing and mounting belongs to
 * Workspace Manager, not this task.
 */
export async function registerPlaceholderModules(): Promise<PlaceholderModule[]> {
  const modules = MODULE_DEFINITIONS.map((manifest) => new PlaceholderModule(manifest));
  for (const module of modules) {
    await module.initialize();
  }
  return modules;
}
