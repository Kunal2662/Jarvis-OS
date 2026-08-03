import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/layout/status-bar-contributions", () => ({ registerCoreStatusBarItems: vi.fn() }));
vi.mock("@/features/dashboard/dashboard-widgets", () => ({ registerCoreDashboardWidgets: vi.fn() }));
vi.mock("@/modules/register-modules", () => ({ registerPlaceholderModules: vi.fn().mockResolvedValue([]) }));

import { registerCoreStatusBarItems } from "@/components/layout/status-bar-contributions";
import { registerCoreDashboardWidgets } from "@/features/dashboard/dashboard-widgets";
import { registerPlaceholderModules } from "@/modules/register-modules";
import { __resetStartupSequenceForTests, runStartupSequence } from "@/core/startup-orchestrator";

describe("runStartupSequence", () => {
  beforeEach(() => {
    __resetStartupSequenceForTests();
    vi.mocked(registerCoreStatusBarItems).mockReset();
    vi.mocked(registerCoreDashboardWidgets).mockReset();
    vi.mocked(registerPlaceholderModules).mockReset().mockResolvedValue([]);
  });

  it("is idempotent -- a second call returns the same promise and does not re-run the real tasks", async () => {
    const first = runStartupSequence();
    const second = runStartupSequence();

    expect(second).toBe(first);
    await first;
    expect(registerCoreStatusBarItems).toHaveBeenCalledOnce();
  });

  it("runs the real high-priority tasks", async () => {
    await runStartupSequence();

    expect(registerCoreStatusBarItems).toHaveBeenCalledOnce();
    expect(registerCoreDashboardWidgets).toHaveBeenCalledOnce();
  });

  it("runs the real medium-priority task", async () => {
    await runStartupSequence();

    expect(registerPlaceholderModules).toHaveBeenCalledOnce();
  });

  it("runs high-priority tasks before medium-priority tasks", async () => {
    const order: string[] = [];
    vi.mocked(registerCoreStatusBarItems).mockImplementation(() => {
      order.push("high");
    });
    vi.mocked(registerPlaceholderModules).mockImplementation(async () => {
      order.push("medium");
      return [];
    });

    await runStartupSequence();

    expect(order).toEqual(["high", "medium"]);
  });

  it("resolves even though the low-priority tier has no real tasks yet", async () => {
    await expect(runStartupSequence()).resolves.toBeUndefined();
  });
});
