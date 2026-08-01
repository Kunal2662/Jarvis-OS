/**
 * The Automation Interface (Task 11) -- every module MAY implement this
 * to expose itself to M4/M7's Automation Engine and M10's AI
 * Orchestrator (ARCHITECTURE.md section 16). Pure interface: no
 * workflow execution, no `ActionExecutor` logic, no rollback mechanics
 * live here -- that is entirely backend scope. This interface only
 * declares *what a module can be asked to do*, never *how*.
 */

export interface AutomationAction {
  id: string;
  label: string;
  /** Whether an Undo exists for this action, matching the backend's
   *  own `Step`/`ActionExecutor` rollback distinction
   *  (ARCHITECTURE.md section 16) -- never assumed reversible by
   *  default. */
  reversible: boolean;
}

export interface AutomationTrigger {
  id: string;
  label: string;
  /** What this trigger fires in response to -- a description only;
   *  the actual trigger evaluation (schedule, webhook, event) is M7's
   *  Scheduler/backend concern. */
  description: string;
}

export interface ModuleEvent {
  id: string;
  label: string;
}

/** Implemented by a module that wants Automation Engine / AI
 *  Orchestrator participation. */
export interface AutomationIntegration {
  /** Actions this module exposes as automatable steps -- matches the
   *  manifest's own `automationSupport.actions` (module-manifest.ts),
   *  as a live method for the same reason `VoiceIntegration` has one:
   *  availability can depend on current state, not just static config. */
  getAutomationActions(): AutomationAction[];
  /** Triggers this module can fire a workflow from (e.g. "new item
   *  arrived") -- surfaced to M7's Workflow Builder once it exists,
   *  never executed here. */
  getAutomationTriggers(): AutomationTrigger[];
  /** Events this module publishes onto the Event Bus / WebSocket layer
   *  (ARCHITECTURE.md sections 6-7) that a workflow could react to. */
  getModuleEvents(): ModuleEvent[];
  /** Whether this module's actions can participate in a multi-step
   *  M7 Workflow (vs. only being callable standalone) -- most modules
   *  should return `true`; a module returns `false` only if its
   *  actions have hard sequencing requirements incompatible with
   *  wave-based parallel dispatch (ARCHITECTURE.md section 16). */
  supportsWorkflows(): boolean;
}
