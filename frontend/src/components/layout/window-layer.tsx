/**
 * Reserved DesktopShell region for future floating/detached module
 * windows (`core/interfaces/window-interface.ts`'s documented,
 * not-yet-implemented `detach()` seam). Renders nothing today -- every
 * module shares the single main window, so there is nothing to layer
 * yet. Exists as a named architectural anchor so DesktopShell's region
 * set doesn't need to change shape again once multi-window support
 * ships; that future work fills this component in, not DesktopShell.
 */
export function WindowLayer() {
  return null;
}
