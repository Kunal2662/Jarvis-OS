import { beforeEach, describe, expect, it } from "vitest";
import { dashboardWidgetRegistry, type DashboardWidgetContribution } from "@/core/dashboard-widget-registry";

function widget(overrides: Partial<DashboardWidgetContribution> = {}): DashboardWidgetContribution {
  return {
    id: "test-widget",
    moduleId: "test-module",
    title: "Test Widget",
    render: () => null,
    defaultSize: { width: 2, height: 2 },
    ...overrides,
  };
}

/**
 * Thin smoke test only -- the actual register/unregister/getAll/
 * getByModule contract is proven once, generically, in
 * `core/__tests__/contribution-registry.test.ts`. This just confirms
 * `dashboardWidgetRegistry` is really a working instance of that shared
 * mechanism with widget-shaped data, not a parallel reimplementation.
 */
describe("dashboardWidgetRegistry", () => {
  beforeEach(() => {
    for (const w of dashboardWidgetRegistry.getAll()) {
      dashboardWidgetRegistry.unregister(w.id);
    }
  });

  it("registers and retrieves a widget contribution", () => {
    const w = widget();
    dashboardWidgetRegistry.register(w);
    expect(dashboardWidgetRegistry.get("test-widget")).toBe(w);
  });

  it("getByModule() filters to a single module's widgets", () => {
    dashboardWidgetRegistry.register(widget({ id: "tasks", moduleId: "automations" }));
    dashboardWidgetRegistry.register(widget({ id: "notes", moduleId: "files" }));

    expect(dashboardWidgetRegistry.getByModule("automations").map((w) => w.id)).toEqual(["tasks"]);
  });
});
