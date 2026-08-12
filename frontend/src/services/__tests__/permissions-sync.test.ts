import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setApiBaseUrl } from "@/services/api/client";
import { permissionFramework } from "@/core/permission-framework";
import {
  denyPermission,
  grantPermission,
  isKnownScope,
  loadPendingPermissions,
  revokePermission,
  syncPluginPermissions,
} from "@/services/permissions-sync";

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
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  // The framework is process-wide by design; clear the scopes these
  // tests touch so one case cannot leak into the next.
  for (const scope of ["network", "filesystem", "memory.read"] as const) {
    permissionFramework.revoke("weather", scope);
    permissionFramework.revoke("other", scope);
  }
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("isKnownScope", () => {
  it("accepts the ten scopes both sides share", () => {
    for (const scope of [
      "network",
      "filesystem",
      "hotkey",
      "agent_tools",
      "voice.stt",
      "voice.tts",
      "memory.read",
      "memory.write",
      "smart_home",
      "notifications",
    ]) {
      expect(isKnownScope(scope)).toBe(true);
    }
  });

  it("rejects anything else", () => {
    expect(isKnownScope("database.drop")).toBe(false);
  });
});

describe("syncPluginPermissions", () => {
  it("mirrors granted and denied into the framework", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({
        data: [
          { plugin_id: "weather", scope: "network", state: "granted" },
          { plugin_id: "weather", scope: "filesystem", state: "denied" },
        ],
      }),
    );

    await syncPluginPermissions("weather");

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/plugins/weather/permissions`);
    expect(permissionFramework.isGranted("weather", "network")).toBe(true);
    expect(permissionFramework.isGranted("weather", "filesystem")).toBe(false);
    expect(permissionFramework.getGrant("weather", "filesystem")?.decision).toBe("always_deny");
  });

  it("leaves a pending scope absent rather than recording a denial", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ data: [{ plugin_id: "weather", scope: "memory.read", state: "pending" }] }),
    );

    await syncPluginPermissions("weather");

    // Absent, not denied -- so a prompt is still the right next step.
    expect(permissionFramework.getGrant("weather", "memory.read")).toBeNull();
    expect(permissionFramework.isGranted("weather", "memory.read")).toBe(false);
  });

  it("ignores a scope outside the shared vocabulary", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ data: [{ plugin_id: "weather", scope: "database.drop", state: "granted" }] }),
    );

    await expect(syncPluginPermissions("weather")).resolves.toHaveLength(1);
  });
});

describe("write-through", () => {
  it("asks the backend before updating the local cache", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: { state: "granted" } }));

    await grantPermission("weather", "network");

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/plugins/weather/permissions/network/grant`);
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(permissionFramework.isGranted("weather", "network")).toBe(true);
  });

  it("leaves the cache untouched when the backend refuses", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Unknown plugin" }, 404));

    await expect(grantPermission("weather", "network")).rejects.toThrow("Unknown plugin");

    // Never show a permission as held that the enforcing process does
    // not recognise.
    expect(permissionFramework.getGrant("weather", "network")).toBeNull();
  });

  it("deny and revoke hit their own routes", async () => {
    // A fresh Response per call: a body stream can only be read once, so
    // a single shared `mockResolvedValue` would hand the second request
    // an already-consumed body.
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ data: {} })));

    await denyPermission("weather", "filesystem");
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/plugins/weather/permissions/filesystem/deny`);
    expect(permissionFramework.isGranted("weather", "filesystem")).toBe(false);

    await revokePermission("weather", "filesystem");
    expect(fetchMock.mock.calls[1][0]).toBe(`${BASE}/plugins/weather/permissions/filesystem/revoke`);
    expect(permissionFramework.getGrant("weather", "filesystem")).toBeNull();
  });
});

describe("loadPendingPermissions", () => {
  it("reads the operator's queue", async () => {
    fetchMock.mockResolvedValue(
      jsonResponse({ data: [{ plugin_id: "weather", scope: "network", state: "pending" }] }),
    );

    await expect(loadPendingPermissions()).resolves.toEqual([
      { plugin_id: "weather", scope: "network", state: "pending" },
    ]);
    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/permissions/pending`);
  });
});
