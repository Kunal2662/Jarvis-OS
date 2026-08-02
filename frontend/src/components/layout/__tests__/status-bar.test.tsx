import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { registerCoreStatusBarItems } from "@/components/layout/status-bar-contributions";
import { StatusBar } from "@/components/layout/status-bar";
import { statusBarRegistry, type StatusBarContribution } from "@/core/interfaces/status-bar-interface";

function contribution(overrides: Partial<StatusBarContribution> = {}): StatusBarContribution {
  return {
    id: "test.item",
    moduleId: "test-module",
    displayName: "Test Item",
    category: "left",
    priority: 10,
    isCore: false,
    render: () => <>Test Value</>,
    ...overrides,
  };
}

describe("StatusBar", () => {
  beforeEach(() => {
    for (const item of statusBarRegistry.getAll()) {
      statusBarRegistry.unregister(item.id);
    }
  });

  it("renders without crashing when nothing is registered -- no fake default items", () => {
    render(<StatusBar />);
    expect(screen.getByLabelText("Workspace status")).toBeEmptyDOMElement();
    expect(screen.getByLabelText("Task status")).toBeEmptyDOMElement();
    expect(screen.getByLabelText("System status")).toBeEmptyDOMElement();
  });

  it("groups contributions into left/center/right by category", () => {
    statusBarRegistry.register(
      contribution({ id: "left-1", category: "left", render: () => <>Left</> }),
    );
    statusBarRegistry.register(
      contribution({ id: "center-1", category: "center", render: () => <>Center</> }),
    );
    statusBarRegistry.register(
      contribution({ id: "right-1", category: "right", render: () => <>Right</> }),
    );

    render(<StatusBar />);

    expect(within(screen.getByLabelText("Workspace status")).getByText("Left")).toBeInTheDocument();
    expect(within(screen.getByLabelText("Task status")).getByText("Center")).toBeInTheDocument();
    expect(within(screen.getByLabelText("System status")).getByText("Right")).toBeInTheDocument();
  });

  it("sorts contributions within a category by ascending priority", () => {
    statusBarRegistry.register(
      contribution({ id: "second", category: "left", priority: 20, render: () => <>Second</> }),
    );
    statusBarRegistry.register(
      contribution({ id: "first", category: "left", priority: 10, render: () => <>First</> }),
    );

    render(<StatusBar />);

    const group = screen.getByLabelText("Workspace status");
    const text = group.textContent ?? "";
    expect(text.indexOf("First")).toBeLessThan(text.indexOf("Second"));
  });

  it("each item carries its own accessible label from displayName", () => {
    statusBarRegistry.register(contribution({ id: "left-1", displayName: "Custom Label" }));

    render(<StatusBar />);

    expect(screen.getByLabelText("Custom Label")).toBeInTheDocument();
  });

  it("integration: Core JARVIS's real 9 items render through the same path, including the honest connection status", () => {
    registerCoreStatusBarItems();

    render(<StatusBar />);

    // No backend WebSocket route exists yet (see services/websocket) --
    // this must never read "Connected". Same assertion the pre-Task-
    // Group-E StatusBar test made, now proven through the registry.
    expect(screen.getByText("Not connected")).toBeInTheDocument();
  });
});
