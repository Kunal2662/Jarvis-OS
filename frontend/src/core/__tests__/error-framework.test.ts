import { describe, expect, it } from "vitest";
import { deriveViewState } from "@/core/error-framework";
import type { ModuleState } from "@/core/module-lifecycle";
import type { ConnectionState } from "@/core/module-lifecycle";

function state(state: ConnectionState): ModuleState {
  return { state, detail: "", error: null, updatedAt: new Date().toISOString() };
}

describe("deriveViewState", () => {
  it("maps not_configured to config_required", () => {
    expect(deriveViewState({ moduleState: state("not_configured") })).toBe("config_required");
  });

  it("maps authenticating to auth_required", () => {
    expect(deriveViewState({ moduleState: state("authenticating") })).toBe("auth_required");
  });

  it("maps connecting/syncing to loading", () => {
    expect(deriveViewState({ moduleState: state("connecting") })).toBe("loading");
    expect(deriveViewState({ moduleState: state("syncing") })).toBe("loading");
  });

  it("maps ready/connected to ready", () => {
    expect(deriveViewState({ moduleState: state("ready") })).toBe("ready");
    expect(deriveViewState({ moduleState: state("connected") })).toBe("ready");
  });

  it("maps error to error", () => {
    expect(deriveViewState({ moduleState: state("error") })).toBe("error");
  });

  it("a denied required permission wins over any lifecycle state", () => {
    expect(deriveViewState({ moduleState: state("ready"), requiredPermissionDenied: true })).toBe(
      "permission_denied",
    );
  });
});
