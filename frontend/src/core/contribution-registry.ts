/**
 * The generic mechanism every UI extension surface registers through --
 * Navigation and Dashboard Widgets today; Routes, Settings pages,
 * Commands, Notifications, Automation actions, Context Menu actions,
 * Permissions, and Developer Tools panels as each is built. All of them
 * store their contributions in an instance of this one class, not a
 * bespoke `Map` plus hand-rolled register/unregister/getAll per surface.
 * "Every UI surface registers through the same architecture" is
 * literally true because they share this implementation, not because
 * they happen to look similar.
 *
 * Deliberately NOT merged into `ApplicationRegistry` itself (Task 3) --
 * that class owns something structurally different (one
 * `RegisterableApplication` per module, plus dependency resolution and
 * manifest validation neither this class nor its consumers need); a
 * module and the many small things it *contributes* to other surfaces
 * are different shapes of data. This is the shared mechanism those
 * contributions use. `ApplicationRegistry` predates this generalization
 * and is deliberately not refactored to compose it -- it already
 * correctly implements the same register/unregister/getAll(cached)
 * pattern, and it is widely depended upon (every module's `initialize()`
 * calls it); refactoring its internals would touch load-bearing, already
 * -tested code for zero externally-visible benefit, since its public API
 * wouldn't change either way.
 */

export interface Contribution {
  id: string;
  moduleId: string;
}

export class DuplicateContributionError extends Error {}

export class ContributionRegistry<T extends Contribution> {
  private readonly items = new Map<string, T>();

  /** Cached result of `getAll()`, invalidated on every mutation -- same
   *  reason `core/application-registry.ts`'s own `getAll()` caches:
   *  a `useSyncExternalStore` consumer needs a referentially-stable
   *  snapshot when nothing changed, or it loops forever. */
  private cachedAll: T[] | null = null;

  register(item: T): void {
    if (this.items.has(item.id)) {
      throw new DuplicateContributionError(`Contribution "${item.id}" is already registered.`);
    }
    this.items.set(item.id, item);
    this.cachedAll = null;
  }

  unregister(id: string): void {
    if (!this.items.delete(id)) return;
    this.cachedAll = null;
  }

  /** Removes every contribution a given module made -- the bulk-cleanup
   *  path a module's own teardown uses instead of tracking each
   *  contribution id it made individually. */
  unregisterByModule(moduleId: string): void {
    let changed = false;
    for (const item of this.getAll()) {
      if (item.moduleId === moduleId && this.items.delete(item.id)) {
        changed = true;
      }
    }
    if (changed) this.cachedAll = null;
  }

  get(id: string): T | undefined {
    return this.items.get(id);
  }

  getAll(): T[] {
    if (!this.cachedAll) {
      this.cachedAll = [...this.items.values()];
    }
    return this.cachedAll;
  }

  getByModule(moduleId: string): T[] {
    return this.getAll().filter((item) => item.moduleId === moduleId);
  }
}
