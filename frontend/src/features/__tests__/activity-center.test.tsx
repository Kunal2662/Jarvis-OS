import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ActivityCenter } from "@/features/activity/activity-center";
import { useAgentActivityStore } from "@/stores/agent-activity.store";
import { useBackgroundTasksStore } from "@/stores/background-tasks.store";

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
});

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
    expect(screen.getByText("files — 40%")).toBeInTheDocument();
  });

  it("shows an agent step from the WebSocket relay", () => {
    useAgentActivityStore.getState().recordAgentStep(
      { thread_id: "th1", step: 2, node: "planner", status: "running", detail: "choosing a tool" },
      "2026-08-06T10:00:00.000Z",
    );

    render(<ActivityCenter />);

    expect(screen.getByText("planner (step 2)")).toBeInTheDocument();
    expect(screen.getByText("choosing a tool")).toBeInTheDocument();
  });

  it("shows an automation step", () => {
    useAgentActivityStore
      .getState()
      .recordAutomationStep({ step_id: "s1", action: "open_browser", status: "ok" }, "2026-08-06T10:00:00.000Z");

    render(<ActivityCenter />);

    expect(screen.getByText("open_browser")).toBeInTheDocument();
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
    useAgentActivityStore
      .getState()
      .recordAgentStep(
        { thread_id: "th1", step: 1, node: "newest", status: "ok", detail: "" },
        "2026-08-06T11:00:00.000Z",
      );
    useAgentActivityStore
      .getState()
      .recordAutomationStep({ step_id: "middle", action: "middle", status: "ok" }, "2026-08-06T10:00:00.000Z");

    render(<ActivityCenter />);

    const rows = screen.getAllByRole("listitem").map((row) => row.textContent ?? "");
    expect(rows[0]).toContain("newest");
    expect(rows[1]).toContain("middle");
    expect(rows[2]).toContain("Oldest task");
  });

  it("maps the backend's free-string statuses onto real outcomes", () => {
    useAgentActivityStore.getState().recordAgentStep(
      { thread_id: "th1", step: 1, node: "done", status: "completed", detail: "" },
      "2026-08-06T10:00:00.000Z",
    );
    useAgentActivityStore.getState().recordAgentStep(
      { thread_id: "th1", step: 2, node: "broke", status: "error", detail: "" },
      "2026-08-06T10:01:00.000Z",
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
