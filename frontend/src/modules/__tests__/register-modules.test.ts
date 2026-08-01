import { beforeEach, describe, expect, it } from "vitest";
import { applicationRegistry } from "@/core/application-registry";
import { MODULE_DEFINITIONS } from "@/modules/module-definitions";
import { registerPlaceholderModules } from "@/modules/register-modules";

describe("registerPlaceholderModules", () => {
  beforeEach(() => {
    for (const module of applicationRegistry.getAll()) {
      applicationRegistry.unregister(module.manifest.name);
    }
  });

  it("MODULE_DEFINITIONS contains exactly the 14 workspace ids ported from nav-items.ts", () => {
    expect(MODULE_DEFINITIONS.map((m) => m.name)).toEqual([
      "home",
      "chat",
      "voice",
      "memory",
      "automations",
      "files",
      "browser",
      "coding",
      "finance",
      "smart-home",
      "calendar",
      "gmail",
      "spotify",
      "settings",
    ]);
  });

  it("registry initialization succeeds without throwing", async () => {
    await expect(registerPlaceholderModules()).resolves.toBeDefined();
  });

  it("registry contains every module after registration", async () => {
    await registerPlaceholderModules();

    expect(applicationRegistry.getAll()).toHaveLength(MODULE_DEFINITIONS.length);
    for (const definition of MODULE_DEFINITIONS) {
      expect(applicationRegistry.has(definition.name)).toBe(true);
    }
  });

  it("registers every module exactly once -- no duplicate registrations", async () => {
    await registerPlaceholderModules();

    const ids = applicationRegistry.getAll().map((m) => m.manifest.name);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("calling registerPlaceholderModules twice does not throw or duplicate entries", async () => {
    await registerPlaceholderModules();
    await expect(registerPlaceholderModules()).resolves.toBeDefined();

    expect(applicationRegistry.getAll()).toHaveLength(MODULE_DEFINITIONS.length);
  });

  it("preserves each module's manifest metadata exactly", async () => {
    await registerPlaceholderModules();

    for (const definition of MODULE_DEFINITIONS) {
      expect(applicationRegistry.get(definition.name)?.manifest).toEqual(definition);
    }
  });

  it("every module starts in the default ConnectionState for its category", async () => {
    await registerPlaceholderModules();

    for (const definition of MODULE_DEFINITIONS) {
      const expectedState = definition.category === "connected" ? "not_configured" : "empty";
      expect(applicationRegistry.get(definition.name)?.health().state).toBe(expectedState);
    }
  });
});
