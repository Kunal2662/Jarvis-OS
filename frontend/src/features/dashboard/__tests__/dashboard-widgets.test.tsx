import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { registerCoreDashboardWidgets } from "@/features/dashboard/dashboard-widgets";
import { dashboardWidgetRegistry } from "@/core/dashboard-widget-registry";
import { useBackgroundTasksStore } from "@/stores/background-tasks.store";
import { useNotificationsStore } from "@/stores/notifications.store";

describe("registerCoreDashboardWidgets", () => {
  beforeEach(() => {
    for (const widget of dashboardWidgetRegistry.getAll()) {
      dashboardWidgetRegistry.unregister(widget.id);
    }
  });

  it("registers exactly 4 core widgets, all marked isCore, owned by the reserved 'core' moduleId", () => {
    registerCoreDashboardWidgets();

    const widgets = dashboardWidgetRegistry.getAll();
    expect(widgets).toHaveLength(4);
    expect(widgets.every((w) => w.isCore)).toBe(true);
    expect(widgets.every((w) => w.moduleId === "core")).toBe(true);
  });

  it("does NOT register a Tasks, Calendar, or Notes widget -- no real backing store exists for any of them", () => {
    registerCoreDashboardWidgets();

    const titles = dashboardWidgetRegistry.getAll().map((w) => w.title);
    expect(titles).not.toContain("Tasks");
    expect(titles).not.toContain("Calendar");
    expect(titles).not.toContain("Notes");
  });
});

describe("core dashboard widget components", () => {
  beforeEach(() => {
    for (const widget of dashboardWidgetRegistry.getAll()) {
      dashboardWidgetRegistry.unregister(widget.id);
    }
    useNotificationsStore.setState({ items: [] });
    useBackgroundTasksStore.setState({ tasks: [] });
    registerCoreDashboardWidgets();
  });

  it("Notifications widget honestly shows 'No notifications' when empty", () => {
    const Notifications = dashboardWidgetRegistry.get("core.widget.notifications")!.render;
    render(<Notifications />);
    expect(screen.getByText("No notifications")).toBeInTheDocument();
  });

  it("Notifications widget lists real items and 'Mark all read' marks every unread item", async () => {
    useNotificationsStore.getState().add({
      id: "n1",
      title: "First alert",
      message: "m",
      severity: "info",
      createdAt: new Date().toISOString(),
      read: false,
    });

    const Notifications = dashboardWidgetRegistry.get("core.widget.notifications")!.render;
    render(<Notifications />);

    expect(screen.getByText("First alert")).toBeInTheDocument();
    expect(screen.getByText("1 unread")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(useNotificationsStore.getState().items[0].read).toBe(true);
  });

  it("System Status widget honestly shows 'No active tasks' and 'Not configured' where no real data source exists", () => {
    const SystemStatus = dashboardWidgetRegistry.get("core.widget.system-status")!.render;
    render(<SystemStatus />);

    expect(screen.getByText("No active tasks")).toBeInTheDocument();
    expect(screen.getAllByText("Not configured")).toHaveLength(3);
  });

  it("System Status widget shows the real running task and its progress", () => {
    useBackgroundTasksStore.getState().start({ id: "t1", moduleId: "files", label: "Syncing files", percent: null });
    useBackgroundTasksStore.getState().update("t1", 42);

    const SystemStatus = dashboardWidgetRegistry.get("core.widget.system-status")!.render;
    render(<SystemStatus />);
    expect(screen.getByText("Syncing files (42%)")).toBeInTheDocument();
  });

  it("Recent Activity widget honestly shows 'No recent activity' when nothing has happened", () => {
    const RecentActivity = dashboardWidgetRegistry.get("core.widget.recent-activity")!.render;
    render(<RecentActivity />);
    expect(screen.getByText("No recent activity")).toBeInTheDocument();
  });

  it("Recent Activity widget merges real notifications and completed/failed tasks, excluding still-running tasks", () => {
    useNotificationsStore.getState().add({
      id: "n1",
      title: "Backup finished",
      message: "m",
      severity: "success",
      createdAt: new Date().toISOString(),
      read: true,
    });
    useBackgroundTasksStore.getState().start({ id: "t1", moduleId: "files", label: "Still running", percent: null });
    useBackgroundTasksStore.getState().start({ id: "t2", moduleId: "files", label: "Import failed", percent: null });
    useBackgroundTasksStore.getState().fail("t2");

    const RecentActivity = dashboardWidgetRegistry.get("core.widget.recent-activity")!.render;
    render(<RecentActivity />);

    expect(screen.getByText("Backup finished")).toBeInTheDocument();
    expect(screen.getByText("Import failed")).toBeInTheDocument();
    expect(screen.queryByText("Still running")).not.toBeInTheDocument();
  });

  it("Quick Actions widget renders real navigation links to core modules", () => {
    const QuickActions = dashboardWidgetRegistry.get("core.widget.quick-actions")!.render;
    render(
      <MemoryRouter>
        <QuickActions />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Open Conversation" })).toHaveAttribute("href", "/chat");
    expect(screen.getByRole("link", { name: "Open Voice" })).toHaveAttribute("href", "/voice");
    expect(screen.getByRole("link", { name: "Open Files" })).toHaveAttribute("href", "/files");
    expect(screen.getByRole("link", { name: "Open Automation" })).toHaveAttribute("href", "/automations");
  });
});
