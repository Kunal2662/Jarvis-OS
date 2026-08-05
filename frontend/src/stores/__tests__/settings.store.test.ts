import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { setApiBaseUrl } from "@/services/api/client";
import { useSettingsStore } from "@/stores/settings.store";

const BASE = "http://127.0.0.1:8000/api/v1";

const TREE = {
  ui: { theme: "jarvis", language: "en" },
  llm: { provider: "openai", api_key: "**********" },
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
  useSettingsStore.setState({ tree: null, loading: false, error: null });
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("useSettingsStore", () => {
  it("starts with no tree rather than an empty object", () => {
    // `null` is "not loaded"; `{}` would be indistinguishable from a
    // backend that legitimately returned nothing.
    expect(useSettingsStore.getState().tree).toBeNull();
  });

  it("loads the backend's redacted tree", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: TREE, meta: { read_only: true } }));

    await useSettingsStore.getState().load();

    expect(fetchMock.mock.calls[0][0]).toBe(`${BASE}/settings`);
    expect(useSettingsStore.getState().tree).toEqual(TREE);
    expect(useSettingsStore.getState().loading).toBe(false);
    expect(useSettingsStore.getState().error).toBeNull();
  });

  it("reads a dotted key out of the loaded tree", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: TREE }));
    await useSettingsStore.getState().load();

    expect(useSettingsStore.getState().get("ui.theme")).toBe("jarvis");
    expect(useSettingsStore.getState().get("llm.provider")).toBe("openai");
  });

  it("returns undefined for an unknown key or an unloaded tree", () => {
    expect(useSettingsStore.getState().get("ui.theme")).toBeUndefined();
    useSettingsStore.setState({ tree: TREE });
    expect(useSettingsStore.getState().get("ui.nope")).toBeUndefined();
    expect(useSettingsStore.getState().get("nope.nope.nope")).toBeUndefined();
  });

  it("does not walk into a non-object value", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ data: TREE }));
    await useSettingsStore.getState().load();
    expect(useSettingsStore.getState().get("ui.theme.deeper")).toBeUndefined();
  });

  it("keeps a load failure in place rather than throwing", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Settings unavailable" }, 500));

    await expect(useSettingsStore.getState().load()).resolves.toBeUndefined();

    expect(useSettingsStore.getState().error).toContain("Settings unavailable");
    expect(useSettingsStore.getState().tree).toBeNull();
    expect(useSettingsStore.getState().loading).toBe(false);
  });

  it("clears a previous error on a fresh attempt", async () => {
    useSettingsStore.setState({ error: "stale" });
    fetchMock.mockResolvedValue(jsonResponse({ data: TREE }));

    await useSettingsStore.getState().load();

    expect(useSettingsStore.getState().error).toBeNull();
  });

  it("stores what the server sent without re-redacting", async () => {
    // Redaction is the backend's job (`public_snapshot()`); a second
    // layer here would imply the first is untrusted.
    fetchMock.mockResolvedValue(jsonResponse({ data: TREE }));
    await useSettingsStore.getState().load();
    expect(useSettingsStore.getState().get("llm.api_key")).toBe("**********");
  });
});
