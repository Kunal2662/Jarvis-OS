/**
 * The three audiences JARVIS renders for -- M8 Phase 5, implementing
 * `ARCHITECTURE.md` §22.11 (Personal/Administrator accounts) and §22.12
 * (hidden backend operations).
 *
 * §22.12 is the binding rule this module exists to enforce:
 *
 * > Users never see provider names, routing decisions, internal agents,
 * > backend execution, API switching, or failover.
 *
 * That is not a preference about clutter. A personal user's product does
 * not contain the information, so any surface that can render it must
 * ask first. Centralising the question here means there is exactly one
 * answer, rather than each panel re-deciding what "advanced" means.
 *
 * **What is real today, and what is not.** The account model itself
 * (§22.11) is approved-but-not-built: the backend has no user table, no
 * roles and no `/api/v1/users`, and the backend is frozen. So
 * `administrator` is currently reachable only the same way `developer`
 * is -- through the existing session-only Developer Mode unlock, which
 * `stores/developer-mode.store.ts` has owned since Phase 1. When a real
 * account model ships, `resolveUserMode()` is the single function that
 * changes; every gate in the UI reads through it and none of them will
 * need touching.
 *
 * This is deliberately *stricter* than today's product needs. Nothing
 * regresses if the account model never arrives, and nothing leaks if it
 * does.
 */

/** Ordered least- to most-privileged; `atLeast()` relies on the order. */
export const USER_MODES = ["personal", "developer", "administrator"] as const;
export type UserMode = (typeof USER_MODES)[number];

const RANK: Record<UserMode, number> = {
  personal: 0,
  developer: 1,
  administrator: 2,
};

export function atLeast(current: UserMode, required: UserMode): boolean {
  return RANK[current] >= RANK[required];
}

/**
 * What a personal user must never be shown (§22.12), as a checklist
 * rather than prose so it can be asserted in a test.
 *
 * Each entry names a *category of information*, not a component. A panel
 * asks "may I show `provider_names`?" and gets one answer, so two panels
 * cannot disagree.
 */
export const RESTRICTED_INFORMATION = [
  "provider_names",
  "provider_routing",
  "internal_agents",
  "backend_execution",
  "api_names",
  "backend_services",
  "raw_debug",
] as const;
export type RestrictedInformation = (typeof RESTRICTED_INFORMATION)[number];

/** Everything in §22.12 requires at least Developer Mode. Administrator
 *  adds *management* surfaces (budgets, users, provider priority), not a
 *  different set of secrets to read. */
const MINIMUM_MODE: Record<RestrictedInformation, UserMode> = {
  provider_names: "developer",
  provider_routing: "developer",
  internal_agents: "developer",
  backend_execution: "developer",
  api_names: "developer",
  backend_services: "developer",
  raw_debug: "developer",
};

export function canReveal(mode: UserMode, information: RestrictedInformation): boolean {
  return atLeast(mode, MINIMUM_MODE[information]);
}

/**
 * The progress vocabulary §22.12 mandates in place of the real thing.
 *
 * A personal user watching an agent run sees these, not `planner` /
 * `tool_executor` / `critic`. The phrasing is fixed by the architecture
 * decision, so it lives here as data rather than being retyped at each
 * call site with slightly different wording.
 */
export const PROGRESS_PHRASES = [
  "Working…",
  "Thinking…",
  "Preparing response…",
  "Checking information…",
  "Almost ready…",
] as const;

/**
 * A stable, non-random progress phrase for a given step.
 *
 * Deterministic on purpose: a phrase picked at random would change on
 * every re-render, which reads as flickering rather than progress. The
 * index advances with the step number, so a longer run genuinely walks
 * through the vocabulary.
 */
export function progressPhraseFor(step: number): string {
  return PROGRESS_PHRASES[Math.abs(step) % PROGRESS_PHRASES.length];
}
