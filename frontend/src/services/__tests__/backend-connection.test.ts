import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setApiBaseUrl } from "@/services/api/client";
import { resetSessionForTesting } from "@/services/api/session";
import {
  connectBackend,
  disconnectBackend,
  getBackendStatus,
  pingBackend,
  resetBackendStatusForTesting,
  subscribeToBackendStatus,
} from "@/services/backend-connection";
import { websocketManager } from "@/services/websocket";

/**
 * Offline support's real requirement is that the app can tell *why* it
 * has no data. These tests pin the three distinguishable outcomes --
 * unreachable, reachable-but-unauthenticated, and ready -- because
 * collapsing any two of them is what produces a UI that says "something
 * went wrong" when the truth is "JARVIS isn't running".
 */

const BASE = "http://127.0.0.1:8000/api/v1";

const SESSION = {
  session_id: "sess-1",
  conversation_id: null,
  thread_id: null,
  created_at: "2026-08-05T00:00:00Z",
  last_active_at: "2026-08-05T00:00:00Z",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;
let connectSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  setApiBaseUrl(BASE);
  resetSessionForTesting();
  resetBackendStatusForTesting();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  // The socket itself is `connection-manager`'s concern and has its own
  // tests; here we only care that it is opened with the session's token.
  connectSpy = vi.spyOn(websocketManager, "connect").mockImplementation(() => {});
  vi.spyOn(websocketManager, "disconnect").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("pingBackend", () => {
  it("is true when /health answers", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "ok", version: "0.28.0" }));
    await expect(pingBackend()).resolves.toBe(true);
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/health`);
  });

  it("is false when the process is not running", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(pingBackend()).resolves.toBe(false);
  });

  it("is false on a non-2xx rather than throwing", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 503 }));
    await expect(pingBackend()).resolves.toBe(false);
  });

  it("does not send the Authorization header", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ status: "ok" }));
    await pingBackend();
    expect(fetchMock.mock.calls[0][1]?.headers).toBeUndefined();
  });
});

describe("connectBackend", () => {
  it("reaches ready and opens the socket with the session token", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "ok" })) // /health
      .mockResolvedValueOnce(jsonResponse({ data: SESSION })); // POST /sessions

    const status = await connectBackend();

    expect(status.state).toBe("ready");
    expect(status.authenticated).toBe(true);
    expect(status.detail).toBe("");
    expect(connectSpy).toHaveBeenCalledWith("sess-1");
  });

  it("reports unreachable without attempting a session", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const status = await connectBackend();

    expect(status.state).toBe("unreachable");
    expect(status.detail).toBe("The JARVIS backend is not running.");
    expect(status.authenticated).toBe(false);
    expect(connectSpy).not.toHaveBeenCalled();
    // Only the ping happened -- no point asking for a session from a
    // process that is not answering.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("reports unauthenticated when the backend is up but refuses a session", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ detail: "Sessions are disabled" }, 403));

    const status = await connectBackend();

    expect(status.state).toBe("unauthenticated");
    expect(status.detail).toBe("Sessions are disabled");
    expect(connectSpy).not.toHaveBeenCalled();
  });

  it("passes through connecting on the way", async () => {
    const seen: string[] = [];
    subscribeToBackendStatus((status) => seen.push(status.state));
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ data: SESSION }));

    await connectBackend();

    expect(seen).toContain("connecting");
    expect(seen.at(-1)).toBe("ready");
  });

  it("is safe to call again as the reconnect path", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ data: SESSION }));
    await connectBackend();

    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ data: SESSION }));
    const status = await connectBackend();

    expect(status.state).toBe("ready");
  });
});

describe("disconnectBackend", () => {
  it("returns to idle and drops authentication", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ status: "ok" }))
      .mockResolvedValueOnce(jsonResponse({ data: SESSION }));
    await connectBackend();

    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await disconnectBackend();

    expect(getBackendStatus().state).toBe("idle");
    expect(getBackendStatus().authenticated).toBe(false);
  });
});

describe("subscribers", () => {
  it("stop receiving updates once unsubscribed", async () => {
    const seen: string[] = [];
    const unsubscribe = subscribeToBackendStatus((status) => seen.push(status.state));
    unsubscribe();

    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await connectBackend();

    expect(seen).toEqual([]);
  });
});
