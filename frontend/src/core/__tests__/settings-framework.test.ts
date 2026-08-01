import { beforeEach, describe, expect, it } from "vitest";
import { ModuleSettings, SettingsValidationError } from "@/core/settings-framework";
import type { SettingsSchema } from "@/core/module-manifest";

const schema: SettingsSchema = {
  syncIntervalMinutes: { type: "integer", default: 15 },
  enabled: { type: "boolean", default: true },
};

describe("ModuleSettings", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("returns schema defaults when nothing is persisted", () => {
    const settings = new ModuleSettings("mod-a", schema);
    expect(settings.get()).toEqual({ syncIntervalMinutes: 15, enabled: true });
  });

  it("set() persists and get() reflects it", () => {
    const settings = new ModuleSettings("mod-a", schema);
    settings.set({ syncIntervalMinutes: 30 });
    expect(settings.get()).toEqual({ syncIntervalMinutes: 30, enabled: true });
  });

  it("rejects a value of the wrong type", () => {
    const settings = new ModuleSettings("mod-a", schema);
    expect(() => settings.set({ syncIntervalMinutes: "thirty" as unknown as number })).toThrow(
      SettingsValidationError,
    );
  });

  it("reset() clears back to defaults", () => {
    const settings = new ModuleSettings("mod-a", schema);
    settings.set({ syncIntervalMinutes: 60 });
    settings.reset();
    expect(settings.get()).toEqual({ syncIntervalMinutes: 15, enabled: true });
  });

  it("export()/import() round-trip", () => {
    const settings = new ModuleSettings("mod-a", schema);
    settings.set({ syncIntervalMinutes: 45 });
    const exported = settings.export();

    const other = new ModuleSettings("mod-b", schema);
    other.import(exported);
    expect(other.get().syncIntervalMinutes).toBe(45);
  });

  it("migrates an older persisted schema version forward", () => {
    const settings = new ModuleSettings("mod-a", schema, 2);
    settings.registerMigration(1, (values) => ({ ...values, enabled: true }));

    localStorage.setItem(
      "jarvis.settings.mod-a",
      JSON.stringify({ schemaVersion: 1, values: { syncIntervalMinutes: 20 } }),
    );

    expect(settings.get()).toEqual({ syncIntervalMinutes: 20, enabled: true });
  });

  it("settings are namespaced per module -- one module's values never leak to another", () => {
    const a = new ModuleSettings("mod-a", schema);
    const b = new ModuleSettings("mod-b", schema);
    a.set({ syncIntervalMinutes: 99 });
    expect(b.get().syncIntervalMinutes).toBe(15);
  });
});
