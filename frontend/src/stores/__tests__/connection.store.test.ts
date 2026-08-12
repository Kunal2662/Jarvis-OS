import { beforeEach, describe, expect, it } from "vitest";
import {
  selectIsLive,
  selectIsOffline,
  useConnectionStore,
} from "@/stores/connection.store";

describe("useConnectionStore", () => {
  beforeEach(() => {
    useConnectionStore.setState({
      state: "idle",
      detail: "",
      socket: "not_configured",
      authenticated: false,
      hasAttempted: false,
    });
  });

  it("starts idle and unauthenticated, never optimistically ready", () => {
    const s = useConnectionStore.getState();
    expect(s.state).toBe("idle");
    expect(s.authenticated).toBe(false);
    expect(s.hasAttempted).toBe(false);
  });

  describe("selectIsOffline", () => {
    it("is false before anything has been attempted", () => {
      useConnectionStore.setState({ state: "unreachable", hasAttempted: false });
      expect(selectIsOffline(useConnectionStore.getState())).toBe(false);
    });

    it("is false while still connecting", () => {
      useConnectionStore.setState({ state: "connecting", hasAttempted: true });
      expect(selectIsOffline(useConnectionStore.getState())).toBe(false);
    });

    it("is true once an attempt has concluded unreachable", () => {
      useConnectionStore.setState({ state: "unreachable", hasAttempted: true });
      expect(selectIsOffline(useConnectionStore.getState())).toBe(true);
    });

    it("does not treat an auth failure as offline", () => {
      // The backend is answering; the app should say so rather than
      // claiming JARVIS is not running.
      useConnectionStore.setState({ state: "unauthenticated", hasAttempted: true });
      expect(selectIsOffline(useConnectionStore.getState())).toBe(false);
    });
  });

  describe("selectIsLive", () => {
    it("is true only in the ready state", () => {
      for (const state of ["idle", "connecting", "unreachable", "unauthenticated", "error"] as const) {
        useConnectionStore.setState({ state });
        expect(selectIsLive(useConnectionStore.getState())).toBe(false);
      }
      useConnectionStore.setState({ state: "ready" });
      expect(selectIsLive(useConnectionStore.getState())).toBe(true);
    });

    it("stays true through a socket reconnect", () => {
      // The REST session is fine; only the socket is re-establishing.
      // Dropping to "not live" here would blank every view for a second.
      useConnectionStore.setState({ state: "ready", socket: "reconnecting" });
      expect(selectIsLive(useConnectionStore.getState())).toBe(true);
    });
  });
});
