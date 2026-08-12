import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GlobalSearchPanel } from "@/features/search/global-search-panel";
import { setApiBaseUrl } from "@/services/api/client";
import { useConnectionStore } from "@/stores/connection.store";

/**
 * Global Search must query the *real* `POST /api/v1/search` and must not
 * pretend to work offline. Both are asserted here, because a search box
 * that silently returns nothing is indistinguishable from one that
 * searched and found nothing.
 */

const BASE = "http://127.0.0.1:8000/api/v1";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

const RESULT = {
  id: "n1",
  title: "Quarterly plan",
  content: "Ship the workspace framework.",
  source: "notes",
  score: 0.9,
  uri: "jarvis://notes/n1",
  metadata: {},
};

let fetchMock: ReturnType<typeof vi.fn>;

function setConnection(state: "ready" | "unreachable") {
  useConnectionStore.setState({
    state,
    detail: "",
    socket: "connected",
    authenticated: state === "ready",
    hasAttempted: true,
  });
}

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  setApiBaseUrl(BASE);
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  setConnection("ready");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("GlobalSearchPanel", () => {
  it("prompts rather than searching an empty query", () => {
    render(<GlobalSearchPanel />);

    expect(screen.getByText(/Search across your workspaces/)).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("does not fire a request below the minimum query length", async () => {
    const user = userEvent.setup();
    render(<GlobalSearchPanel />);

    await user.type(screen.getByLabelText("Search across JARVIS"), "a");

    await new Promise((resolve) => setTimeout(resolve, 400));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("queries the real backend search endpoint", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(jsonResponse({ data: [RESULT] }));

    render(<GlobalSearchPanel />);
    await user.type(screen.getByLabelText("Search across JARVIS"), "plan");

    expect(await screen.findByText("Quarterly plan")).toBeInTheDocument();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`${BASE}/search`);
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toMatchObject({ query: "plan", top_k: 30 });
  });

  it("labels each result with the backend source that produced it", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(jsonResponse({ data: [RESULT] }));

    render(<GlobalSearchPanel />);
    await user.type(screen.getByLabelText("Search across JARVIS"), "plan");

    expect(await screen.findByText("notes")).toBeInTheDocument();
  });

  it("distinguishes no matches from not having searched", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(jsonResponse({ data: [] }));

    render(<GlobalSearchPanel />);
    await user.type(screen.getByLabelText("Search across JARVIS"), "zzz");

    expect(await screen.findByText("No matches")).toBeInTheDocument();
  });

  it("shows the backend's own reason when a search fails", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(jsonResponse({ detail: "Search index rebuilding" }, 503));

    render(<GlobalSearchPanel />);
    await user.type(screen.getByLabelText("Search across JARVIS"), "plan");

    expect(await screen.findByText("Search failed")).toBeInTheDocument();
    expect(screen.getByText(/Search index rebuilding/)).toBeInTheDocument();
  });

  it("says it is offline instead of firing a doomed request", async () => {
    const user = userEvent.setup();
    setConnection("unreachable");

    render(<GlobalSearchPanel />);
    await user.type(screen.getByLabelText("Search across JARVIS"), "plan");

    expect(await screen.findByText("Search is offline")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock).not.toHaveBeenCalled());
  });

  it("debounces so typing does not fire a request per keystroke", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(jsonResponse({ data: [RESULT] }));

    render(<GlobalSearchPanel />);
    await user.type(screen.getByLabelText("Search across JARVIS"), "planning");

    await screen.findByText("Quarterly plan");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("returns to the prompt when the query is cleared", async () => {
    const user = userEvent.setup();
    fetchMock.mockResolvedValue(jsonResponse({ data: [RESULT] }));

    render(<GlobalSearchPanel />);
    const input = screen.getByLabelText("Search across JARVIS");
    await user.type(input, "plan");
    await screen.findByText("Quarterly plan");

    await user.clear(input);

    expect(await screen.findByText(/Search across your workspaces/)).toBeInTheDocument();
  });
});
