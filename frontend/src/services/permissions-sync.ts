/**
 * Backend permission decisions, applied to the local framework -- M8
 * Phase 2's "Permissions model surfaced from the backend's Authorization
 * Engine".
 *
 * **This is not a second permission system.** `core/permission-
 * framework.ts` (Phase 1) stays the one thing frontend code asks "may
 * this module do that?"; it was built with an in-memory store precisely
 * because nothing had populated it yet. This module populates it, from
 * the backend's `PermissionModel` -- the real Authorization Engine, whose
 * ten-scope vocabulary the framework already mirrors exactly (verified
 * against `core/plugins/sdk.py`'s `PERMISSION_SCOPES`).
 *
 * Direction is one-way on read and write-through on change: the backend
 * decides, the framework caches the decision so a synchronous
 * `isGranted()` check stays synchronous. A UI that grants a permission
 * calls `grantPermission` here, which asks the backend first and only
 * updates the local cache once the backend has agreed -- never the
 * reverse, which would show a permission as held that the process
 * enforcing it does not recognise.
 */

import { permissionsApi, type PermissionEntry } from "@/services/api/endpoints";
import {
  permissionFramework,
  type PermissionScope,
} from "@/core/permission-framework";

/** The ten scopes both sides share. A backend scope outside this set is
 *  ignored rather than coerced: the framework's `PermissionScope` union
 *  is exhaustive by design, and widening it here to accommodate an
 *  unknown string would defeat that. */
const KNOWN_SCOPES: readonly PermissionScope[] = [
  "network",
  "filesystem",
  "hotkey",
  "agent_tools",
  "voice.stt",
  "voice.tts",
  "memory.read",
  "memory.write",
  "smart_home",
  "notifications",
];

export function isKnownScope(scope: string): scope is PermissionScope {
  return (KNOWN_SCOPES as readonly string[]).includes(scope);
}

/**
 * Mirror one backend entry into the framework.
 *
 * `pending` becomes *absent* rather than a denial. The distinction
 * matters: `isGranted()` returning `false` for an absent grant lets the
 * UI prompt, whereas recording an explicit `always_deny` would make the
 * app treat "not asked yet" as "the user said no".
 */
function applyEntry(entry: PermissionEntry): void {
  if (!isKnownScope(entry.scope)) return;
  if (entry.state === "granted") {
    permissionFramework.grant(entry.plugin_id, entry.scope, "always_allow");
  } else if (entry.state === "denied") {
    permissionFramework.grant(entry.plugin_id, entry.scope, "always_deny");
  } else {
    permissionFramework.revoke(entry.plugin_id, entry.scope);
  }
}

/** Load one plugin's permissions from the backend into the framework. */
export async function syncPluginPermissions(pluginId: string): Promise<PermissionEntry[]> {
  const entries = await permissionsApi.forPlugin(pluginId);
  for (const entry of entries) applyEntry(entry);
  return entries;
}

/** Grant server-side, then locally. Throws if the backend refuses, and
 *  the local cache is untouched in that case. */
export async function grantPermission(pluginId: string, scope: PermissionScope): Promise<void> {
  await permissionsApi.grant(pluginId, scope);
  applyEntry({ plugin_id: pluginId, scope, state: "granted" });
}

export async function denyPermission(pluginId: string, scope: PermissionScope): Promise<void> {
  await permissionsApi.deny(pluginId, scope);
  applyEntry({ plugin_id: pluginId, scope, state: "denied" });
}

export async function revokePermission(pluginId: string, scope: PermissionScope): Promise<void> {
  await permissionsApi.revoke(pluginId, scope);
  applyEntry({ plugin_id: pluginId, scope, state: "pending" });
}

/** Everything awaiting an operator decision -- what a permission-prompt
 *  surface reads. */
export async function loadPendingPermissions(): Promise<PermissionEntry[]> {
  return permissionsApi.pending();
}
