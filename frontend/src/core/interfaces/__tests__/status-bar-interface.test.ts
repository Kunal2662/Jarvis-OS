import { beforeEach, describe, expect, it } from "vitest";
import { statusBarRegistry, type StatusBarContribution } from "@/core/interfaces/status-bar-interface";

function contribution(overrides: Partial<StatusBarContribution> = {}): StatusBarContribution {
  return {
    id: "test.item",
    moduleId: "test-module",
    displayName: "Test Item",
    category: "left",
    priority: 10,
    isCore: false,
    render: () => null,
    ...overrides,
  };
}

/**
 * Thin smoke test only -- the actual register/unregister/getAll/
 * getByModule contract is proven once, generically, in
 * `core/__tests__/contribution-registry.test.ts`. This just confirms
 * `statusBarRegistry` is really a working instance of that shared
 * mechanism with status-item-shaped data, not a parallel
 * reimplementation.
 */
describe("statusBarRegistry", () => {
  beforeEach(() => {
    for (const item of statusBarRegistry.getAll()) {
      statusBarRegistry.unregister(item.id);
    }
  });

  it("registers and retrieves a status bar contribution", () => {
    const item = contribution();
    statusBarRegistry.register(item);
    expect(statusBarRegistry.get("test.item")).toBe(item);
  });

  it("getByModule() filters to a single module's contributions", () => {
    statusBarRegistry.register(contribution({ id: "a", moduleId: "github" }));
    statusBarRegistry.register(contribution({ id: "b", moduleId: "spotify" }));

    expect(statusBarRegistry.getByModule("github").map((c) => c.id)).toEqual(["a"]);
  });
});
