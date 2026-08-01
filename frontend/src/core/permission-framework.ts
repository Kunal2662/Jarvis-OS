/**
 * The Permission Framework -- generic, per Task 5's explicit
 * instruction: this file has no knowledge of Gmail, Calendar, or any
 * other concrete module. It mirrors the fixed permission vocabulary
 * ARCHITECTURE.md section 10 already defines for the backend manifest
 * (`network`, `filesystem`, `hotkey`, `agent_tools`, `voice.stt`,
 * `voice.tts`, `memory.read`, `memory.write`, `smart_home`,
 * `notifications`), plus the categories/decision types this phase adds
 * on the frontend side. The actual grant/deny decision is made by the
 * user, surfaced through a real UI in a later phase -- this framework
 * only defines the shape that decision takes and enforces it once made.
 */

export type PermissionScope =
  | "network"
  | "filesystem"
  | "hotkey"
  | "agent_tools"
  | "voice.stt"
  | "voice.tts"
  | "memory.read"
  | "memory.write"
  | "smart_home"
  | "notifications";

export type PermissionCategory = "data" | "device" | "ai" | "system";

export const PERMISSION_CATEGORY: Record<PermissionScope, PermissionCategory> = {
  network: "system",
  filesystem: "system",
  hotkey: "device",
  agent_tools: "ai",
  "voice.stt": "device",
  "voice.tts": "device",
  "memory.read": "data",
  "memory.write": "data",
  smart_home: "device",
  notifications: "system",
};

export type PermissionDecision = "ask_once" | "always_allow" | "always_deny" | "temporary";

export interface PermissionGrant {
  moduleId: string;
  scope: PermissionScope;
  decision: PermissionDecision;
  /** Required, and only meaningful, when `decision === "temporary"`. */
  expiresAt: string | null;
  grantedAt: string;
}

export interface PermissionHistoryEntry extends PermissionGrant {
  /** Whether this entry represents the grant being created, or a
   *  request that was evaluated against it. */
  event: "granted" | "revoked" | "checked" | "denied";
}

/**
 * One instance per running app, injected into every `BaseApplication`
 * (Task 1) -- modules never maintain their own permission state, they
 * ask this framework. Backed by an in-memory store for now; persistence
 * is Storage Framework's (Task 7) job once a module actually needs a
 * grant to survive a restart, not this framework's own concern.
 */
export class PermissionFramework {
  private readonly grants = new Map<string, PermissionGrant>();
  private readonly history: PermissionHistoryEntry[] = [];

  private key(moduleId: string, scope: PermissionScope): string {
    return `${moduleId}:${scope}`;
  }

  grant(moduleId: string, scope: PermissionScope, decision: PermissionDecision, expiresAt: string | null = null): PermissionGrant {
    const grant: PermissionGrant = { moduleId, scope, decision, expiresAt, grantedAt: new Date().toISOString() };
    this.grants.set(this.key(moduleId, scope), grant);
    this.history.push({ ...grant, event: "granted" });
    return grant;
  }

  revoke(moduleId: string, scope: PermissionScope): void {
    const existing = this.grants.get(this.key(moduleId, scope));
    this.grants.delete(this.key(moduleId, scope));
    if (existing) this.history.push({ ...existing, event: "revoked" });
  }

  /**
   * Whether `moduleId` currently holds `scope` -- expired `temporary`
   * grants are treated as absent (and swept) rather than trusted stale.
   * `"ask_once"` grants that have already been consulted once still
   * read as allowed here; re-prompting on every single call would make
   * "ask once" meaningless -- the UI layer decides when a fresh prompt
   * is warranted (e.g. a new session), not this check.
   */
  isGranted(moduleId: string, scope: PermissionScope): boolean {
    const grant = this.grants.get(this.key(moduleId, scope));
    if (!grant) {
      this.history.push({
        moduleId,
        scope,
        decision: "always_deny",
        expiresAt: null,
        grantedAt: new Date().toISOString(),
        event: "denied",
      });
      return false;
    }
    if (grant.decision === "always_deny") return false;
    if (grant.decision === "temporary" && grant.expiresAt && new Date(grant.expiresAt) < new Date()) {
      this.grants.delete(this.key(moduleId, scope));
      return false;
    }
    this.history.push({ ...grant, event: "checked" });
    return true;
  }

  getGrant(moduleId: string, scope: PermissionScope): PermissionGrant | null {
    return this.grants.get(this.key(moduleId, scope)) ?? null;
  }

  getGrantsFor(moduleId: string): PermissionGrant[] {
    return [...this.grants.values()].filter((g) => g.moduleId === moduleId);
  }

  /** Diagnostic/Developer Mode use (Task 16) -- every grant, denial,
   *  revocation, and check, oldest first. Never drives application
   *  logic, matching `ModuleLifecycle.getHistory()`'s same rule. */
  getHistory(moduleId?: string): readonly PermissionHistoryEntry[] {
    return moduleId ? this.history.filter((e) => e.moduleId === moduleId) : this.history;
  }
}

/** One shared instance -- permission grants are process-wide, not
 *  per-component; every module reads/writes through this single
 *  framework, matching ARCHITECTURE.md section 17's "one Authorization
 *  Engine, never four separate ad-hoc mechanisms" rule applied to the
 *  frontend. */
export const permissionFramework = new PermissionFramework();
