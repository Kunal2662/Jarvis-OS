/**
 * The Window Interface (Task 14) -- extends `services/window/window-service.ts`
 * (Phase 1, wraps Tauri's real window API) with the per-module surface
 * this phase adds: `focus`/`detach`. Today there is exactly one Tauri
 * window (the main window), so every module currently shares it;
 * `detach()` is the documented seam for "Future Multi-window" (Task 14's
 * own item) -- deliberately throwing rather than faking a second window
 * that doesn't exist.
 */

import { windowService } from "@/services/window/window-service";

export interface WindowInterface {
  open(): Promise<void>;
  close(): Promise<void>;
  minimize(): Promise<void>;
  maximize(): Promise<void>;
  focus(): Promise<void>;
  resize(width: number, height: number): Promise<void>;
  /** Pulls this module out of the main window into its own -- not yet
   *  implemented; every module shares the single main window today. */
  detach(): Promise<never>;
}

/**
 * The current, single-window implementation every module gets today.
 * `open`/`close`/`resize` on the shared main window are meaningful only
 * in a hypothetical multi-window future; until `detach()` is real, they
 * proxy to the one window every module already renders inside, which is
 * never actually closed/resized by a module's own action -- documented
 * here rather than silently allowed to do something surprising.
 */
export function createWindowInterface(_moduleId: string): WindowInterface {
  return {
    open: async () => {
      await windowService.unmaximize();
    },
    close: async () => {
      throw new Error("Per-module window close is not available until detach() exists (multi-window).");
    },
    minimize: async () => {
      await windowService.minimize();
    },
    maximize: async () => {
      await windowService.maximize();
    },
    focus: async () => {
      // The main window is always focused when its content is visible
      // in a single-window app -- no-op until multi-window exists.
    },
    resize: async () => {
      throw new Error("Per-module window resize is not available until detach() exists (multi-window).");
    },
    detach: async () => {
      throw new Error(
        "Multi-window support is not implemented yet (Task 14's own documented future item).",
      );
    },
  };
}
