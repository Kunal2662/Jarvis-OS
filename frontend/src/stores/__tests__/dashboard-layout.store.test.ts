import { beforeEach, describe, expect, it } from "vitest";
import { useDashboardLayoutStore } from "@/stores/dashboard-layout.store";

function reset() {
  useDashboardLayoutStore.setState({ order: [], entries: {} });
}

describe("useDashboardLayoutStore", () => {
  beforeEach(reset);

  it("starts empty -- no widget is placed until ensureWidget() sees it", () => {
    const state = useDashboardLayoutStore.getState();
    expect(state.order).toEqual([]);
    expect(state.entries).toEqual({});
  });

  it("ensureWidget() places a new widget at its declared default size", () => {
    useDashboardLayoutStore.getState().ensureWidget("w1", { width: 2, height: 1 });

    const state = useDashboardLayoutStore.getState();
    expect(state.order).toEqual(["w1"]);
    expect(state.entries.w1).toEqual({ id: "w1", width: 2, height: 1, pinned: false, visible: true });
  });

  it("ensureWidget() is a no-op once an entry already exists, even with a different size", () => {
    useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });
    useDashboardLayoutStore.getState().resizeWidget("w1", { width: 2, height: 2 });
    useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });

    expect(useDashboardLayoutStore.getState().entries.w1.width).toBe(2);
    expect(useDashboardLayoutStore.getState().entries.w1.height).toBe(2);
  });

  it("removeWidget() hides an unpinned widget without forgetting its layout", () => {
    useDashboardLayoutStore.getState().ensureWidget("w1", { width: 2, height: 2 });
    useDashboardLayoutStore.getState().removeWidget("w1");

    const entry = useDashboardLayoutStore.getState().entries.w1;
    expect(entry.visible).toBe(false);
    expect(entry.width).toBe(2);
    expect(entry.height).toBe(2);
  });

  it("removeWidget() refuses to remove a pinned widget", () => {
    useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });
    useDashboardLayoutStore.getState().togglePin("w1");
    useDashboardLayoutStore.getState().removeWidget("w1");

    expect(useDashboardLayoutStore.getState().entries.w1.visible).toBe(true);
  });

  it("addWidget() restores a removed widget to visible", () => {
    useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });
    useDashboardLayoutStore.getState().removeWidget("w1");
    useDashboardLayoutStore.getState().addWidget("w1");

    expect(useDashboardLayoutStore.getState().entries.w1.visible).toBe(true);
  });

  it("resizeWidget() updates only the target widget's size", () => {
    useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });
    useDashboardLayoutStore.getState().ensureWidget("w2", { width: 1, height: 1 });
    useDashboardLayoutStore.getState().resizeWidget("w1", { width: 2, height: 2 });

    expect(useDashboardLayoutStore.getState().entries.w1).toMatchObject({ width: 2, height: 2 });
    expect(useDashboardLayoutStore.getState().entries.w2).toMatchObject({ width: 1, height: 1 });
  });

  it("togglePin() flips a widget's pinned state", () => {
    useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });
    useDashboardLayoutStore.getState().togglePin("w1");
    expect(useDashboardLayoutStore.getState().entries.w1.pinned).toBe(true);
    useDashboardLayoutStore.getState().togglePin("w1");
    expect(useDashboardLayoutStore.getState().entries.w1.pinned).toBe(false);
  });

  describe("moveWidget()", () => {
    beforeEach(() => {
      reset();
      const { ensureWidget } = useDashboardLayoutStore.getState();
      ensureWidget("a", { width: 1, height: 1 });
      ensureWidget("b", { width: 1, height: 1 });
      ensureWidget("c", { width: 1, height: 1 });
    });

    it("swaps with the adjacent peer on 'up'/'down'", () => {
      useDashboardLayoutStore.getState().moveWidget("b", "up");
      expect(useDashboardLayoutStore.getState().order).toEqual(["b", "a", "c"]);

      useDashboardLayoutStore.getState().moveWidget("b", "down");
      expect(useDashboardLayoutStore.getState().order).toEqual(["a", "b", "c"]);
    });

    it("moves to the front/back of the group on 'start'/'end' (implemented as a swap with the current first/last peer)", () => {
      useDashboardLayoutStore.getState().moveWidget("c", "start");
      expect(useDashboardLayoutStore.getState().order).toEqual(["c", "b", "a"]);

      useDashboardLayoutStore.getState().moveWidget("c", "end");
      // Swap semantics, not splice/insert -- "c" (currently first) swaps
      // places with "a" (currently last), so "c" ends up last again and
      // "a" takes its old front slot; "b" is untouched in the middle.
      expect(useDashboardLayoutStore.getState().order).toEqual(["a", "b", "c"]);
    });

    it("is a no-op at the boundary", () => {
      useDashboardLayoutStore.getState().moveWidget("a", "up");
      expect(useDashboardLayoutStore.getState().order).toEqual(["a", "b", "c"]);

      useDashboardLayoutStore.getState().moveWidget("c", "down");
      expect(useDashboardLayoutStore.getState().order).toEqual(["a", "b", "c"]);
    });

    it("only reorders among same-pinned-state peers -- a pinned widget never swaps with an unpinned neighbor", () => {
      // "b" is pinned; its only peer group is itself, so moving it must
      // be a no-op rather than swapping with unpinned "a" or "c".
      useDashboardLayoutStore.getState().togglePin("b");
      useDashboardLayoutStore.getState().moveWidget("b", "up");
      expect(useDashboardLayoutStore.getState().order).toEqual(["a", "b", "c"]);

      // Pin "a" too -- now "a" and "b" are peers, "c" is not.
      useDashboardLayoutStore.getState().togglePin("a");
      useDashboardLayoutStore.getState().moveWidget("b", "up");
      expect(useDashboardLayoutStore.getState().order).toEqual(["b", "a", "c"]);
    });
  });

  describe("reorderPeers()", () => {
    beforeEach(() => {
      reset();
      const { ensureWidget } = useDashboardLayoutStore.getState();
      ensureWidget("a", { width: 1, height: 1 });
      ensureWidget("b", { width: 1, height: 1 });
      ensureWidget("c", { width: 1, height: 1 });
    });

    it("applies a full drag-produced permutation of the group", () => {
      useDashboardLayoutStore.getState().reorderPeers(["c", "a", "b"], false);
      expect(useDashboardLayoutStore.getState().order).toEqual(["c", "a", "b"]);
    });

    it("leaves the opposite pin group's positions untouched", () => {
      useDashboardLayoutStore.getState().togglePin("b");
      // Only "a"/"c" are unpinned peers now; reorder them.
      useDashboardLayoutStore.getState().reorderPeers(["c", "a"], false);
      // "b" (pinned) keeps its original slot; "a"/"c" swap around it.
      expect(useDashboardLayoutStore.getState().order).toEqual(["c", "b", "a"]);
    });

    it("leaves hidden widgets' positions untouched", () => {
      useDashboardLayoutStore.getState().removeWidget("b");
      useDashboardLayoutStore.getState().reorderPeers(["c", "a"], false);
      expect(useDashboardLayoutStore.getState().order).toEqual(["c", "b", "a"]);
    });
  });

  it("resetLayout() clears everything", () => {
    useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });
    useDashboardLayoutStore.getState().resetLayout();

    const state = useDashboardLayoutStore.getState();
    expect(state.order).toEqual([]);
    expect(state.entries).toEqual({});
  });

  describe("export / import", () => {
    it("round-trips the current layout", () => {
      useDashboardLayoutStore.getState().ensureWidget("w1", { width: 2, height: 1 });
      useDashboardLayoutStore.getState().togglePin("w1");
      const json = useDashboardLayoutStore.getState().exportLayout();

      reset();
      useDashboardLayoutStore.getState().importLayout(json);

      const state = useDashboardLayoutStore.getState();
      expect(state.order).toEqual(["w1"]);
      expect(state.entries.w1).toMatchObject({ width: 2, height: 1, pinned: true });
    });

    it("rejects malformed JSON without touching the current layout", () => {
      useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });

      expect(() => useDashboardLayoutStore.getState().importLayout("not json")).toThrow();
      expect(useDashboardLayoutStore.getState().order).toEqual(["w1"]);
    });

    it("rejects a document missing the expected top-level fields, without mutating state", () => {
      useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });

      expect(() => useDashboardLayoutStore.getState().importLayout(JSON.stringify({ foo: "bar" }))).toThrow();
      expect(useDashboardLayoutStore.getState().order).toEqual(["w1"]);
    });

    it("accepts an 'order' entry with no matching 'entries' record -- structurally valid, just an empty slot", () => {
      expect(() =>
        useDashboardLayoutStore.getState().importLayout(JSON.stringify({ order: ["w2"], entries: {} })),
      ).not.toThrow();
      expect(useDashboardLayoutStore.getState().order).toEqual(["w2"]);
    });

    it("rejects a malformed entry (wrong field type), without mutating state", () => {
      useDashboardLayoutStore.getState().ensureWidget("w1", { width: 1, height: 1 });

      expect(() =>
        useDashboardLayoutStore
          .getState()
          .importLayout(JSON.stringify({ order: ["w2"], entries: { w2: { id: "w2", width: "not-a-number" } } })),
      ).toThrow();
      expect(useDashboardLayoutStore.getState().order).toEqual(["w1"]);
    });
  });
});
