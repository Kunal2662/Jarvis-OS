import { MotionConfig } from "motion/react";
import { StartupGate } from "@/components/startup/startup-gate";
import { ErrorBoundary } from "@/providers/error-boundary";
import { StoreProvider } from "@/providers/store-provider";
import { ThemeProvider } from "@/providers/theme-provider";

/**
 * The full provider stack, composed once here so `main.tsx` stays a
 * one-line mount. Order matters: StoreProvider gates everything below it
 * on Zustand's persisted stores finishing rehydration (so ThemeProvider
 * never flashes the default theme), ErrorBoundary wraps everything so a
 * failure anywhere below it degrades gracefully instead of white-screening
 * the app.
 *
 * `StartupGate` (Phase 4, Task Group I) owns everything that used to
 * render directly here (`QueryProvider`/`DeveloperProvider`/
 * `CommandPaletteProvider`/`NotificationProvider`/`RouterProvider`) --
 * it reveals that real subtree only once both real initialization
 * (`core/startup-orchestrator.ts`) and the startup choreography are
 * done, rather than mounting it immediately.
 */
export function AppProviders() {
  return (
    <ErrorBoundary>
      <StoreProvider>
        <ThemeProvider>
          {/* `reducedMotion="user"` makes every Motion component in the
              tree respect the OS-level prefers-reduced-motion setting
              automatically (ARCHITECTURE.md section 16) -- the plain-CSS
              override in index.css handles everything that isn't a
              Motion component. */}
          <MotionConfig reducedMotion="user">
            <StartupGate />
          </MotionConfig>
        </ThemeProvider>
      </StoreProvider>
    </ErrorBoundary>
  );
}
