import { beforeEach, describe, expect, it } from "vitest";
import { ContributionRegistry, DuplicateContributionError, type Contribution } from "@/core/contribution-registry";

interface TestContribution extends Contribution {
  label: string;
}

function contribution(overrides: Partial<TestContribution> = {}): TestContribution {
  return { id: "test-id", moduleId: "test-module", label: "Test", ...overrides };
}

/**
 * The canonical test suite for the generic mechanism every UI extension
 * surface (Navigation, Dashboard Widgets, and future ones) shares --
 * `dashboard-widget-registry.test.ts` and any future contribution-
 * holding registry's own tests stay thin, since the register/unregister/
 * getAll/getByModule contract is proven once, here.
 */
describe("ContributionRegistry", () => {
  let registry: ContributionRegistry<TestContribution>;

  beforeEach(() => {
    registry = new ContributionRegistry<TestContribution>();
  });

  it("registers and looks up a contribution", () => {
    const c = contribution();
    registry.register(c);
    expect(registry.get("test-id")).toBe(c);
  });

  it("rejects a duplicate contribution id", () => {
    registry.register(contribution());
    expect(() => registry.register(contribution())).toThrow(DuplicateContributionError);
  });

  it("getAll() returns a referentially-stable array between mutations", () => {
    registry.register(contribution());
    // Regression guard: a useSyncExternalStore consumer needs the same
    // reference back when nothing changed, or React loops forever (see
    // core/application-registry.ts's own history of this exact bug).
    expect(registry.getAll()).toBe(registry.getAll());
  });

  it("getAll() returns a new reference after register()/unregister()", () => {
    registry.register(contribution({ id: "a" }));
    const beforeRegister = registry.getAll();
    registry.register(contribution({ id: "b" }));
    expect(registry.getAll()).not.toBe(beforeRegister);

    const beforeUnregister = registry.getAll();
    registry.unregister("b");
    expect(registry.getAll()).not.toBe(beforeUnregister);
  });

  it("unregister() on an unknown id is a safe no-op, including for getAll() stability", () => {
    registry.register(contribution());
    const before = registry.getAll();
    expect(() => registry.unregister("never-registered")).not.toThrow();
    expect(registry.getAll()).toBe(before); // nothing actually changed
  });

  it("getByModule() filters to a single module's contributions", () => {
    registry.register(contribution({ id: "a", moduleId: "automations" }));
    registry.register(contribution({ id: "b", moduleId: "files" }));
    registry.register(contribution({ id: "c", moduleId: "automations" }));

    expect(registry.getByModule("automations").map((c) => c.id)).toEqual(["a", "c"]);
  });

  it("unregisterByModule() removes every contribution a module made", () => {
    registry.register(contribution({ id: "a", moduleId: "automations" }));
    registry.register(contribution({ id: "b", moduleId: "files" }));
    registry.register(contribution({ id: "c", moduleId: "automations" }));

    registry.unregisterByModule("automations");

    expect(registry.getByModule("automations")).toEqual([]);
    expect(registry.get("b")).toBeDefined();
  });

  it("unregisterByModule() for a module with no contributions is a safe no-op", () => {
    registry.register(contribution({ id: "a", moduleId: "files" }));
    const before = registry.getAll();
    expect(() => registry.unregisterByModule("never-contributed")).not.toThrow();
    expect(registry.getAll()).toBe(before);
  });
});
