/**
 * The Module State Machine -- the frontend port of the shipped Python
 * `domain/app_state/models.py` (`ConnectionState`) and
 * `domain/app_state/machine.py` (`ModuleStateMachine`), per
 * ARCHITECTURE.md section 4. Same states, same values, same transition
 * graph -- not redesigned, only ported -- plus one new state this phase
 * adds: `SHUTDOWN`, a terminal state every module can reach from
 * anywhere, needed because `BaseApplication.shutdown()` (Task 1) has no
 * Python-side equivalent to model (the Python state machine never had a
 * "the whole app is closing" state; the frontend one needs it because
 * `BaseApplication` instances outlive route mounts/unmounts and need an
 * explicit terminal marker).
 *
 * No module may invent a custom state outside this set -- the same
 * binding rule ARCHITECTURE.md section 4 states, now enforced in code:
 * `ModuleLifecycle.transitionTo()` throws `InvalidStateTransitionError`
 * for anything not in `TRANSITIONS`, exactly like the Python
 * `ModuleStateMachine` does.
 */

export type ConnectionState =
  | "not_installed"
  | "not_configured"
  | "disconnected"
  | "connecting"
  | "authenticating"
  | "connected"
  | "syncing"
  | "ready"
  | "empty"
  | "offline"
  | "error"
  | "shutdown";

export interface ModuleState {
  state: ConnectionState;
  detail: string;
  error: string | null;
  updatedAt: string;
}

export class InvalidStateTransitionError extends Error {
  constructor(moduleId: string, from: ConnectionState, to: ConnectionState) {
    super(`${moduleId}: cannot move from "${from}" to "${to}"`);
    this.name = "InvalidStateTransitionError";
  }
}

/**
 * Legal next states per current state -- ported verbatim from Python's
 * `_TRANSITIONS` dict, extended with every state's implicit `-> shutdown`
 * edge (added once, below, rather than repeated in every entry).
 */
const BASE_TRANSITIONS: Record<Exclude<ConnectionState, "shutdown">, ConnectionState[]> = {
  not_installed: ["not_configured"],
  not_configured: ["connecting"],
  connecting: ["authenticating", "connected", "error"],
  authenticating: ["connected", "error"],
  connected: ["syncing", "ready", "empty", "error"],
  syncing: ["ready", "empty", "error", "offline"],
  ready: ["syncing", "empty", "offline", "error", "disconnected"],
  empty: ["syncing", "ready", "offline", "error", "disconnected"],
  offline: ["connecting", "syncing", "ready", "empty", "disconnected", "error"],
  error: ["connecting", "disconnected", "not_configured"],
  disconnected: ["connecting", "not_configured"],
};

function buildTransitions(): Record<ConnectionState, readonly ConnectionState[]> {
  const entries = Object.entries(BASE_TRANSITIONS) as [Exclude<ConnectionState, "shutdown">, ConnectionState[]][];
  const transitions: Partial<Record<ConnectionState, readonly ConnectionState[]>> = { shutdown: [] };
  for (const [state, targets] of entries) {
    transitions[state] = [...targets, "shutdown"];
  }
  return transitions as Record<ConnectionState, readonly ConnectionState[]>;
}

export const TRANSITIONS: Record<ConnectionState, readonly ConnectionState[]> = buildTransitions();

/**
 * Owns one module's current lifecycle position, exactly like Python's
 * `ModuleStateMachine`. Every future module's `BaseApplication` instance
 * holds one of these rather than a bare state field, for the same reason
 * the Python original does: an illegal jump (e.g. `not_configured`
 * straight to `syncing`) raises instead of silently letting the UI
 * render a state that was never actually reached.
 */
export class ModuleLifecycle {
  private readonly moduleId: string;
  private current: ModuleState;
  private readonly history: ModuleState[] = [];

  constructor(moduleId: string, initial: ConnectionState = "not_configured") {
    this.moduleId = moduleId;
    this.current = { state: initial, detail: "", error: null, updatedAt: new Date().toISOString() };
    this.history.push(this.current);
  }

  get state(): ConnectionState {
    return this.current.state;
  }

  get moduleState(): ModuleState {
    return this.current;
  }

  canTransitionTo(target: ConnectionState): boolean {
    if (target === this.current.state) return true;
    return TRANSITIONS[this.current.state].includes(target);
  }

  transitionTo(target: ConnectionState, options: { detail?: string; error?: string } = {}): ModuleState {
    if (!this.canTransitionTo(target)) {
      throw new InvalidStateTransitionError(this.moduleId, this.current.state, target);
    }
    this.current = {
      state: target,
      detail: options.detail ?? "",
      error: options.error ?? null,
      updatedAt: new Date().toISOString(),
    };
    this.history.push(this.current);
    return this.current;
  }

  /** Every state this machine has been in, oldest first -- diagnostic/
   *  Developer Mode use (Task 16), never drives application logic. */
  getHistory(): readonly ModuleState[] {
    return this.history;
  }
}

/**
 * Default starting state per module *category*, mirroring Python's
 * `MODULE_DEFAULT_STATES` -- connected-type modules (an external account)
 * start `not_configured`; local-only modules (no "connection" concept)
 * start `empty`. A module manifest (Task 4) declares its own category,
 * which `BaseApplication` (Task 1) uses to pick the right default here.
 */
export const DEFAULT_STATE_BY_CATEGORY = {
  connected: "not_configured",
  local: "empty",
} as const satisfies Record<string, ConnectionState>;
