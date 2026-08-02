/**
 * The Dashboard Widget Registry (UI Architecture Update) -- the
 * Dashboard's equivalent of `application-registry.ts`: the single
 * place every widget a module contributes is registered, looked up,
 * and enumerated. Deliberately mirrors `ApplicationRegistry`'s own
 * shape (register/unregister/getAll, duplicate-id guard, a cached
 * `getAll()` so `useSyncExternalStore` consumers stay stable) rather
 * than inventing a second registry pattern -- a plugin author who
 * already understands one understands both. No React import: this is
 * a `core/` framework file, the same rule `base-application.ts`
 * follows; the widget grid UI that will eventually render these
 * contributions is a separate, later task.
 */

export interface DashboardWidgetContribution {
  id: string;
  moduleId: string;
  title: string;
  /** Renders the widget's content. A function reference, not
   *  serialized data -- the same shape `NavigationContribution`'s own
   *  `commandPaletteEntries[].action` already uses, appropriate for
   *  same-process, same-bundle first-party modules (every module
   *  today). Typed `unknown` rather than a React type here on purpose:
   *  no widget grid UI exists yet to consume this contract, and this
   *  file has no React dependency to justify importing `ReactNode`
   *  just for a type. */
  render: () => unknown;
  defaultSize: { width: number; height: number };
}

export class DuplicateWidgetError extends Error {}

export class DashboardWidgetRegistry {
  private readonly widgets = new Map<string, DashboardWidgetContribution>();
  private cachedAll: DashboardWidgetContribution[] | null = null;

  register(widget: DashboardWidgetContribution): void {
    if (this.widgets.has(widget.id)) {
      throw new DuplicateWidgetError(`Widget "${widget.id}" is already registered.`);
    }
    this.widgets.set(widget.id, widget);
    this.cachedAll = null;
  }

  unregister(widgetId: string): void {
    this.widgets.delete(widgetId);
    this.cachedAll = null;
  }

  get(widgetId: string): DashboardWidgetContribution | undefined {
    return this.widgets.get(widgetId);
  }

  /** Referentially stable between mutations -- required by
   *  `useSyncExternalStore` consumers (see
   *  `core/application-registry.ts`'s own header comment for the
   *  exact bug this cache exists to prevent). */
  getAll(): DashboardWidgetContribution[] {
    if (!this.cachedAll) {
      this.cachedAll = [...this.widgets.values()];
    }
    return this.cachedAll;
  }

  getByModule(moduleId: string): DashboardWidgetContribution[] {
    return this.getAll().filter((widget) => widget.moduleId === moduleId);
  }
}

/** One shared instance -- widget registration is process-wide, matching
 *  `applicationRegistry`'s own singleton pattern. */
export const dashboardWidgetRegistry = new DashboardWidgetRegistry();
