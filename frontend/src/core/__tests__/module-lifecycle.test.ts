import { describe, expect, it } from "vitest";
import { InvalidStateTransitionError, ModuleLifecycle } from "@/core/module-lifecycle";

describe("ModuleLifecycle", () => {
  it("starts in the given initial state", () => {
    const lifecycle = new ModuleLifecycle("test", "empty");
    expect(lifecycle.state).toBe("empty");
  });

  it("allows a legal transition", () => {
    const lifecycle = new ModuleLifecycle("test", "not_configured");
    lifecycle.transitionTo("connecting");
    expect(lifecycle.state).toBe("connecting");
  });

  it("rejects an illegal transition (mirrors the Python ModuleStateMachine)", () => {
    const lifecycle = new ModuleLifecycle("test", "not_configured");
    expect(() => lifecycle.transitionTo("syncing")).toThrow(InvalidStateTransitionError);
    // A rejected transition never mutates state.
    expect(lifecycle.state).toBe("not_configured");
  });

  it("always allows a self-transition", () => {
    const lifecycle = new ModuleLifecycle("test", "ready");
    expect(() => lifecycle.transitionTo("ready")).not.toThrow();
  });

  it("allows shutdown from any state", () => {
    for (const state of ["not_configured", "connecting", "ready", "error", "offline"] as const) {
      const lifecycle = new ModuleLifecycle("test", state);
      expect(lifecycle.canTransitionTo("shutdown")).toBe(true);
    }
  });

  it("shutdown is terminal -- no further transitions are legal", () => {
    const lifecycle = new ModuleLifecycle("test", "ready");
    lifecycle.transitionTo("shutdown");
    expect(lifecycle.canTransitionTo("connecting")).toBe(false);
    expect(lifecycle.canTransitionTo("ready")).toBe(false);
  });

  it("records every transition in order", () => {
    const lifecycle = new ModuleLifecycle("test", "not_configured");
    lifecycle.transitionTo("connecting");
    lifecycle.transitionTo("connected");
    lifecycle.transitionTo("ready");
    expect(lifecycle.getHistory().map((s) => s.state)).toEqual([
      "not_configured",
      "connecting",
      "connected",
      "ready",
    ]);
  });

  it("carries an error detail through an error transition", () => {
    const lifecycle = new ModuleLifecycle("test", "connecting");
    lifecycle.transitionTo("error", { error: "auth failed" });
    expect(lifecycle.moduleState.error).toBe("auth failed");
  });
});
