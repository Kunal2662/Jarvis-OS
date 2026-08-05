import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ActivityCenter } from "@/features/activity/activity-center";
import { PROGRESS_PHRASES } from "@/core/user-mode";
import { useAgentActivityStore } from "@/stores/agent-activity.store";
import { useBackgroundTasksStore } from "@/stores/background-tasks.store";
import { useDeveloperModeStore } from "@/stores/developer-mode.store";
import { resetUserModeForTesting } from "@/stores/user-mode.store";

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  useBackgroundTasksStore.setState({ tasks: [] });
  useAgentActivityStore.setState({ agentSteps: [], automationSteps: [] });
  resetUserModeForTesting();
});

function agentStep(node: string, step = 1, at = "2026-08-06T10:00:00.000Z") {
  useAgentActivityStore
    .getState()
    .recordAgentStep({ thread_id: "th1", step, node, status: "running", detail: "internal detail" }, at);
}

describe("ActivityCenter", () => {
  it("is empty until something actually happens", () => {
    render(<ActivityCenter />);
    expect(screen.getByText("Nothing running")).toBeInTheDocument();
  });

  it("shows a background task", () => {
    useBackgroundTasksStore.getState().start({
      id: "t1",
      moduleId: "files",
      label: "Indexing files",
      percent: 40,
    });

    render(<ActivityCenter />);

    expect(screen.getByText("Indexing files")).toBeInTheDocument();
  });

  it("shows an automation step", () => {
    useDeveloperModeStore.getState().unlock();
    useAgentActivityStore
      .getState()
      .recordAutomationStep({ step_id: "s1", action: "open_browser", status: "ok" }, "2026-08-06T10:00:00.000Z");

    render(<ActivityCenter />);

    expect(screen.getByText("open_browser")).toBeInTheDocument();
  });

  it("maps the backend's free-string statuses onto real outcomes", () => {
    agentStep("done", 1, "2026-08-06T10:00:00.000Z");
    useAgentActivityStore.getState().recordAgentStep(
      { thread_id: "th1", step: 2, node: "broke", status: "error", detail: "" },
      "2026-08-06T10:01:00.000Z",
    );
    useAgentActivityStore.getState().recordAgentStep(
      { thread_id: "th1", step: 3, node: "ok", status: "completed", detail: "" },
      "2026-08-06T10:02:00.000Z",
    );

    render(<ActivityCenter />);

    expect(screen.getByLabelText("completed")).toBeInTheDocument();
    expect(screen.getByLabelText("failed")).toBeInTheDocument();
  });

  it("treats an unrecognised status as still running rather than inventing an outcome", () => {
    useAgentActivityStore.getState().recordAgentStep(
      { thread_id: "th1", step: 1, node: "odd", status: "reticulating", detail: "" },
      "2026-08-06T10:00:00.000Z",
    );

    render(<ActivityCenter />);

    expect(screen.getByLabelText("running")).toBeInTheDocument();
  });
});

/**
 * `ARCHITECTURE.md` §22.12: a personal user never sees internal agent
 * names, backend execution detail or module names. These tests are the
 * enforcement — the panel shipped in M8 Phase 3 leaked all three.
 */
describe("§22.12 — personal mode hides internals", () => {
  it("replaces agent node names with the mandated progress vocabulary", () => {
    agentStep("tool_executor", 1);

    render(<ActivityCenter />);

    expect(screen.queryByText(/tool_executor/)).not.toBeInTheDocument();
    expect(screen.queryByText("internal detail")).not.toBeInTheDocument();
    const rendered = screen.getAllByRole("listitem")[0].textContent ?? "";
    expect(PROGRESS_PHRASES.some((phrase) => rendered.includes(phrase))).toBe(true);
  });

  it("hides automation action names", () => {
    useAgentActivityStore
      .getState()
      .recordAutomationStep({ step_id: "s1", action: "open_browser", status: "ok" }, "2026-08-06T10:00:00.000Z");

    render(<ActivityCenter />);

    expect(screen.queryByText("open_browser")).not.toBeInTheDocument();
  });

  it("hides the backend module a task belongs to but keeps its progress", () => {
    useBackgroundTasksStore.getState().start({
      id: "t1",
      moduleId: "files",
      label: "Indexing files",
      percent: 40,
    });

    render(<ActivityCenter />);

    // The label is the user's own business; the module name is not.
    expect(screen.getByText("Indexing files")).toBeInTheDocument();
    expect(screen.queryByText(/files —/)).not.toBeInTheDocument();
    expect(screen.getByText("40%")).toBeInTheDocument();
  });

  it("keeps step count, order and status identical to developer mode", () => {
    // The progress vocabulary must not turn real progress into a
    // decorative animation: a personal user sees fewer *words*, not
    // fewer or differently-ordered events.
    agentStep("alpha", 1, "2026-08-06T10:00:00.000Z");
    agentStep("beta", 2, "2026-08-06T10:01:00.000Z");

    const personal = render(<ActivityCenter />);
    const personalRows = screen.getAllByRole("listitem").length;
    personal.unmount();

    useDeveloperModeStore.getState().unlock();
    render(<ActivityCenter />);

    expect(screen.getAllByRole("listitem")).toHaveLength(personalRows);
    expect(screen.getByText(/alpha/)).toBeInTheDocument();
  });
});

describe("developer mode shows the real trace", () => {
  beforeEach(() => useDeveloperModeStore.getState().unlock());

  it("shows agent node names and detail", () => {
    agentStep("planner", 3);

    render(<ActivityCenter />);

    expect(screen.getByText("planner (step 3)")).toBeInTheDocument();
    expect(screen.getByText("internal detail")).toBeInTheDocument();
  });

  it("merges all three sources newest first", () => {
    useBackgroundTasksStore.setState({
      tasks: [
        {
          id: "t1",
          moduleId: "files",
          label: "Oldest task",
          percent: null,
          status: "running",
          timestamp: "2026-08-06T09:00:00.000Z",
        },
      ],
    });
    agentStep("newest", 1, "2026-08-06T11:00:00.000Z");
    useAgentActivityStore
      .getState()
      .recordAutomationStep({ step_id: "middle", action: "middle", status: "ok" }, "2026-08-06T10:00:00.000Z");

    render(<ActivityCenter />);

    const rows = screen.getAllByRole("listitem").map((row) => row.textContent ?? "");
    expect(rows[0]).toContain("newest");
    expect(rows[1]).toContain("middle");
    expect(rows[2]).toContain("Oldest task");
  });
});
