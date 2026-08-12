import { create } from "zustand";
import { persist } from "zustand/middleware";
import { panelRegistry, type PanelZone } from "@/core/panel-registry";

/**
 * Multi-workspace panel layouts -- M8 Phase 3's Universal Workspace
 * Framework.
 *
 * **"Workspace" already meant two other things in this codebase**, and
 * conflating them would be a real bug rather than a naming quibble:
 *
 * 1. `core/workspace-manager.ts` / `stores/workspace.store.ts` -- which
 *    *module* the current route has mounted. One at a time, driven by
 *    the URL. Untouched by this store.
 * 2. The backend `Workspace` entity (M11 Task Group A) -- a data scope
 *    owning projects, notes, tasks and files, reachable at
 *    `/api/v1/workspaces`.
 *
 * This store owns a third, genuinely distinct thing: a **named
 * arrangement of panels**. It links to (2) through
 * `backendWorkspaceId` rather than reimplementing it, so a layout can
 * scope its panels to a real backend workspace. It never copies backend
 * data -- only the id, which is the whole point of a foreign key.
 *
 * **Why layouts persist locally.** There is no backend endpoint for
 * panel geometry, and the backend contract is frozen. A layout is also
 * genuinely per-device state -- the arrangement that suits a 34" monitor
 * is wrong on a laptop -- so `localStorage` is where it belongs rather
 * than a compromise. Same `jarvis.<name>` key convention as
 * `sidebar.store.ts`, `dock.store.ts` and `dashboard-layout.store.ts`.
 */

export const SCHEMA_VERSION = 1;

/** `detached` is a zone in the data model but not a `PanelZone` -- it has
 *  no dock geometry, only a floating frame. */
export type PanelPlacement = PanelZone | "detached";

export interface PanelFrame {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PanelInstance {
  /** Unique per placement, not per panel type -- the same panel may be
   *  open twice in different zones, which is the point of instances. */
  instanceId: string;
  /** Key into `panelRegistry`. */
  panelId: string;
  placement: PanelPlacement;
  /** Position within its zone's stack, ascending. */
  order: number;
  collapsed: boolean;
  /** Share of its zone, as a fraction of that zone's stack. Normalised
   *  so a zone's panels always sum to 1. */
  size: number;
  /** Floating geometry; `null` unless `placement === "detached"`. */
  frame: PanelFrame | null;
  /** Where a detached panel goes back to. Captured at detach time so
   *  "restore" means *back where it was*, not "wherever the default
   *  zone happens to be". */
  restoreTo: { placement: PanelZone; order: number } | null;
}

export interface WorkspaceLayout {
  id: string;
  name: string;
  /** The backend `Workspace.id` this layout scopes its panels to, or
   *  `null` for "not bound". Never the backend workspace's *data*. */
  backendWorkspaceId: string | null;
  panels: PanelInstance[];
  /** Fractions of the shell taken by the edge zones. `main` is whatever
   *  is left, so it can never be squeezed to nothing by arithmetic. */
  zoneSizes: { left: number; right: number; bottom: number };
}

/** Below these the zone reads as a handle rather than a panel. */
export const MIN_ZONE_FRACTION = 0.12;
export const MAX_ZONE_FRACTION = 0.45;
const DEFAULT_ZONE_SIZES = { left: 0.2, right: 0.22, bottom: 0.25 };

export const MIN_PANEL_FRACTION = 0.1;

function uid(prefix: string): string {
  return `${prefix}-${crypto.randomUUID().slice(0, 8)}`;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

/** Panels sharing one zone, in render order. */
export function panelsInZone(layout: WorkspaceLayout, zone: PanelPlacement): PanelInstance[] {
  return layout.panels.filter((p) => p.placement === zone).sort((a, b) => a.order - b.order);
}

/**
 * Make a zone's sizes sum to 1 and renumber its order densely.
 *
 * Called after every structural change rather than trusted to each
 * mutation: closing the middle of three panels leaves both a gap in
 * `order` and a total of 0.66, and every consumer would otherwise need
 * to defend against it.
 */
function normaliseZone(panels: PanelInstance[], zone: PanelPlacement): PanelInstance[] {
  const inZone = panels.filter((p) => p.placement === zone).sort((a, b) => a.order - b.order);
  if (inZone.length === 0) return panels;

  const total = inZone.reduce((sum, p) => sum + p.size, 0);
  const scale = total > 0 ? 1 / total : 0;
  const resized = new Map(
    inZone.map((panel, index) => [
      panel.instanceId,
      {
        ...panel,
        order: index,
        size: total > 0 ? panel.size * scale : 1 / inZone.length,
      },
    ]),
  );
  return panels.map((panel) => resized.get(panel.instanceId) ?? panel);
}

function normaliseAllZones(panels: PanelInstance[]): PanelInstance[] {
  let next = panels;
  for (const zone of ["left", "main", "right", "bottom"] as const) {
    next = normaliseZone(next, zone);
  }
  return next;
}

function newPanelInstance(panelId: string, placement: PanelPlacement, order: number): PanelInstance {
  return {
    instanceId: uid("panel"),
    panelId,
    placement,
    order,
    collapsed: false,
    size: 1,
    frame: placement === "detached" ? { x: 120, y: 120, width: 480, height: 360 } : null,
    restoreTo: null,
  };
}

/**
 * The layout a fresh install opens on: the Dashboard filling `main`,
 * nothing else. Deliberately sparse -- an arrangement the user did not
 * ask for is a worse first impression than an empty one, and every panel
 * is one click away in the panel menu.
 */
export function createDefaultLayout(name = "Default"): WorkspaceLayout {
  return {
    id: uid("ws"),
    name,
    backendWorkspaceId: null,
    panels: [newPanelInstance("home.dashboard", "main", 0)],
    zoneSizes: { ...DEFAULT_ZONE_SIZES },
  };
}

export interface WorkspaceLayoutState {
  workspaces: WorkspaceLayout[];
  activeWorkspaceId: string;

  // --- Workspace lifecycle -------------------------------------------
  createWorkspace: (name?: string) => string;
  renameWorkspace: (id: string, name: string) => void;
  deleteWorkspace: (id: string) => void;
  duplicateWorkspace: (id: string) => string | null;
  resetWorkspace: (id: string) => void;
  setActiveWorkspace: (id: string) => void;
  bindBackendWorkspace: (id: string, backendWorkspaceId: string | null) => void;

  // --- Import / export -----------------------------------------------
  exportWorkspace: (id: string) => string;
  importWorkspace: (json: string) => string;

  // --- Panel lifecycle -------------------------------------------------
  openPanel: (panelId: string, zone?: PanelPlacement) => string | null;
  closePanel: (instanceId: string) => void;
  toggleCollapsed: (instanceId: string) => void;
  movePanel: (instanceId: string, placement: PanelPlacement, order?: number) => void;
  resizePanel: (instanceId: string, size: number) => void;
  resizeZone: (zone: keyof WorkspaceLayout["zoneSizes"], fraction: number) => void;
  detachPanel: (instanceId: string) => void;
  restorePanel: (instanceId: string) => void;
  moveDetached: (instanceId: string, frame: Partial<PanelFrame>) => void;
}

export class WorkspaceImportError extends Error {}

/** Structural validation for an imported document. Never trusts a file's
 *  shape -- same rule `core/settings-framework.ts`'s `import()` follows. */
function parseImported(json: string): WorkspaceLayout {
  let parsed: unknown;
  try {
    parsed = JSON.parse(json);
  } catch {
    throw new WorkspaceImportError("That file is not valid JSON.");
  }
  if (!parsed || typeof parsed !== "object") {
    throw new WorkspaceImportError("That file does not contain a workspace.");
  }
  const doc = parsed as { schemaVersion?: unknown; workspace?: unknown };
  if (doc.schemaVersion !== SCHEMA_VERSION) {
    throw new WorkspaceImportError(
      `Unsupported workspace format (expected version ${SCHEMA_VERSION}).`,
    );
  }
  const workspace = doc.workspace as Partial<WorkspaceLayout> | undefined;
  if (!workspace || typeof workspace.name !== "string" || !Array.isArray(workspace.panels)) {
    throw new WorkspaceImportError("That workspace is missing a name or its panels.");
  }

  // Panels referencing a panel type this build does not have are dropped
  // rather than rejected: a layout exported from a build with an extra
  // module should still import, minus what cannot be rendered.
  const panels = (workspace.panels as PanelInstance[])
    .filter((panel) => panel && typeof panel.panelId === "string" && panelRegistry.get(panel.panelId))
    .map((panel, index) => ({
      ...newPanelInstance(panel.panelId, panel.placement ?? "main", index),
      collapsed: Boolean(panel.collapsed),
      size: typeof panel.size === "number" && panel.size > 0 ? panel.size : 1,
      frame: panel.placement === "detached" ? (panel.frame ?? null) : null,
    }));

  const sizes = workspace.zoneSizes ?? DEFAULT_ZONE_SIZES;
  return {
    id: uid("ws"),
    name: workspace.name,
    backendWorkspaceId:
      typeof workspace.backendWorkspaceId === "string" ? workspace.backendWorkspaceId : null,
    panels: normaliseAllZones(panels),
    zoneSizes: {
      left: clamp(sizes.left ?? DEFAULT_ZONE_SIZES.left, MIN_ZONE_FRACTION, MAX_ZONE_FRACTION),
      right: clamp(sizes.right ?? DEFAULT_ZONE_SIZES.right, MIN_ZONE_FRACTION, MAX_ZONE_FRACTION),
      bottom: clamp(sizes.bottom ?? DEFAULT_ZONE_SIZES.bottom, MIN_ZONE_FRACTION, MAX_ZONE_FRACTION),
    },
  };
}

const initialWorkspace = createDefaultLayout();

export const useWorkspaceLayoutStore = create<WorkspaceLayoutState>()(
  persist(
    (set, get) => {
      /** Apply `mutate` to the active layout. Every panel action goes
       *  through here so none of them can forget to normalise or to
       *  target the right workspace. */
      function updateActive(mutate: (layout: WorkspaceLayout) => WorkspaceLayout): void {
        set((state) => ({
          workspaces: state.workspaces.map((workspace) =>
            workspace.id === state.activeWorkspaceId ? mutate(workspace) : workspace,
          ),
        }));
      }

      function updatePanels(
        mutate: (panels: PanelInstance[]) => PanelInstance[],
      ): void {
        updateActive((layout) => ({ ...layout, panels: normaliseAllZones(mutate(layout.panels)) }));
      }

      return {
        workspaces: [initialWorkspace],
        activeWorkspaceId: initialWorkspace.id,

        createWorkspace: (name) => {
          const workspace = createDefaultLayout(name ?? `Workspace ${get().workspaces.length + 1}`);
          set((state) => ({
            workspaces: [...state.workspaces, workspace],
            activeWorkspaceId: workspace.id,
          }));
          return workspace.id;
        },

        renameWorkspace: (id, name) => {
          const trimmed = name.trim();
          if (!trimmed) return; // a nameless workspace is unselectable in the switcher
          set((state) => ({
            workspaces: state.workspaces.map((w) => (w.id === id ? { ...w, name: trimmed } : w)),
          }));
        },

        deleteWorkspace: (id) => {
          set((state) => {
            // Never delete the last one -- an app with no workspace has
            // nothing to render, and "delete" is not "factory reset".
            if (state.workspaces.length <= 1) return state;
            const workspaces = state.workspaces.filter((w) => w.id !== id);
            return {
              workspaces,
              activeWorkspaceId:
                state.activeWorkspaceId === id
                  ? (workspaces[0]?.id ?? state.activeWorkspaceId)
                  : state.activeWorkspaceId,
            };
          });
        },

        duplicateWorkspace: (id) => {
          const source = get().workspaces.find((w) => w.id === id);
          if (!source) return null;
          const copy: WorkspaceLayout = {
            ...source,
            id: uid("ws"),
            name: `${source.name} copy`,
            // Fresh instance ids: two workspaces sharing one instance id
            // would make every panel action ambiguous.
            panels: source.panels.map((panel) => ({ ...panel, instanceId: uid("panel") })),
            zoneSizes: { ...source.zoneSizes },
          };
          set((state) => ({ workspaces: [...state.workspaces, copy], activeWorkspaceId: copy.id }));
          return copy.id;
        },

        resetWorkspace: (id) => {
          set((state) => ({
            workspaces: state.workspaces.map((w) =>
              // Keeps the identity (id, name, backend binding) and
              // replaces only the arrangement -- "reset" means the
              // layout, not the workspace.
              w.id === id
                ? { ...createDefaultLayout(w.name), id: w.id, backendWorkspaceId: w.backendWorkspaceId }
                : w,
            ),
          }));
        },

        setActiveWorkspace: (id) => {
          if (!get().workspaces.some((w) => w.id === id)) return;
          set({ activeWorkspaceId: id });
        },

        bindBackendWorkspace: (id, backendWorkspaceId) => {
          set((state) => ({
            workspaces: state.workspaces.map((w) => (w.id === id ? { ...w, backendWorkspaceId } : w)),
          }));
        },

        exportWorkspace: (id) => {
          const workspace = get().workspaces.find((w) => w.id === id);
          if (!workspace) throw new WorkspaceImportError("No such workspace.");
          // Same `{schemaVersion, ...}` envelope `ModuleSettings.export()`
          // and `dashboard-layout.store.ts` already establish.
          return JSON.stringify({ schemaVersion: SCHEMA_VERSION, workspace }, null, 2);
        },

        importWorkspace: (json) => {
          const workspace = parseImported(json);
          set((state) => ({
            workspaces: [...state.workspaces, workspace],
            activeWorkspaceId: workspace.id,
          }));
          return workspace.id;
        },

        openPanel: (panelId, zone) => {
          const contribution = panelRegistry.get(panelId);
          if (!contribution) return null;

          const layout = get().workspaces.find((w) => w.id === get().activeWorkspaceId);
          if (!layout) return null;

          // Already open in this workspace: focus it rather than opening
          // a duplicate the user did not ask for. Re-opening a collapsed
          // panel expands it, which is what clicking its menu entry
          // plainly means.
          const existing = layout.panels.find((panel) => panel.panelId === panelId);
          if (existing) {
            if (existing.collapsed) get().toggleCollapsed(existing.instanceId);
            return existing.instanceId;
          }

          const placement = zone ?? contribution.defaultZone;
          const instance = newPanelInstance(
            panelId,
            placement,
            panelsInZone(layout, placement).length,
          );
          updatePanels((panels) => [...panels, instance]);
          return instance.instanceId;
        },

        closePanel: (instanceId) => {
          updatePanels((panels) => panels.filter((panel) => panel.instanceId !== instanceId));
        },

        toggleCollapsed: (instanceId) => {
          updatePanels((panels) =>
            panels.map((panel) =>
              panel.instanceId === instanceId ? { ...panel, collapsed: !panel.collapsed } : panel,
            ),
          );
        },

        movePanel: (instanceId, placement, order) => {
          updatePanels((panels) =>
            panels.map((panel) =>
              panel.instanceId === instanceId
                ? {
                    ...panel,
                    placement,
                    // `order + 0.5` lands the panel *between* two
                    // existing ones; `normaliseZone` then renumbers to
                    // dense integers. Cheaper and less error-prone than
                    // splicing the array and rewriting every neighbour.
                    order: order === undefined ? Number.MAX_SAFE_INTEGER : order + 0.5,
                    frame: placement === "detached" ? (panel.frame ?? { x: 120, y: 120, width: 480, height: 360 }) : null,
                  }
                : panel,
            ),
          );
        },

        resizePanel: (instanceId, size) => {
          updatePanels((panels) => {
            const target = panels.find((panel) => panel.instanceId === instanceId);
            if (!target || target.placement === "detached") return panels;

            const siblings = panels.filter(
              (panel) => panel.placement === target.placement && panel.instanceId !== instanceId,
            );
            if (siblings.length === 0) return panels;

            const next = clamp(size, MIN_PANEL_FRACTION, 1 - MIN_PANEL_FRACTION * siblings.length);
            // The remainder is shared among siblings in proportion to
            // what they already had, so resizing one panel does not
            // silently even out every other panel in the zone.
            const siblingTotal = siblings.reduce((sum, panel) => sum + panel.size, 0);
            const remaining = 1 - next;
            return panels.map((panel) => {
              if (panel.instanceId === instanceId) return { ...panel, size: next };
              if (panel.placement !== target.placement) return panel;
              const share = siblingTotal > 0 ? panel.size / siblingTotal : 1 / siblings.length;
              return { ...panel, size: Math.max(MIN_PANEL_FRACTION, remaining * share) };
            });
          });
        },

        resizeZone: (zone, fraction) => {
          updateActive((layout) => ({
            ...layout,
            zoneSizes: {
              ...layout.zoneSizes,
              [zone]: clamp(fraction, MIN_ZONE_FRACTION, MAX_ZONE_FRACTION),
            },
          }));
        },

        detachPanel: (instanceId) => {
          updatePanels((panels) =>
            panels.map((panel) => {
              if (panel.instanceId !== instanceId || panel.placement === "detached") return panel;
              return {
                ...panel,
                restoreTo: { placement: panel.placement, order: panel.order },
                placement: "detached",
                collapsed: false,
                frame: panel.frame ?? {
                  // Cascade so two detached panels do not land exactly
                  // on top of each other.
                  x: 120 + panels.filter((p) => p.placement === "detached").length * 28,
                  y: 120 + panels.filter((p) => p.placement === "detached").length * 28,
                  width: 480,
                  height: 360,
                },
              };
            }),
          );
        },

        restorePanel: (instanceId) => {
          updatePanels((panels) =>
            panels.map((panel) => {
              if (panel.instanceId !== instanceId) return panel;
              const back = panel.restoreTo;
              return {
                ...panel,
                placement: back?.placement ?? panelRegistry.get(panel.panelId)?.defaultZone ?? "main",
                order: back?.order ?? Number.MAX_SAFE_INTEGER,
                restoreTo: null,
                frame: null,
              };
            }),
          );
        },

        moveDetached: (instanceId, frame) => {
          updateActive((layout) => ({
            ...layout,
            panels: layout.panels.map((panel) =>
              panel.instanceId === instanceId && panel.frame
                ? { ...panel, frame: { ...panel.frame, ...frame } }
                : panel,
            ),
          }));
        },
      };
    },
    {
      name: "jarvis.workspace-layouts",
      version: SCHEMA_VERSION,
      /**
       * Hydration is triggered by the startup sequence
       * (`core/startup-orchestrator.ts`), not automatically on import.
       *
       * `merge` below drops panels whose contribution is not registered,
       * and Zustand's automatic hydration runs the moment this module is
       * first imported -- which is whenever some component happens to
       * import it, quite possibly before `registerCorePanels()` has run.
       * A layout restored at that moment would have every one of its
       * panels dropped as "unknown" and come back empty, and the user
       * would have lost their arrangement to an import-order accident.
       * Making the order explicit is the only way it stays correct.
       */
      skipHydration: true,
      // Only the data, never the actions.
      partialize: (state) => ({
        workspaces: state.workspaces,
        activeWorkspaceId: state.activeWorkspaceId,
      }),
      /**
       * A persisted layout can outlive the panels it references -- a
       * module removed between releases, or a workspace exported from a
       * build that had one this build does not. Dropping unknown panels
       * on rehydrate is what makes "Workspace Restore" safe: the
       * alternative is a container asked to render a panel type that no
       * longer exists.
       */
      merge: (persisted, current) => {
        const saved = persisted as Partial<WorkspaceLayoutState> | undefined;
        if (!saved?.workspaces?.length) return current;
        const workspaces = saved.workspaces.map((workspace) => ({
          ...workspace,
          panels: normaliseAllZones(
            workspace.panels.filter((panel) => panelRegistry.get(panel.panelId)),
          ),
        }));
        return {
          ...current,
          workspaces,
          activeWorkspaceId: workspaces.some((w) => w.id === saved.activeWorkspaceId)
            ? (saved.activeWorkspaceId as string)
            : workspaces[0].id,
        };
      },
    },
  ),
);

/** The active layout. A selector rather than stored state -- two fields
 *  that can disagree about which workspace is active is a bug waiting to
 *  happen. */
export function selectActiveWorkspace(state: WorkspaceLayoutState): WorkspaceLayout {
  return (
    state.workspaces.find((w) => w.id === state.activeWorkspaceId) ??
    state.workspaces[0] ??
    createDefaultLayout()
  );
}
