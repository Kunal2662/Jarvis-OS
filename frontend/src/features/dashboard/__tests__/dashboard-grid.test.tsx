import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { dashboardWidgetRegistry, type DashboardWidgetContribution } from "@/core/dashboard-widget-registry";
import { DashboardGrid } from "@/features/dashboard/dashboard-grid";
import { useDashboardLayoutStore } from "@/stores/dashboard-layout.store";
import { useModuleEnablementStore } from "@/stores/module-enablement.store";

function widget(overrides: Partial<DashboardWidgetContribution> = {}): DashboardWidgetContribution {
  return {
    id: "w1",
    moduleId: "core",
    title: "Widget One",
    render: () => <span>Widget One content</span>,
    defaultSize: { width: 1, height: 1 },
    isCore: true,
    ...overrides,
  };
}

function renderGrid() {
  return render(
    <MemoryRouter>
      <DashboardGrid />
    </MemoryRouter>,
  );
}

describe("DashboardGrid", () => {
  beforeEach(() => {
    for (const w of dashboardWidgetRegistry.getAll()) {
      dashboardWidgetRegistry.unregister(w.id);
    }
    useDashboardLayoutStore.setState({ order: [], entries: {} });
    useModuleEnablementStore.setState({ enabledModuleIds: [] });
  });

  it("shows the empty state when no widgets are registered", () => {
    renderGrid();
    expect(screen.getByText(/No widgets to show/)).toBeInTheDocument();
  });

  it("auto-places a newly available widget at its declared default size, without an explicit user action", () => {
    dashboardWidgetRegistry.register(widget());
    renderGrid();

    expect(screen.getByRole("group", { name: "Widget One" })).toBeInTheDocument();
    expect(useDashboardLayoutStore.getState().entries.w1).toMatchObject({ width: 1, height: 1, visible: true });
  });

  it("hides a widget belonging to a disabled, non-core module", () => {
    dashboardWidgetRegistry.register(widget({ id: "w2", moduleId: "gmail", isCore: false }));
    renderGrid();

    expect(screen.queryByRole("group", { name: "Widget One" })).not.toBeInTheDocument();
  });

  it("shows a widget belonging to an enabled, non-core module", () => {
    useModuleEnablementStore.setState({ enabledModuleIds: ["gmail"] });
    dashboardWidgetRegistry.register(widget({ id: "w2", moduleId: "gmail", isCore: false }));
    renderGrid();

    expect(screen.getByRole("group", { name: "Widget One" })).toBeInTheDocument();
  });

  it("Remove hides the widget and it reappears via Add widget", async () => {
    dashboardWidgetRegistry.register(widget());
    renderGrid();

    const user = userEvent.setup();
    const card = screen.getByRole("group", { name: "Widget One" });
    await user.click(within(card).getByRole("button", { name: "Remove" }));

    expect(screen.queryByRole("group", { name: "Widget One" })).not.toBeInTheDocument();
    expect(useDashboardLayoutStore.getState().entries.w1.visible).toBe(false);

    await user.click(screen.getByRole("button", { name: "Add widget" }));
    await user.click(screen.getByRole("menuitem", { name: "Widget One" }));

    expect(screen.getByRole("group", { name: "Widget One" })).toBeInTheDocument();
  });

  it("Remove is disabled while the widget is pinned", async () => {
    dashboardWidgetRegistry.register(widget());
    renderGrid();

    const user = userEvent.setup();
    await user.click(within(screen.getByRole("group", { name: "Widget One" })).getByRole("button", { name: "Pin" }));

    // Pinning moves the widget to the pinned peer group's own
    // Reorder.Group (Task Group L), a different subtree -- re-query
    // rather than reuse the pre-pin `card` reference, which now points
    // at a detached, unmounted node.
    const card = screen.getByRole("group", { name: "Widget One" });
    expect(within(card).getByRole("button", { name: "Remove" })).toBeDisabled();
  });

  it("Resize cycles the widget through the fixed size tiers", async () => {
    dashboardWidgetRegistry.register(widget());
    renderGrid();

    const user = userEvent.setup();
    const card = screen.getByRole("group", { name: "Widget One" });
    await user.click(within(card).getByRole("button", { name: "Resize" }));

    expect(useDashboardLayoutStore.getState().entries.w1).toMatchObject({ width: 2, height: 1 });
  });

  it("Move up/down reorders unpinned peers", async () => {
    dashboardWidgetRegistry.register(widget({ id: "a", title: "Widget A" }));
    dashboardWidgetRegistry.register(widget({ id: "b", title: "Widget B" }));
    renderGrid();

    const user = userEvent.setup();
    const cardB = screen.getByRole("group", { name: "Widget B" });
    await user.click(within(cardB).getByRole("button", { name: "Move up" }));

    expect(useDashboardLayoutStore.getState().order).toEqual(["b", "a"]);
  });

  it("renders each widget's real content via its own render component", () => {
    dashboardWidgetRegistry.register(widget());
    renderGrid();
    expect(screen.getByText("Widget One content")).toBeInTheDocument();
  });

  describe("drag-to-reorder (Task Group L)", () => {
    it("exposes a dedicated drag handle alongside the existing Move up/down buttons -- additive, not a replacement", () => {
      dashboardWidgetRegistry.register(widget());
      renderGrid();

      const card = screen.getByRole("group", { name: "Widget One" });
      expect(within(card).getByRole("button", { name: "Drag to reorder" })).toBeInTheDocument();
      expect(within(card).getByRole("button", { name: "Move up" })).toBeInTheDocument();
      expect(within(card).getByRole("button", { name: "Move down" })).toBeInTheDocument();
    });

    it("a pinned widget's peer group is separate from unpinned widgets -- moveWidget() still refuses to cross it", async () => {
      // The real drag interaction itself (pointer geometry, motion
      // physics) isn't meaningfully testable under jsdom -- covered by
      // `dashboard-layout.store.test.ts`'s direct `reorderPeers()`
      // tests and live browser verification instead. This proves the
      // two Reorder.Group peer partitions this task group introduced
      // didn't regress the pre-existing pinned/unpinned boundary the
      // Move buttons already enforced.
      dashboardWidgetRegistry.register(widget({ id: "a", title: "Widget A" }));
      dashboardWidgetRegistry.register(widget({ id: "b", title: "Widget B" }));
      renderGrid();

      const user = userEvent.setup();
      await user.click(
        within(screen.getByRole("group", { name: "Widget B" })).getByRole("button", { name: "Pin" }),
      );
      await user.click(
        within(screen.getByRole("group", { name: "Widget B" })).getByRole("button", { name: "Move up" }),
      );

      // "b" is the only pinned widget -- Move up is a no-op for it, not
      // a swap with unpinned "a".
      expect(useDashboardLayoutStore.getState().order).toEqual(["a", "b"]);
    });
  });
});
