/**
 * The AI Integration Interface (Task 9) -- every module MAY implement
 * this to participate in M10's AI Orchestrator (ARCHITECTURE.md section
 * 15). Pure interface, zero implementation: no LLM call, no prompt, no
 * tool-execution logic lives here or anywhere in `core/` -- that is
 * entirely backend (M10) scope, reached only through the API Interface
 * (Task 12) once a module actually implements this.
 */

export interface AIContext {
  moduleId: string;
  /** A short, structured snapshot of this module's current state --
   *  never raw UI state, never PII beyond what the module's own data
   *  already contains. Shape is module-specific; the AI Orchestrator
   *  (M10) treats it as opaque context, not a schema it validates. */
  summary: Record<string, unknown>;
}

export interface SuggestedAction {
  id: string;
  label: string;
  /** The automation action id (see automation-integration.ts) this
   *  suggestion would trigger if accepted -- never executed
   *  automatically, always a user-confirmed action. */
  automationActionId: string;
}

/** Implemented by a module that wants AI Orchestrator participation.
 *  Optional -- a module with no AI-relevant state simply doesn't
 *  implement this interface. */
export interface AIIntegration {
  /** Whether this module currently permits AI access -- checks
   *  `agent_tools` in `permission-framework.ts`, never assumes yes. */
  canUseAI(): boolean;
  /** The context this module contributes to the AI Orchestrator's
   *  Context Engine (ARCHITECTURE.md section 15) when its data is
   *  relevant to the current request. */
  getAIContext(): AIContext;
  /** Actions this module could suggest right now, given its own
   *  current state -- surfaced to the user, never auto-executed. */
  getSuggestedActions(): SuggestedAction[];
  /** Executes one of `getSuggestedActions()`'s actions, after the user
   *  has explicitly confirmed it -- routes through the Automation
   *  Interface (Task 11), never implements the action itself here. */
  performAIAction(actionId: string): Promise<void>;
}
