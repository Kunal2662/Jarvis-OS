import { beforeEach, describe, expect, it } from "vitest";
import { isModuleEnabled, useModuleEnablementStore } from "@/stores/module-enablement.store";

describe("useModuleEnablementStore", () => {
  beforeEach(() => {
    useModuleEnablementStore.setState({ enabledModuleIds: [] });
  });

  it("starts with nothing enabled -- minimal default set is enforced by isCore, not this store", () => {
    expect(useModuleEnablementStore.getState().enabledModuleIds).toEqual([]);
  });

  it("enableModule() adds a module id, idempotently", () => {
    const { enableModule } = useModuleEnablementStore.getState();
    enableModule("gmail");
    enableModule("gmail");

    expect(useModuleEnablementStore.getState().enabledModuleIds).toEqual(["gmail"]);
  });

  it("disableModule() removes a module id", () => {
    const { enableModule, disableModule } = useModuleEnablementStore.getState();
    enableModule("gmail");
    disableModule("gmail");

    expect(useModuleEnablementStore.getState().enabledModuleIds).toEqual([]);
  });

  it("disableModule() on a never-enabled id is a safe no-op", () => {
    expect(() => useModuleEnablementStore.getState().disableModule("never-enabled")).not.toThrow();
  });
});

describe("isModuleEnabled", () => {
  it("a core module is always enabled, regardless of the enabled set", () => {
    expect(isModuleEnabled(true, "settings", [])).toBe(true);
  });

  it("a non-core module is enabled only if present in the enabled set", () => {
    expect(isModuleEnabled(false, "gmail", [])).toBe(false);
    expect(isModuleEnabled(false, "gmail", ["gmail"])).toBe(true);
    expect(isModuleEnabled(false, "gmail", ["calendar"])).toBe(false);
  });
});
