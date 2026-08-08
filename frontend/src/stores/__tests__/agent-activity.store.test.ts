import { beforeEach, describe, expect, it } from "vitest";
import { selectThreadSteps, useAgentActivityStore } from "@/stores/agent-activity.store";

function agentStep(threadId: string, step: number) {
  return { thread_id: threadId, step, node: `n${step}`, status: "ok", detail: "" };
}

describe("useAgentActivityStore", () => {
  beforeEach(() => {
    useAgentActivityStore.setState({ agentSteps: [], automationSteps: [] });
  });

  it("starts empty", () => {
    expect(useAgentActivityStore.getState().agentSteps).toEqual([]);
    expect(useAgentActivityStore.getState().automationSteps).toEqual([]);
  });

  it("appends agent steps newest last", () => {
    const store = useAgentActivityStore.getState();
    store.recordAgentStep(agentStep("t1", 1));
    store.recordAgentStep(agentStep("t1", 2));
    expect(useAgentActivityStore.getState().agentSteps.map((s) => s.step)).toEqual([1, 2]);
  });

  it("stamps receivedAt, defaulting to now", () => {
    useAgentActivityStore.getState().recordAgentStep(agentStep("t1", 1), "2026-08-05T00:00:00Z");
    expect(useAgentActivityStore.getState().agentSteps[0].receivedAt).toBe("2026-08-05T00:00:00Z");

    useAgentActivityStore.getState().recordAgentStep(agentStep("t1", 2));
    expect(useAgentActivityStore.getState().agentSteps[1].receivedAt).toMatch(/^\d{4}-/);
  });

  it("caps the list so a long-running agent cannot grow it without bound", () => {
    const store = useAgentActivityStore.getState();
    for (let i = 0; i < 250; i += 1) store.recordAgentStep(agentStep("t1", i));

    const steps = useAgentActivityStore.getState().agentSteps;
    expect(steps).toHaveLength(200);
    // The cap drops the oldest, keeping the most recent window.
    expect(steps[0].step).toBe(50);
    expect(steps.at(-1)?.step).toBe(249);
  });

  it("caps automation steps the same way", () => {
    const store = useAgentActivityStore.getState();
    for (let i = 0; i < 250; i += 1) {
      store.recordAutomationStep({ step_id: `s${i}`, action: "x", status: "ok" });
    }
    expect(useAgentActivityStore.getState().automationSteps).toHaveLength(200);
  });

  it("clears one thread without touching another", () => {
    const store = useAgentActivityStore.getState();
    store.recordAgentStep(agentStep("t1", 1));
    store.recordAgentStep(agentStep("t2", 1));

    useAgentActivityStore.getState().clearAgent("t1");

    expect(useAgentActivityStore.getState().agentSteps.map((s) => s.thread_id)).toEqual(["t2"]);
  });

  it("clears every thread when none is named", () => {
    const store = useAgentActivityStore.getState();
    store.recordAgentStep(agentStep("t1", 1));
    store.recordAgentStep(agentStep("t2", 1));

    useAgentActivityStore.getState().clearAgent();

    expect(useAgentActivityStore.getState().agentSteps).toEqual([]);
  });

  it("keeps the two kinds of run independent", () => {
    const store = useAgentActivityStore.getState();
    store.recordAgentStep(agentStep("t1", 1));
    store.recordAutomationStep({ step_id: "s1", action: "x", status: "ok" });

    useAgentActivityStore.getState().clearAutomation();

    expect(useAgentActivityStore.getState().agentSteps).toHaveLength(1);
    expect(useAgentActivityStore.getState().automationSteps).toEqual([]);
  });

  it("selectThreadSteps filters to one thread", () => {
    const store = useAgentActivityStore.getState();
    store.recordAgentStep(agentStep("t1", 1));
    store.recordAgentStep(agentStep("t2", 1));
    store.recordAgentStep(agentStep("t1", 2));

    const steps = selectThreadSteps("t1")(useAgentActivityStore.getState());
    expect(steps.map((s) => s.step)).toEqual([1, 2]);
  });
});
