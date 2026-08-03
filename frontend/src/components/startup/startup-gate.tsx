import { useEffect, useRef, useState } from "react";
import { useReducedMotionConfig } from "motion/react";
import { StartupSequence } from "@/components/startup/startup-sequence";
import { runStartupSequence } from "@/core/startup-orchestrator";
import { CommandPaletteProvider } from "@/providers/command-palette-provider";
import { DeveloperProvider } from "@/providers/developer-provider";
import { NotificationProvider } from "@/providers/notification-provider";
import { QueryProvider } from "@/providers/query-provider";
import { RouterProvider } from "@/providers/router-provider";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

/** The rest of the real provider chain -- everything that used to sit
 *  directly under `MotionConfig` in `providers/app-providers.tsx`
 *  before this task group, extracted so `StartupGate` can render it
 *  only once both real initialization and (unless skipped) the
 *  startup choreography have finished. */
function RealApp() {
  return (
    <QueryProvider>
      <DeveloperProvider>
        <CommandPaletteProvider>
          <NotificationProvider>
            <RouterProvider />
          </NotificationProvider>
        </CommandPaletteProvider>
      </DeveloperProvider>
    </QueryProvider>
  );
}

/**
 * Gates the real app behind the startup sequence (Phase 4, Task Group
 * I). Reveals `RealApp` only once BOTH real initialization
 * (`core/startup-orchestrator.ts` -- `ApplicationRegistry`/
 * `dashboardWidgetRegistry`/`statusBarRegistry` genuinely populated,
 * which `WorkspaceManager` and friends assume by the time they mount)
 * and the choreographed animation are done -- whichever finishes last.
 * Skips the choreography (revealing as soon as real work finishes)
 * when the user has set `skipStartupAnimation`
 * (`stores/accessibility-preferences.store.ts`), OR when reduced motion
 * is in effect -- via `useReducedMotionConfig()`, which combines the OS
 * `prefers-reduced-motion` media query with the real, persisted
 * `reducedMotion` preference (`AccessibleMotionConfig` feeds it into
 * `MotionConfig`, Task Group K) -- per the accessibility requirement
 * that disabling the animation launches straight into the dashboard.
 */
export function StartupGate() {
  const skipPreference = useAccessibilityPreferencesStore((s) => s.skipStartupAnimation);
  const reducedMotion = useReducedMotionConfig();
  const skip = skipPreference || reducedMotion;

  const [ready, setReady] = useState(false);
  const workDoneRef = useRef(false);
  const choreographyDoneRef = useRef(false);

  const revealIfReady = () => {
    if (workDoneRef.current && (skip || choreographyDoneRef.current)) {
      setReady(true);
    }
  };

  useEffect(() => {
    let cancelled = false;
    void runStartupSequence().then(() => {
      if (cancelled) return;
      workDoneRef.current = true;
      revealIfReady();
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs exactly once; revealIfReady reads current refs/state via closure at call time.
  }, []);

  if (ready) return <RealApp />;
  // Real init is fast today (well under 100ms -- see startup-orchestrator.ts)
  // and this branch renders nothing while it finishes, rather than a
  // fake spinner for a delay too short to perceive.
  if (skip) return null;

  return (
    <StartupSequence
      onComplete={() => {
        choreographyDoneRef.current = true;
        revealIfReady();
      }}
    />
  );
}
