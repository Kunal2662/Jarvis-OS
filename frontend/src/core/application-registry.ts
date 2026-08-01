/**
 * The Application Registry (Task 3) -- the single place every
 * `BaseApplication` (Task 1) instance is registered, looked up, and
 * queried by dependency/capability. A module is never referenced by a
 * direct import from another module's own file (that would be exactly
 * the kind of cross-module coupling `ARCHITECTURE.md` section 2's
 * layering rule forbids) -- everything goes through this registry
 * instead.
 */

import type { ConnectionState, ModuleState } from "@/core/module-lifecycle";
import type { ModuleCapability, ModuleManifest } from "@/core/module-manifest";
import { validateManifest } from "@/core/module-manifest";

/** The subset of `BaseApplication` the registry actually needs --
 *  defined here, not imported from base-application.ts, so this file
 *  has zero runtime dependency on that one (only `base-application.ts`
 *  depends on this file, never the reverse). Includes `health()`/
 *  `status()` so the Developer Mode State Inspector (Task 16) can query
 *  any registered module through the registry alone, without importing
 *  each module's own concrete class. `mount()`/`unmount()` were added in
 *  Phase 3 Task Group B for the identical reason, one level up:
 *  `WorkspaceManager` drives a module's navigation lifecycle through the
 *  registry alone, never importing a concrete module class either. */
export interface RegisterableApplication {
  readonly manifest: ModuleManifest;
  initialize(): Promise<void>;
  mount(): void;
  unmount(): void;
  health(): { healthy: boolean; state: ConnectionState };
  status(): { moduleId: string; state: ModuleState; history: readonly ModuleState[] };
}

export class DuplicateModuleError extends Error {}
export class MissingDependencyError extends Error {}
export class CircularDependencyError extends Error {}

export class ApplicationRegistry {
  private readonly modules = new Map<string, RegisterableApplication>();

  /** Cached result of `getAll()`, invalidated on every `register()`/
   *  `unregister()`. Exists so `getAll()` returns a referentially-stable
   *  array between mutations -- `ModuleStateInspector` (Developer Mode)
   *  feeds it directly into `useSyncExternalStore`, whose contract
   *  requires `getSnapshot()` to return the *same* reference when
   *  nothing changed; without this cache, `[...this.modules.values()]`
   *  allocated a new array on every call, which reads as "changed" on
   *  every check and produces a real, reproduced-in-browser "Maximum
   *  update depth exceeded" crash the moment the registry is non-empty. */
  private cachedAll: RegisterableApplication[] | null = null;

  /** Registers a module. Validates its manifest and that every declared
   *  dependency is *already* registered -- a module cannot depend on
   *  one that hasn't been registered yet, forcing dependency-ordered
   *  registration rather than allowing a dangling reference to exist
   *  even briefly. */
  register(app: RegisterableApplication): void {
    validateManifest(app.manifest);
    if (this.modules.has(app.manifest.name)) {
      throw new DuplicateModuleError(`Module "${app.manifest.name}" is already registered.`);
    }
    for (const dependencyId of app.manifest.dependencies) {
      if (!this.modules.has(dependencyId)) {
        throw new MissingDependencyError(
          `Module "${app.manifest.name}" depends on "${dependencyId}", which is not registered yet.`,
        );
      }
    }
    this.modules.set(app.manifest.name, app);
    this.cachedAll = null;
  }

  unregister(moduleId: string): void {
    const dependents = this.getDependents(moduleId);
    if (dependents.length > 0) {
      throw new Error(
        `Cannot unregister "${moduleId}": still depended on by ${dependents.map((d) => d.manifest.name).join(", ")}.`,
      );
    }
    this.modules.delete(moduleId);
    this.cachedAll = null;
  }

  // --- Lookup -------------------------------------------------------------
  get(moduleId: string): RegisterableApplication | undefined {
    return this.modules.get(moduleId);
  }

  has(moduleId: string): boolean {
    return this.modules.has(moduleId);
  }

  // --- Discovery ------------------------------------------------------------
  getAll(): RegisterableApplication[] {
    if (!this.cachedAll) {
      this.cachedAll = [...this.modules.values()];
    }
    return this.cachedAll;
  }

  getByCategory(category: ModuleManifest["category"]): RegisterableApplication[] {
    return this.getAll().filter((m) => m.manifest.category === category);
  }

  getByCapability(capability: ModuleCapability): RegisterableApplication[] {
    return this.getAll().filter((m) => m.manifest.capabilities.includes(capability));
  }

  // --- Dependencies -----------------------------------------------------------
  getDependents(moduleId: string): RegisterableApplication[] {
    return this.getAll().filter((m) => m.manifest.dependencies.includes(moduleId));
  }

  /** Topologically sorts every registered module so dependencies always
   *  come before their dependents -- the order `initialize()` (Task 1)
   *  must run in across the whole app, not just within one module.
   *  `register()`'s own "dependency must already be registered" gate
   *  already makes a true cycle unconstructable through the public API
   *  today -- the cycle check below is kept anyway as a correctness
   *  guard on the sort algorithm itself, not a currently-reachable
   *  error path, in case a future bulk-registration entry point ever
   *  registers a batch of manifests without that same ordering gate. */
  resolveInitializationOrder(): string[] {
    const order: string[] = [];
    const visited = new Set<string>();
    const visiting = new Set<string>();

    const visit = (moduleId: string): void => {
      if (visited.has(moduleId)) return;
      if (visiting.has(moduleId)) {
        throw new CircularDependencyError(`Circular dependency detected involving "${moduleId}".`);
      }
      visiting.add(moduleId);
      const module = this.modules.get(moduleId);
      for (const dependencyId of module?.manifest.dependencies ?? []) {
        visit(dependencyId);
      }
      visiting.delete(moduleId);
      visited.add(moduleId);
      order.push(moduleId);
    };

    for (const moduleId of this.modules.keys()) visit(moduleId);
    return order;
  }

  /** Initializes every registered module in dependency order -- the one
   *  place `BaseApplication.initialize()` is called from app startup,
   *  never invoked ad-hoc per module. */
  async initializeAll(): Promise<void> {
    for (const moduleId of this.resolveInitializationOrder()) {
      await this.modules.get(moduleId)?.initialize();
    }
  }

  // --- Metadata ---------------------------------------------------------------
  getMetadata(moduleId: string): ModuleManifest["developerMetadata"] | undefined {
    return this.modules.get(moduleId)?.manifest.developerMetadata;
  }
}

/** One shared instance -- module registration is process-wide. */
export const applicationRegistry = new ApplicationRegistry();
