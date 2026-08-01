import { beforeEach, describe, expect, it, vi } from "vitest";
import { toast } from "sonner";
import { notificationFramework } from "@/core/notification-framework";
import { useBackgroundTasksStore } from "@/stores/background-tasks.store";
import { useNotificationsStore } from "@/stores/notifications.store";

vi.mock("sonner", () => ({
  toast: Object.assign(vi.fn(), {
    success: vi.fn(),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
  }),
}));

describe("notificationFramework", () => {
  beforeEach(() => {
    useNotificationsStore.setState({ items: [] });
    useBackgroundTasksStore.setState({ tasks: [] });
    vi.clearAllMocks();
  });

  it("success() adds a persistent record and shows a toast", () => {
    notificationFramework.success("mod-a", "Saved", "Your changes were saved.");

    expect(useNotificationsStore.getState().items).toHaveLength(1);
    expect(useNotificationsStore.getState().items[0]?.severity).toBe("success");
    expect(toast.success).toHaveBeenCalledWith("Saved", { description: "Your changes were saved." });
  });

  it("error() routes to the error toast and severity", () => {
    notificationFramework.error("mod-a", "Failed", "Something broke.");
    expect(toast.error).toHaveBeenCalled();
    expect(useNotificationsStore.getState().items[0]?.severity).toBe("error");
  });

  it("progress lifecycle tracks a background task through completion", () => {
    notificationFramework.progress.start("mod-a", "task-1", "Syncing...");
    expect(useBackgroundTasksStore.getState().tasks).toHaveLength(1);
    expect(useBackgroundTasksStore.getState().tasks[0]?.status).toBe("running");

    notificationFramework.progress.update("task-1", 50);
    expect(useBackgroundTasksStore.getState().tasks[0]?.percent).toBe(50);

    notificationFramework.progress.complete("task-1");
    expect(useBackgroundTasksStore.getState().tasks[0]?.status).toBe("completed");
  });

  it("push() throws rather than silently no-op-ing", () => {
    expect(() => notificationFramework.push("mod-a", "Title", "Message")).toThrow(/not implemented/);
  });
});
