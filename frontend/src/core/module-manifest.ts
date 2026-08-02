/**
 * The Module Manifest -- the frontend TypeScript shape of
 * ARCHITECTURE.md section 10's manifest specification, extended with
 * `category` and `capabilities`, the two fields this phase's Task 4
 * explicitly adds on top of that standard. Every field below maps to
 * exactly one entry in the backend manifest's JSON shape; nothing here
 * invents a parallel format.
 */

import type { ConnectionState } from "@/core/module-lifecycle";
import type { PermissionScope } from "@/core/permission-framework";

/**
 * Whether a module represents an external, authenticated connection
 * (Gmail, Spotify) or purely local state (Tasks, Memory) -- decides the
 * default `ConnectionState` per `module-lifecycle.ts`'s
 * `DEFAULT_STATE_BY_CATEGORY`.
 */
export type ModuleCategory = "connected" | "local";

/** What a module can *do*, independent of what it currently has
 *  permission for -- e.g. a module capable of `"automation"` may still
 *  have that permission denied; capabilities describe the ceiling,
 *  permissions (permission-framework.ts) describe what's actually
 *  granted right now. */
export type ModuleCapability = "ai" | "voice" | "automation" | "notifications" | "background-sync";

export interface ModuleCommand {
  id: string;
  description: string;
}

export interface VoiceCommandBinding {
  phrase: string;
  commandId: string;
}

export interface AutomationSupport {
  actions: string[];
  reversible: string[];
}

/** JSON Schema-shaped, matching `settings-framework.ts`'s expectations
 *  and the backend's own settings schema convention (ARCHITECTURE.md
 *  section 11). */
export type SettingsSchema = Record<
  string,
  { type: "string" | "number" | "boolean" | "integer"; default: unknown; description?: string }
>;

export interface ModuleManifest {
  name: string;
  /** Human-readable label a UI renders (e.g. "Files & Drive") -- distinct
   *  from `name`, which is the kebab-case machine id every other field on
   *  this interface and `ApplicationRegistry` key off of. */
  displayName: string;
  version: string;
  category: ModuleCategory;
  dependencies: string[];
  permissions: PermissionScope[];
  commands: ModuleCommand[];
  voiceCommands: VoiceCommandBinding[];
  automationSupport: AutomationSupport;
  settingsSchema: SettingsSchema;
  icon: string;
  routes: string[];
  capabilities: ModuleCapability[];
  /** True only for the fixed, non-disableable default set (Dashboard,
   *  AI's three children, Automation, Files, Settings) -- per the UI
   *  Architecture Update, everything else ships disabled by default
   *  and only appears once `ModuleEnablementStore` turns it on.
   *  Manifest *data*, not a hardcoded list in the Sidebar component
   *  itself -- Core JARVIS never needs a code change when a new
   *  optional module registers. */
  isCore: boolean;
  /** Groups this module under a synthetic parent nav item (e.g. `"ai"`
   *  for Conversation/Voice/Memory) -- `undefined` renders as a
   *  top-level entry. Purely UI-taxonomy data; a module with no
   *  `parentGroup` behaves exactly as before this field existed. */
  parentGroup?: string;
  developerMetadata: {
    author: string;
    homepage: string | null;
    repository: string | null;
  };
}

export class ManifestValidationError extends Error {}

/**
 * Validates a manifest's structural shape before `ApplicationRegistry`
 * (Task 3) accepts it -- catches an incomplete/malformed module
 * declaration at registration time, not at some later, harder-to-trace
 * failure point.
 */
export function validateManifest(manifest: ModuleManifest): void {
  if (!manifest.name || !/^[a-z][a-z0-9-]*$/.test(manifest.name)) {
    throw new ManifestValidationError(
      `Manifest "name" must be lowercase, kebab-case, and non-empty (got "${manifest.name}").`,
    );
  }
  if (!manifest.displayName || !manifest.displayName.trim()) {
    throw new ManifestValidationError(`Manifest "${manifest.name}" is missing a non-empty "displayName".`);
  }
  if (!/^\d+\.\d+\.\d+$/.test(manifest.version)) {
    throw new ManifestValidationError(
      `Manifest "${manifest.name}" has an invalid semver "version": "${manifest.version}".`,
    );
  }
  if (manifest.category !== "connected" && manifest.category !== "local") {
    throw new ManifestValidationError(`Manifest "${manifest.name}" has an unknown category.`);
  }
  const commandIds = new Set(manifest.commands.map((c) => c.id));
  for (const binding of manifest.voiceCommands) {
    if (!commandIds.has(binding.commandId)) {
      throw new ManifestValidationError(
        `Manifest "${manifest.name}": voice command "${binding.phrase}" references unknown command id "${binding.commandId}".`,
      );
    }
  }
}

/** The default `ConnectionState` (module-lifecycle.ts) a module of this
 *  manifest's category starts in on a fresh install. */
export function defaultStateFor(manifest: ModuleManifest): ConnectionState {
  return manifest.category === "connected" ? "not_configured" : "empty";
}
