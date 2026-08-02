import { MotionConfig } from "motion/react";
import { CommandPaletteProvider } from "@/providers/command-palette-provider";
import { DeveloperProvider } from "@/providers/developer-provider";
import { ErrorBoundary } from "@/providers/error-boundary";
import { NotificationProvider } from "@/providers/notification-provider";
import { QueryProvider } from "@/providers/query-provider";
import { RouterProvider } from "@/providers/router-provider";
import { StoreProvider } from "@/providers/store-provider";
import { ThemeProvider } from "@/providers/theme-provider";

/**
 * The full provider stack, composed once here so `main.tsx` stays a
 * one-line mount. Order matters: StoreProvider gates everything below it
 * on Zustand's persisted stores finishing rehydration (so ThemeProvider
 * never flashes the default theme), ErrorBoundary wraps everything so a
 * failure anywhere below it degrades gracefully instead of white-screening
 * the app.
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
            <QueryProvider>
              <DeveloperProvider>
                <CommandPaletteProvider>
                  <NotificationProvider>
                    <RouterProvider />
                  </NotificationProvider>
                </CommandPaletteProvider>
              </DeveloperProvider>
            </QueryProvider>
          </MotionConfig>
        </ThemeProvider>
      </StoreProvider>
    </ErrorBoundary>
  );
}
