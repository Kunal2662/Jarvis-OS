import type { ModuleManifest } from "@/core/module-manifest";

/**
 * Testing Foundation (Task 17) -- builds a minimal, valid
 * `ModuleManifest` for a test double, so every future module's own test
 * suite (and this framework's own tests) don't hand-write the same
 * 10-field object repeatedly. Every field has a sane default;
 * `overrides` replaces only what a specific test needs to vary.
 */
export function createTestManifest(overrides: Partial<ModuleManifest> = {}): ModuleManifest {
  return {
    name: "test-module",
    displayName: "Test Module",
    version: "1.0.0",
    category: "local",
    dependencies: [],
    permissions: [],
    commands: [],
    voiceCommands: [],
    automationSupport: { actions: [], reversible: [] },
    settingsSchema: {},
    icon: "square",
    routes: [],
    capabilities: [],
    developerMetadata: { author: "test", homepage: null, repository: null },
    ...overrides,
  };
}
