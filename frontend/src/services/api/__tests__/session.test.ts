import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getAuthToken, setApiBaseUrl } from "@/services/api/client";
import {
  createSession,
  endSession,
  ensureSession,
  getSession,
  getSessionToken,
  resetSessionForTesting,
} from "@/services/api/session";

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

beforeEach(() => {
  setApiBaseUrl(BASE);
  resetSessionForTesting();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createSession", () => {
  it("POSTs anonymously and installs the token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: SESSION }));

    const session = await createSession();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/sessions`);
    expect(init.method).toBe("POST");
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
    expect(session.session_id).toBe("sess-1");
    expect(getAuthToken()).toBe("sess-1");
    expect(getSessionToken()).toBe("sess-1");
  });

  it("identifies the client in metadata", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: SESSION }));
    await createSession();
    expect(JSON.parse(fetchMock.mock.calls[0][1].body as string)).toEqual({
      conversation_id: null,
      thread_id: null,
      metadata: { client: "jarvis-desktop" },
    });
  });
});

describe("ensureSession", () => {
  it("creates one when none exists", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: SESSION }));

    await ensureSession();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  });

  it("reuses a live session with one validating GET", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: SESSION }));
    await createSession();
    fetchMock.mockClear();

    fetchMock.mockResolvedValue(jsonResponse({ data: { ...SESSION, last_active_at: "later" } }));
    const session = await ensureSession();

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/sessions/sess-1`);
    expect(session.last_active_at).toBe("later");
  });

  it("replaces a session the backend has forgotten", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: SESSION }));
    await createSession();
    fetchMock.mockClear();

    // The backend restarted: validation 404s, so a fresh session is
    // created rather than the app carrying on with a dead token.
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "Unknown session" }, 404))
      .mockResolvedValueOnce(jsonResponse({ data: { ...SESSION, session_id: "sess-2" } }));

    const session = await ensureSession();

    expect(session.session_id).toBe("sess-2");
    expect(getAuthToken()).toBe("sess-2");
  });

  it("propagates a genuine outage rather than looping", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(ensureSession()).rejects.toThrow();
  });
});

describe("endSession", () => {
  it("DELETEs server-side and clears the token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: SESSION }));
    await createSession();
    fetchMock.mockClear();
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await endSession();

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/sessions/sess-1`);
    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
    expect(getAuthToken()).toBeNull();
    expect(getSession()).toBeNull();
  });

  it("clears the local token even when the server refuses the close", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: SESSION }));
    await createSession();
    fetchMock.mockResolvedValue(jsonResponse({ detail: "nope" }, 500));

    await expect(endSession()).rejects.toThrow();
    expect(getAuthToken()).toBeNull();
  });

  it("is a no-op with no session", async () => {
    await endSession();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(getAuthToken()).toBeNull();
  });
});

describe("token storage", () => {
  it("never writes the token to localStorage", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: SESSION }));
    await createSession();

    // The backend's session table does not survive a restart and M11
    // Task Group F locked `/sessions/{id}` to its own bearer, so the
    // token stays in memory for one page lifetime, by design.
    const persisted = Object.keys(localStorage).filter((key) =>
      String(localStorage.getItem(key)).includes("sess-1"),
    );
    expect(persisted).toEqual([]);
  });
});
