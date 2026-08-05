import { create } from "zustand";
import type { AgentStepPayload, AutomationStepPayload } from "@/services/websocket";

/**
 * Live agent and automation progress -- M8 Phase 2's "AI Integration" and
 * "Automation Integration" over the WebSocket relay.
 *
 * One store for both because they are the same shape of thing (a run
 * emitting ordered steps) consumed by the same kind of UI (a trace list),
 * and two near-identical stores would be the duplication this project's
 * architecture rules single out. They stay separately keyed and
 * separately clearable, so a caller never has to filter one out of the
 * other.
 *
 * **Token streaming is not here.** M10 split agent output deliberately:
 * step-level progress relays over this WebSocket as `agent.step`, while
 * token-level output is Server-Sent Events on `/api/v1/agent/stream`.
 * Mirroring tokens into a Zustand store would fight that design and
 * re-render the tree per token; the chat view consumes the SSE stream
 * directly when it is built.
 *
 * Both lists are capped. An agent loop can emit steps indefinitely, and
 * an unbounded array behind a live view is a memory leak with a
 * user-visible slowdown attached.
 */

const MAX_STEPS = 200;

export interface AgentStep extends AgentStepPayload {
  receivedAt: string;
}

export interface AutomationStep extends AutomationStepPayload {
  receivedAt: string;
}

interface AgentActivityShape {
  /** Newest last, matching the reading order of a trace. */
  agentSteps: AgentStep[];
  automationSteps: AutomationStep[];

  recordAgentStep: (payload: AgentStepPayload, receivedAt?: string) => void;
  recordAutomationStep: (payload: AutomationStepPayload, receivedAt?: string) => void;
  clearAgent: (threadId?: string) => void;
  clearAutomation: () => void;
}

export const useAgentActivityStore = create<AgentActivityShape>()((set) => ({
  agentSteps: [],
  automationSteps: [],

  recordAgentStep: (payload, receivedAt = new Date().toISOString()) =>
    set((s) => ({ agentSteps: [...s.agentSteps, { ...payload, receivedAt }].slice(-MAX_STEPS) })),

  recordAutomationStep: (payload, receivedAt = new Date().toISOString()) =>
    set((s) => ({
      automationSteps: [...s.automationSteps, { ...payload, receivedAt }].slice(-MAX_STEPS),
    })),

  /** Clearing one thread rather than all of them is the common case when
   *  a chat view unmounts; omitting `threadId` clears everything. */
  clearAgent: (threadId) =>
    set((s) => ({
      agentSteps: threadId ? s.agentSteps.filter((step) => step.thread_id !== threadId) : [],
    })),

  clearAutomation: () => set({ automationSteps: [] }),
}));

/** The steps for one agent thread, oldest first. */
export function selectThreadSteps(threadId: string) {
  return (s: AgentActivityShape): AgentStep[] =>
    s.agentSteps.filter((step) => step.thread_id === threadId);
}
