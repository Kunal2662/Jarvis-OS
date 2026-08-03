import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface WidgetLayoutEntry {
  id: string;
  /** Grid units, matching `DashboardWidgetContribution.defaultSize`
   *  (`core/dashboard-widget-registry.ts`) -- starts at the
   *  contribution's own default, then follows whatever the user resizes
   *  it to via `resizeWidget()`. */
  width: number;
  height: number;
  /** Pinned widgets always render before unpinned ones and can't be
   *  removed while pinned (must unpin first) -- same "pin is a
   *  rendering-order preference, not a visibility one" shape as
   *  `stores/dock.store.ts`'s pinned items, applied to a grid instead of
   *  a list. */
  pinned: boolean;
  /** False = "removed" from the grid without forgetting its layout --
   *  `addWidget()` restores it exactly where it was rather than
   *  re-appending it, so removing and re-adding a widget isn't
   *  destructive. */
  visible: boolean;
}

interface PersistedLayout {
  schemaVersion: number;
  order: string[];
  entries: Record<string, WidgetLayoutEntry>;
}

interface DashboardLayoutState {
  order: string[];
  entries: Record<string, WidgetLayoutEntry>;
  /** Registers a widget id into the layout the first time the grid
   *  sees it (a newly registered contribution, or a fresh install) --
   *  a no-op if an entry already exists, so calling it on every render
   *  for every currently-available widget never overwrites a user's
   *  existing size/position/pin choice. */
  ensureWidget: (id: string, defaultSize: { width: number; height: number }) => void;
  /** Soft-remove: keeps the entry (so its size/pin state survives) but
   *  hides it from the grid until `addWidget()` brings it back. Refuses
   *  to remove a pinned widget -- unpin first, matching the Dock's own
   *  "pin is a deliberate extra step to undo" behavior. */
  removeWidget: (id: string) => void;
  addWidget: (id: string) => void;
  resizeWidget: (id: string, size: { width: number; height: number }) => void;
  /** Reorders `id` relative to its same-pinned-state peers only (a
   *  pinned widget only ever reorders among other pinned widgets, an
   *  unpinned one only among other unpinned ones) -- swapping with a
   *  raw-array neighbor of the *other* pin state would be a no-op from
   *  the user's point of view, since rendering partitions pinned before
   *  unpinned regardless of their interleaved storage order. "up"/"down"
   *  swap with the adjacent peer; "start"/"end" swap with the first/last
   *  peer, which moves `id` to that end of its group. */
  moveWidget: (id: string, direction: "up" | "down" | "start" | "end") => void;
  /** Applies a full drag-produced reorder of one peer group (Task Group
   *  L, additive alongside `moveWidget`'s discrete up/down/start/end
   *  steps -- neither replaces the other). `peerIds` must be a
   *  permutation of that group's current members, exactly what
   *  `Reorder.Group`'s own `onReorder` callback provides. Walks the
   *  stored `order` array and, at each position currently held by a
   *  member of the target pinned/unpinned group, substitutes the next
   *  id from the new sequence -- every other id (the opposite pin
   *  group, and hidden widgets) keeps its exact position untouched. */
  reorderPeers: (peerIds: string[], pinned: boolean) => void;
  togglePin: (id: string) => void;
  resetLayout: () => void;
  /** One JSON document, matching `core/settings-framework.ts`'s
   *  `{schemaVersion, values}` export envelope shape. */
  exportLayout: () => string;
  /** Validated before being applied -- malformed or corrupted input
   *  (wrong shape, non-array order, non-object entries) is rejected
   *  rather than partially applied, so a bad import can't leave the
   *  store in an inconsistent state. Never trusts the imported
   *  `schemaVersion` blindly, matching `ModuleSettings.import()`'s own
   *  "validate, don't assume" discipline. */
  importLayout: (json: string) => void;
}

const SCHEMA_VERSION = 1;

function isValidEntry(value: unknown): value is WidgetLayoutEntry {
  if (typeof value !== "object" || value === null) return false;
  const entry = value as Record<string, unknown>;
  return (
    typeof entry.id === "string" &&
    typeof entry.width === "number" &&
    typeof entry.height === "number" &&
    typeof entry.pinned === "boolean" &&
    typeof entry.visible === "boolean"
  );
}

function parseImportedLayout(json: string): PersistedLayout {
  const parsed: unknown = JSON.parse(json);
  if (typeof parsed !== "object" || parsed === null) {
    throw new Error("Imported layout must be a JSON object.");
  }
  const candidate = parsed as Record<string, unknown>;
  if (!Array.isArray(candidate.order) || !candidate.order.every((id) => typeof id === "string")) {
    throw new Error("Imported layout is missing a valid 'order' array.");
  }
  if (typeof candidate.entries !== "object" || candidate.entries === null) {
    throw new Error("Imported layout is missing a valid 'entries' object.");
  }
  const entries = candidate.entries as Record<string, unknown>;
  for (const [id, entry] of Object.entries(entries)) {
    if (!isValidEntry(entry) || entry.id !== id) {
      throw new Error(`Imported layout has an invalid entry for widget "${id}".`);
    }
  }
  return {
    schemaVersion: SCHEMA_VERSION,
    order: candidate.order as string[],
    entries: entries as Record<string, WidgetLayoutEntry>,
  };
}

/**
 * The Dashboard Widget Grid's own preference layer (Phase 3, Task Group
 * F) -- which registered widgets the user currently sees, in what
 * order, at what size, and whether pinned. Distinct from
 * `dashboardWidgetRegistry` (`core/dashboard-widget-registry.ts`), the
 * same split `stores/dock.store.ts` (preference) and
 * `core/application-registry.ts` (what exists) already establish: this
 * store never invents widgets, it only remembers the user's layout
 * choices for widgets the registry says exist. `reorderPeers()` (Phase
 * 4, Task Group L) added drag-to-reorder support, additive alongside
 * `moveWidget()`'s existing discrete step buttons -- both operate on
 * the same `order` array, so the two interaction models can never
 * disagree about the current layout.
 */
export const useDashboardLayoutStore = create<DashboardLayoutState>()(
  persist(
    (set, get) => ({
      order: [],
      entries: {},
      ensureWidget: (id, defaultSize) => {
        if (get().entries[id]) return;
        set((s) => ({
          order: [...s.order, id],
          entries: {
            ...s.entries,
            [id]: { id, width: defaultSize.width, height: defaultSize.height, pinned: false, visible: true },
          },
        }));
      },
      removeWidget: (id) =>
        set((s) => {
          const entry = s.entries[id];
          if (!entry || entry.pinned) return s;
          return { entries: { ...s.entries, [id]: { ...entry, visible: false } } };
        }),
      addWidget: (id) =>
        set((s) => {
          const entry = s.entries[id];
          if (!entry) return s;
          return { entries: { ...s.entries, [id]: { ...entry, visible: true } } };
        }),
      resizeWidget: (id, size) =>
        set((s) => {
          const entry = s.entries[id];
          if (!entry) return s;
          return { entries: { ...s.entries, [id]: { ...entry, width: size.width, height: size.height } } };
        }),
      moveWidget: (id, direction) =>
        set((s) => {
          const entry = s.entries[id];
          if (!entry) return s;

          const peers = s.order.filter((otherId) => s.entries[otherId]?.pinned === entry.pinned);
          const peerIndex = peers.indexOf(id);
          if (peerIndex === -1) return s;

          const targetPeerIndex =
            direction === "start"
              ? 0
              : direction === "end"
                ? peers.length - 1
                : direction === "up"
                  ? peerIndex - 1
                  : peerIndex + 1;
          if (targetPeerIndex < 0 || targetPeerIndex >= peers.length || targetPeerIndex === peerIndex) return s;

          const targetId = peers[targetPeerIndex];
          const order = [...s.order];
          const fromIndex = order.indexOf(id);
          const toIndex = order.indexOf(targetId);
          [order[fromIndex], order[toIndex]] = [order[toIndex], order[fromIndex]];
          return { order };
        }),
      reorderPeers: (peerIds, pinned) =>
        set((s) => {
          const peerSet = new Set(peerIds);
          let nextIndex = 0;
          const order = s.order.map((id) => {
            if (peerSet.has(id) && s.entries[id]?.pinned === pinned) {
              return peerIds[nextIndex++];
            }
            return id;
          });
          return { order };
        }),
      togglePin: (id) =>
        set((s) => {
          const entry = s.entries[id];
          if (!entry) return s;
          return { entries: { ...s.entries, [id]: { ...entry, pinned: !entry.pinned } } };
        }),
      resetLayout: () => set({ order: [], entries: {} }),
      exportLayout: () => {
        const { order, entries } = get();
        const payload: PersistedLayout = { schemaVersion: SCHEMA_VERSION, order, entries };
        return JSON.stringify(payload);
      },
      importLayout: (json) => {
        const parsed = parseImportedLayout(json);
        set({ order: parsed.order, entries: parsed.entries });
      },
    }),
    {
      name: "jarvis.dashboard-layout",
      partialize: (s) => ({ order: s.order, entries: s.entries }),
    },
  ),
);
