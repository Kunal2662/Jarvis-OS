import type { ReactNode } from "react";
import { MotionConfig } from "motion/react";
import { StartupGate } from "@/components/startup/startup-gate";
import { ErrorBoundary } from "@/providers/error-boundary";
import { StoreProvider } from "@/providers/store-provider";
import { ThemeProvider } from "@/providers/theme-provider";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

/**
 * The real, persisted `reducedMotion` preference (Task Group K) is an
 * app-level override on top of `"user"` mode's own OS-level
 * `prefers-reduced-motion` detection. `"always"` here makes every
 * *declarative* Motion animation in the tree (`animate`/`variants`
 * props -- `DesktopShell`'s stagger reveal, `JarvisLogo`'s pulse, etc.)
 * skip/instant-apply automatically, since Motion's own rendering engine
 * already consults `MotionConfig`'s `reducedMotion` internally for
 * those. It does **not** automatically reach the public
 * `useReducedMotion()` hook -- that hook only ever reads the OS media
 * query and ignores this context entirely, which is exactly why real
 * call sites that branch on their own logic (`components/startup/
 * startup-gate.tsx`, `components/voice/voice-waveform-renderer.tsx`)
 * use `useReducedMotionConfig()` instead -- the hook Motion itself uses
 * internally to combine the two.
 *
 * A separate component, rendered as `StoreProvider`'s child (same
 * reasoning as `ThemeProvider` reading `useThemeStore` the same way)
 * rather than read directly in `AppProviders` -- `StoreProvider` gates
 * its children on hydration by not rendering them at all until it's
 * done, so a hook read *inside* that gate can never observe the
 * pre-hydration default the way one read *above* it could.
 */
export function AccessibleMotionConfig({ children }: { children: ReactNode }) {
  const forceReducedMotion = useAccessibilityPreferencesStore((s) => s.reducedMotion);
  return <MotionConfig reducedMotion={forceReducedMotion ? "always" : "user"}>{children}</MotionConfig>;
}

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
          <AccessibleMotionConfig>
            <StartupGate />
          </AccessibleMotionConfig>
        </ThemeProvider>
      </StoreProvider>
    </ErrorBoundary>
  );
}
