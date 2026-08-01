import { isTauri } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { useWindowStore } from "@/stores/window.store";

/**
 * Window Management foundation (Task 14). Wraps Tauri's real window API
 * (`@tauri-apps/api/window`) -- resizable/maximize/minimize/fullscreen
 * are Tauri's own native window chrome, not reimplemented in React.
 * Every call is guarded by `isTauri()`: this code also runs in a plain
 * browser during development (Vite's dev server preview), where none of
 * these APIs exist -- it degrades to a no-op there instead of throwing.
 *
 * DPI awareness and multi-monitor support need no code here: Tauri's
 * webview is DPI-aware by the OS's own scaling, and `Window`'s
 * `currentMonitor()`/`availableMonitors()` (called from a future
 * multi-monitor-aware feature, not this foundation) already expose
 * per-monitor geometry -- this service doesn't need to duplicate either.
 */

async function withWindow<T>(fn: (window: ReturnType<typeof getCurrentWindow>) => Promise<T>): Promise<T | null> {
  if (!isTauri()) return null;
  return fn(getCurrentWindow());
}

export const windowService = {
  maximize: () => withWindow((w) => w.maximize()),
  unmaximize: () => withWindow((w) => w.unmaximize()),
  toggleMaximize: () => withWindow((w) => w.toggleMaximize()),
  minimize: () => withWindow((w) => w.minimize()),
  async setFullscreen(fullscreen: boolean) {
    await withWindow((w) => w.setFullscreen(fullscreen));
  },
  close: () => withWindow((w) => w.close()),

  /**
   * Mirrors the window's real maximize/fullscreen state into
   * `stores/window.store.ts` and keeps listening for external changes
   * (the user dragging a maximize/restore via the OS title bar, not just
   * through this app's own UI). Returns an unsubscribe function; call
   * once from a top-level effect (e.g. DesktopShell), not per-component.
   */
  async subscribeToWindowState(): Promise<() => void> {
    if (!isTauri()) return () => {};
    const win = getCurrentWindow();
    const { setMaximized, setFullscreen, setSize } = useWindowStore.getState();

    const [isMaximized, isFullscreen, size] = await Promise.all([
      win.isMaximized(),
      win.isFullscreen(),
      win.innerSize(),
    ]);
    setMaximized(isMaximized);
    setFullscreen(isFullscreen);
    setSize(size.width, size.height);

    const unlistenResized = await win.onResized(async () => {
      setMaximized(await win.isMaximized());
      const newSize = await win.innerSize();
      setSize(newSize.width, newSize.height);
    });

    return () => {
      unlistenResized();
    };
  },
};
