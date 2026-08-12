import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotificationCenter } from "@/features/notifications/notification-center";
import { useNotificationsStore, type NotificationRecord } from "@/stores/notifications.store";

function record(overrides: Partial<NotificationRecord> = {}): NotificationRecord {
  return {
    id: crypto.randomUUID(),
    title: "Backup finished",
    message: "3 files copied.",
    severity: "success",
    createdAt: "2026-08-06T09:30:00.000Z",
    read: false,
    ...overrides,
  };
}

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      disconnect() {}
    },
  );
  useNotificationsStore.setState({ items: [] });
});

describe("NotificationCenter", () => {
  it("shows an honest empty state rather than seeded rows", () => {
    render(<NotificationCenter />);

    expect(screen.getByText("No notifications")).toBeInTheDocument();
    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
  });

  it("renders real entries from the store", () => {
    useNotificationsStore.setState({ items: [record({ title: "Sync failed", severity: "error" })] });

    render(<NotificationCenter />);

    expect(screen.getByText("Sync failed")).toBeInTheDocument();
    expect(screen.getByText("3 files copied.")).toBeInTheDocument();
  });

  it("counts unread", () => {
    useNotificationsStore.setState({
      items: [record(), record({ read: true }), record()],
    });

    render(<NotificationCenter />);

    expect(screen.getByText("2 unread")).toBeInTheDocument();
  });

  it("says so when everything is read", () => {
    useNotificationsStore.setState({ items: [record({ read: true })] });
    render(<NotificationCenter />);
    expect(screen.getByText("All read")).toBeInTheDocument();
  });

  it("marks one entry read", async () => {
    const user = userEvent.setup();
    const item = record({ title: "Only one" });
    useNotificationsStore.setState({ items: [item] });

    render(<NotificationCenter />);
    await user.click(screen.getByRole("button", { name: 'Mark "Only one" as read' }));

    expect(useNotificationsStore.getState().items[0].read).toBe(true);
  });

  it("marks every unread entry read at once", async () => {
    const user = userEvent.setup();
    useNotificationsStore.setState({ items: [record(), record(), record({ read: true })] });

    render(<NotificationCenter />);
    await user.click(screen.getByRole("button", { name: "Mark all read" }));

    expect(useNotificationsStore.getState().items.every((item) => item.read)).toBe(true);
  });

  it("clears the list", async () => {
    const user = userEvent.setup();
    useNotificationsStore.setState({ items: [record()] });

    render(<NotificationCenter />);
    await user.click(screen.getByRole("button", { name: "Clear all notifications" }));

    expect(useNotificationsStore.getState().items).toEqual([]);
    expect(screen.getByText("No notifications")).toBeInTheDocument();
  });

  it("windows a long list rather than rendering every row", () => {
    // The store is unbounded and a long session accumulates entries; the
    // panel must not render 500 DOM nodes behind a 300px rail.
    useNotificationsStore.setState({
      items: Array.from({ length: 500 }, (_, index) => record({ title: `Item ${index}` })),
    });

    render(<NotificationCenter />);

    expect(screen.getAllByRole("listitem").length).toBeLessThan(500);
    expect(screen.getByText("500 unread")).toBeInTheDocument();
  });
});
