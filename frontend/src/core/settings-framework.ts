/**
 * The Settings Framework -- generic, per-module settings storage
 * matching ARCHITECTURE.md section 11's standard (versioned, migration
 * strategy, defaults, import/export, reset) applied module-by-module on
 * the frontend. A module declares its `SettingsSchema` in its manifest
 * (module-manifest.ts); this framework is the only thing that reads or
 * writes the resulting values -- a module never touches `localStorage`
 * (or, later, Tauri's store plugin) directly.
 */

import type { SettingsSchema } from "@/core/module-manifest";

export class SettingsValidationError extends Error {}

type SettingsValues = Record<string, unknown>;

interface PersistedSettings {
  schemaVersion: number;
  values: SettingsValues;
}

/** A migration moves one module's persisted settings from
 *  `fromVersion` to `fromVersion + 1` -- registered per-module, run in
 *  order, exactly once each, matching ARCHITECTURE.md section 11's
 *  "forward-only, one function per version bump" rule. */
export type SettingsMigration = (values: SettingsValues) => SettingsValues;

export class ModuleSettings {
  private readonly moduleId: string;
  private readonly schema: SettingsSchema;
  private readonly currentVersion: number;
  private readonly migrations: SettingsMigration[] = [];

  constructor(moduleId: string, schema: SettingsSchema, currentVersion: number = 1) {
    this.moduleId = moduleId;
    this.schema = schema;
    this.currentVersion = currentVersion;
  }

  /** Register the migration that upgrades schema version `fromVersion`
   *  to `fromVersion + 1`. Call once per version bump, in order, at
   *  module registration time. */
  registerMigration(fromVersion: number, migration: SettingsMigration): void {
    this.migrations[fromVersion] = migration;
  }

  private storageKey(): string {
    return `jarvis.settings.${this.moduleId}`;
  }

  private defaults(): SettingsValues {
    return Object.fromEntries(Object.entries(this.schema).map(([key, field]) => [key, field.default]));
  }

  private validate(values: SettingsValues): void {
    for (const [key, value] of Object.entries(values)) {
      const field = this.schema[key];
      if (!field) continue; // extra/unknown keys are ignored, not rejected -- forward compatibility
      const actualType = typeof value;
      const expected = field.type === "integer" ? "number" : field.type;
      if (actualType !== expected) {
        throw new SettingsValidationError(
          `${this.moduleId}.${key}: expected ${field.type}, got ${actualType}.`,
        );
      }
    }
  }

  private migrate(persisted: PersistedSettings): PersistedSettings {
    let { schemaVersion, values } = persisted;
    while (schemaVersion < this.currentVersion) {
      const migration = this.migrations[schemaVersion];
      if (!migration) break; // no migration registered -- stop rather than guess
      values = migration(values);
      schemaVersion += 1;
    }
    return { schemaVersion, values };
  }

  /** Real values if any are persisted (migrated forward first),
   *  otherwise the schema's own defaults -- never `undefined`, per
   *  ARCHITECTURE.md section 11's "every setting has a declared
   *  default" rule. */
  get(): SettingsValues {
    const raw = localStorage.getItem(this.storageKey());
    if (!raw) return this.defaults();
    try {
      const persisted = this.migrate(JSON.parse(raw) as PersistedSettings);
      return { ...this.defaults(), ...persisted.values };
    } catch {
      return this.defaults();
    }
  }

  set(values: Partial<SettingsValues>): void {
    const merged = { ...this.get(), ...values };
    this.validate(merged);
    const persisted: PersistedSettings = { schemaVersion: this.currentVersion, values: merged };
    localStorage.setItem(this.storageKey(), JSON.stringify(persisted));
  }

  reset(): void {
    localStorage.removeItem(this.storageKey());
  }

  /** One JSON document, matching the manifest's `settingsSchema` shape
   *  -- ARCHITECTURE.md section 11's Import/Export standard. */
  export(): string {
    return JSON.stringify({ schemaVersion: this.currentVersion, values: this.get() });
  }

  /** Validated and migrated before being applied -- never trusts an
   *  imported file's `schemaVersion` blindly. */
  import(json: string): void {
    const parsed = this.migrate(JSON.parse(json) as PersistedSettings);
    this.validate(parsed.values);
    localStorage.setItem(
      this.storageKey(),
      JSON.stringify({ schemaVersion: this.currentVersion, values: parsed.values }),
    );
  }
}
