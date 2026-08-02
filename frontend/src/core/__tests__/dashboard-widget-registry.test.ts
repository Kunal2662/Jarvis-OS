import { beforeEach, describe, expect, it } from "vitest";
import {
  DashboardWidgetRegistry,
  DuplicateWidgetError,
  type DashboardWidgetContribution,
} from "@/core/dashboard-widget-registry";

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

describe("DashboardWidgetRegistry", () => {
  let registry: DashboardWidgetRegistry;

  beforeEach(() => {
    registry = new DashboardWidgetRegistry();
  });

  it("registers and looks up a widget", () => {
    const w = widget();
    registry.register(w);
    expect(registry.get("test-widget")).toBe(w);
  });

  it("rejects a duplicate widget id", () => {
    registry.register(widget());
    expect(() => registry.register(widget())).toThrow(DuplicateWidgetError);
  });

  it("getAll() returns a referentially-stable array between mutations", () => {
    registry.register(widget());
    // Same regression guard as ApplicationRegistry's own test --
    // a future consumer via useSyncExternalStore needs this.
    expect(registry.getAll()).toBe(registry.getAll());
  });

  it("getAll() returns a new reference after register()/unregister()", () => {
    registry.register(widget({ id: "a" }));
    const before = registry.getAll();
    registry.register(widget({ id: "b" }));
    expect(registry.getAll()).not.toBe(before);

    const beforeUnregister = registry.getAll();
    registry.unregister("b");
    expect(registry.getAll()).not.toBe(beforeUnregister);
  });

  it("getByModule() filters to a single module's contributions", () => {
    registry.register(widget({ id: "tasks", moduleId: "automations" }));
    registry.register(widget({ id: "notes", moduleId: "files" }));
    registry.register(widget({ id: "quick-actions", moduleId: "automations" }));

    const automationsWidgets = registry.getByModule("automations").map((w) => w.id);
    expect(automationsWidgets).toEqual(["tasks", "quick-actions"]);
  });

  it("unregister() removes a widget", () => {
    registry.register(widget());
    registry.unregister("test-widget");
    expect(registry.get("test-widget")).toBeUndefined();
  });
});
