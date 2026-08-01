import { beforeEach, describe, expect, it, vi } from "vitest";
import { createModuleApiClient } from "@/core/interfaces/api-interface";

const fetchMock = vi.fn();
vi.stubGlobal("fetch", fetchMock);

function mockResponse(data: unknown, ok = true, status = 200) {
  return {
    ok,
    status,
    json: async () => ({ data }),
  } as Response;
}

describe("createModuleApiClient", () => {
  beforeEach(() => {
    fetchMock.mockReset();
  });

  it("scopes every request path under /<moduleId>/...", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse({ ok: true }));
    const client = createModuleApiClient("gmail");

    await client.get("/messages");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/gmail/messages");
  });

  it("never lets a module override the base path -- even an absolute-looking path stays scoped", async () => {
    fetchMock.mockResolvedValueOnce(mockResponse({ ok: true }));
    const client = createModuleApiClient("calendar");

    await client.get("events");

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/calendar/events");
  });

  it("uses the correct HTTP method per call", async () => {
    fetchMock.mockResolvedValue(mockResponse({ ok: true }));
    const client = createModuleApiClient("tasks");

    await client.post("/items", { title: "Buy milk" });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ title: "Buy milk" }));
  });
});
