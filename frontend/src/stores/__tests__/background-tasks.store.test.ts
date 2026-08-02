import { beforeEach, describe, expect, it } from "vitest";
import { useBackgroundTasksStore } from "@/stores/background-tasks.store";

describe("useBackgroundTasksStore", () => {
  beforeEach(() => {
    useBackgroundTasksStore.setState({ tasks: [] });
  });

  it("start() adds a running task with a real timestamp, without the caller supplying one", () => {
    useBackgroundTasksStore.getState().start({ id: "t1", moduleId: "files", label: "Syncing", percent: null });

    const task = useBackgroundTasksStore.getState().tasks[0];
    expect(task.status).toBe("running");
    expect(typeof task.timestamp).toBe("string");
    expect(Number.isNaN(new Date(task.timestamp).getTime())).toBe(false);
  });

  it("complete() marks the task completed and bumps its timestamp", async () => {
    useBackgroundTasksStore.getState().start({ id: "t1", moduleId: "files", label: "Syncing", percent: null });
    const startedAt = useBackgroundTasksStore.getState().tasks[0].timestamp;

    await new Promise((resolve) => setTimeout(resolve, 2));
    useBackgroundTasksStore.getState().complete("t1");

    const task = useBackgroundTasksStore.getState().tasks[0];
    expect(task.status).toBe("completed");
    expect(new Date(task.timestamp).getTime()).toBeGreaterThanOrEqual(new Date(startedAt).getTime());
  });

  it("fail() marks the task failed and bumps its timestamp", () => {
    useBackgroundTasksStore.getState().start({ id: "t1", moduleId: "files", label: "Syncing", percent: null });
    useBackgroundTasksStore.getState().fail("t1");

    expect(useBackgroundTasksStore.getState().tasks[0].status).toBe("failed");
  });

  it("update() sets percent/label and bumps the timestamp, without touching other tasks", () => {
    useBackgroundTasksStore.getState().start({ id: "t1", moduleId: "files", label: "Syncing", percent: null });
    useBackgroundTasksStore.getState().start({ id: "t2", moduleId: "files", label: "Other", percent: null });

    useBackgroundTasksStore.getState().update("t1", 50);

    const [t1, t2] = useBackgroundTasksStore.getState().tasks;
    expect(t1.percent).toBe(50);
    expect(t2.percent).toBeNull();
  });
});
