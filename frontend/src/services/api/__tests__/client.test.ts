import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiList,
  apiRequest,
  apiVoid,
  getApiBaseUrl,
  getAuthToken,
  setApiBaseUrl,
  setAuthToken,
} from "@/services/api/client";

/**
 * The client's job is to be right about what the *backend actually
 * sends*. Phase 1's version was written against `ARCHITECTURE.md`'s
 * specified shapes and got two of them wrong, so these tests assert
 * against real response bodies -- the offset `meta` M11 Task Group F
 * ships and the `{"detail": "..."}` every FastAPI route raises -- not
 * against the spec.
 */

const BASE = "http://127.0.0.1:8000/api/v1";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  setApiBaseUrl(BASE);
  setAuthToken(null);
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("configuration", () => {
  it("defaults to the local backend", () => {
    expect(getApiBaseUrl()).toBe(BASE);
  });

  it("strips a trailing slash so paths never double up", () => {
    setApiBaseUrl("http://example.test/api/v1/");
    expect(getApiBaseUrl()).toBe("http://example.test/api/v1");
    setApiBaseUrl(BASE);
  });
});

describe("authentication", () => {
  it("sends the Bearer token once set", async () => {
    setAuthToken("session-123");
    expect(getAuthToken()).toBe("session-123");
    fetchMock.mockResolvedValue(jsonResponse({ data: { id: "w1" } }));

    await apiRequest("/workspaces/w1");

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer session-123");
  });

  it("omits the header for an anonymous request", async () => {
    setAuthToken("session-123");
    fetchMock.mockResolvedValue(jsonResponse({ data: { session_id: "s" } }));

    await apiRequest("/sessions", { method: "POST", anonymous: true, body: {} });

    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });

  it("omits the header when no token is installed", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: null }));
    await apiRequest("/health");
    const [, init] = fetchMock.mock.calls[0];
    expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
  });
});

describe("query strings", () => {
  it("serialises values and drops undefined/null", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: [], meta: {} }));

    await apiList("/tasks", {
      query: { workspace_id: "w1", limit: 50, offset: 0, status: undefined, tag: null },
    });

    const [url] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/tasks?workspace_id=w1&limit=50&offset=0`);
  });

  it("emits no `?` when every value was omitted", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: [], meta: {} }));
    await apiList("/tasks", { query: { status: undefined } });
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/tasks`);
  });
});

describe("envelope handling", () => {
  it("unwraps `data` for a single resource", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: { id: "w1", name: "Work" } }));
    await expect(apiRequest("/workspaces/w1")).resolves.toEqual({ id: "w1", name: "Work" });
  });

  it("returns undefined for a 204 without parsing a body", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiRequest("/sessions/s1")).resolves.toBeUndefined();
  });

  it("keeps the backend's real offset pagination meta", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        data: [{ id: "t1" }, { id: "t2" }],
        meta: { count: 2, limit: 50, offset: 0, has_more: true },
      }),
    );

    const page = await apiList<{ id: string }>("/tasks");

    expect(page.items).toHaveLength(2);
    expect(page.meta).toEqual({ count: 2, limit: 50, offset: 0, has_more: true });
  });

  it("fills in a sane meta when a route sends none", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: [{ id: "a" }] }));
    const page = await apiList<{ id: string }>("/integrations");
    expect(page.meta).toEqual({ count: 1, limit: 1, offset: 0, has_more: false });
  });

  it("preserves extra meta keys a route adds", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ data: [], meta: { count: 0, limit: 50, offset: 0, has_more: false, total_bytes: 12 } }),
    );
    const page = await apiList("/files");
    expect(page.meta.total_bytes).toBe(12);
  });
});

describe("error handling", () => {
  it("uses FastAPI's `detail` as the message", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Workspace not found" }, 404));

    const error = await apiRequest("/workspaces/nope").catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe("Workspace not found");
    expect((error as ApiError).status).toBe(404);
    expect((error as ApiError).isOffline).toBe(false);
  });

  it("marks a 401 as UNAUTHENTICATED with a recovery action", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Invalid session" }, 401));
    const error = (await apiRequest("/tasks").catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("UNAUTHENTICATED");
    expect(error.recoveryAction).toBe("Sign in again.");
  });

  it("treats 5xx as retryable and 4xx as not", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "boom" }, 503));
    const server = (await apiRequest("/tasks").catch((e: unknown) => e)) as ApiError;
    expect(server.retryable).toBe(true);

    fetchMock.mockResolvedValue(jsonResponse({ detail: "bad input" }, 400));
    const client = (await apiRequest("/tasks").catch((e: unknown) => e)) as ApiError;
    expect(client.retryable).toBe(false);
  });

  it("still understands the richer `error` envelope", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: "WORKSPACE_LOCKED",
            message: "Locked",
            recovery_action: "Unlock it.",
            severity: "warning",
            retryable: false,
          },
        },
        409,
      ),
    );
    const error = (await apiRequest("/workspaces/w1").catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("WORKSPACE_LOCKED");
    expect(error.recoveryAction).toBe("Unlock it.");
  });

  it("reports a 2xx that is not an envelope as an error, not a TypeError", async () => {
    fetchMock.mockResolvedValue(new Response("not json", { status: 200 }));

    const error = (await apiRequest("/workspaces/w1").catch((e: unknown) => e)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("MALFORMED_RESPONSE");
    expect(error.message).toContain("/workspaces/w1");
  });

  it("reports a malformed collection response the same way", async () => {
    fetchMock.mockResolvedValue(new Response("not json", { status: 200 }));

    const error = (await apiList("/tasks").catch((e: unknown) => e)) as ApiError;

    expect(error).toBeInstanceOf(ApiError);
    expect(error.code).toBe("MALFORMED_RESPONSE");
  });

  it("falls back when the body is not JSON at all", async () => {
    fetchMock.mockResolvedValue(new Response("<html>502</html>", { status: 502 }));
    const error = (await apiRequest("/tasks").catch((e: unknown) => e)) as ApiError;
    expect(error.code).toBe("HTTP_502");
    expect(error.message).toBe("Request failed with status 502.");
  });

  it("distinguishes unreachable from a server error", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const error = (await apiRequest("/tasks").catch((e: unknown) => e)) as ApiError;

    expect(error.code).toBe("BACKEND_UNREACHABLE");
    expect(error.isOffline).toBe(true);
    expect(error.status).toBe(0);
  });
});

describe("apiVoid", () => {
  it("resolves on any 2xx without needing a body", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    await expect(apiVoid("/sessions/s1", { method: "DELETE" })).resolves.toBeUndefined();
  });

  it("throws the backend's reason on failure", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Not your session" }, 403));
    await expect(apiVoid("/sessions/s1", { method: "DELETE" })).rejects.toThrow("Not your session");
  });
});
