import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { registerCoreStatusBarItems } from "@/components/layout/status-bar-contributions";
import { applicationRegistry } from "@/core/application-registry";
import { statusBarRegistry } from "@/core/interfaces/status-bar-interface";
import { TestApplication } from "@/core/test-utils/test-application";
import { useBackgroundTasksStore } from "@/stores/background-tasks.store";
import { useNotificationsStore } from "@/stores/notifications.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

describe("registerCoreStatusBarItems", () => {
  beforeEach(() => {
    for (const item of statusBarRegistry.getAll()) {
      statusBarRegistry.unregister(item.id);
    }
  });

  it("registers exactly 9 core items, all marked isCore, owned by the reserved 'core' moduleId", () => {
    registerCoreStatusBarItems();

    const items = statusBarRegistry.getAll();
    expect(items).toHaveLength(9);
    expect(items.every((item) => item.isCore)).toBe(true);
    expect(items.every((item) => item.moduleId === "core")).toBe(true);
  });

  it("distributes items across left/center/right per the approved design", () => {
    registerCoreStatusBarItems();

    const byCategory = (category: "left" | "center" | "right") =>
      statusBarRegistry.getAll().filter((item) => item.category === category).length;

    expect(byCategory("left")).toBe(2); // Current Workspace, Active Module
    expect(byCategory("center")).toBe(2); // Current Running Task, Background Task Progress
    expect(byCategory("right")).toBe(5); // AI Provider, Voice Status, Automation Status, Internet/Offline, Notifications
  });
});

describe("core status bar item components", () => {
  beforeEach(async () => {
    for (const module of applicationRegistry.getAll()) {
      applicationRegistry.unregister(module.manifest.name);
    }
    for (const item of statusBarRegistry.getAll()) {
      statusBarRegistry.unregister(item.id);
    }
    useWorkspaceStore.setState({ activeModuleId: null });
    useBackgroundTasksStore.setState({ tasks: [] });
    useNotificationsStore.setState({ items: [] });
    registerCoreStatusBarItems();
  });

  it("Active Module honestly shows '—' when nothing is active", () => {
    const ActiveModule = statusBarRegistry.get("core.active-module")!.render;
    render(<ActiveModule />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("Active Module shows the real active module's displayName", async () => {
    await new TestApplication({ name: "gmail", displayName: "Gmail" }).initialize();
    useWorkspaceStore.setState({ activeModuleId: "gmail" });

    const ActiveModule = statusBarRegistry.get("core.active-module")!.render;
    render(<ActiveModule />);
    expect(screen.getByText("Gmail")).toBeInTheDocument();
  });

  it("Current Running Task honestly shows 'No active tasks' when none are running", () => {
    const RunningTask = statusBarRegistry.get("core.running-task")!.render;
    render(<RunningTask />);
    expect(screen.getByText("No active tasks")).toBeInTheDocument();
  });

  it("Current Running Task / Background Task Progress show real task state", () => {
    useBackgroundTasksStore
      .getState()
      .start({ id: "sync-1", moduleId: "files", label: "Syncing files", percent: null });
    useBackgroundTasksStore.getState().update("sync-1", 42);

    const RunningTask = statusBarRegistry.get("core.running-task")!.render;
    const Progress = statusBarRegistry.get("core.task-progress")!.render;
    render(
      <>
        <RunningTask />
        <Progress />
      </>,
    );

    expect(screen.getByText("Syncing files")).toBeInTheDocument();
    expect(screen.getByText("42%")).toBeInTheDocument();
  });

  it("AI Provider / Voice Status / Automation Status honestly show 'Not configured', never fake data", () => {
    const AiProvider = statusBarRegistry.get("core.ai-provider")!.render;
    const Voice = statusBarRegistry.get("core.voice-status")!.render;
    const Automation = statusBarRegistry.get("core.automation-status")!.render;
    render(
      <>
        <AiProvider />
        <Voice />
        <Automation />
      </>,
    );

    expect(screen.getAllByText("Not configured")).toHaveLength(3);
  });

  it("Notification Indicator shows the real unread count", () => {
    useNotificationsStore.getState().add({
      id: "n1",
      title: "Test",
      message: "Test message",
      severity: "info",
      createdAt: new Date().toISOString(),
      read: false,
    });

    const Notifications = statusBarRegistry.get("core.notifications")!.render;
    render(<Notifications />);
    expect(screen.getByText("1 unread")).toBeInTheDocument();
  });
});
