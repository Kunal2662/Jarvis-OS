import { useState } from "react";
import { Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { StartupSequence } from "@/components/startup/startup-sequence";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

/**
 * Developer Mode's Startup Preview (Phase 4, Task Group I) -- the real
 * `StartupSequence` component the app plays once per real launch
 * (`components/startup/startup-gate.tsx`), replayable here on demand
 * since it otherwise only runs once per page load. "Replay" mounts the
 * exact same component with the exact same choreography; there is no
 * separate preview-only animation. The three preference toggles drive
 * the real, persisted `accessibility-preferences.store.ts` -- the same
 * store `StartupGate`/`MotionConfig`/every glass surface reads on every
 * real launch. Settings > Accessibility (Task Group K) is the real
 * end-user surface for these same toggles; this panel is a QA
 * convenience, not a second source of truth.
 */
export function StartupPreview() {
  const [replaying, setReplaying] = useState(false);
  const skipStartupAnimation = useAccessibilityPreferencesStore((s) => s.skipStartupAnimation);
  const setSkipStartupAnimation = useAccessibilityPreferencesStore((s) => s.setSkipStartupAnimation);
  const reducedMotion = useAccessibilityPreferencesStore((s) => s.reducedMotion);
  const setReducedMotion = useAccessibilityPreferencesStore((s) => s.setReducedMotion);
  const disableGlassEffects = useAccessibilityPreferencesStore((s) => s.disableGlassEffects);
  const setDisableGlassEffects = useAccessibilityPreferencesStore((s) => s.setDisableGlassEffects);

  return (
    <div className="flex flex-1 flex-col gap-4 p-4">
      <Button variant="secondary" size="sm" disabled={replaying} onClick={() => setReplaying(true)}>
        <Play aria-hidden="true" />
        Replay startup sequence
      </Button>

      <div>
        <p className="mb-2 text-caption font-medium text-muted-foreground">Preferences (real, persisted)</p>
        <div className="flex flex-col gap-1.5">
          <Button
            variant={skipStartupAnimation ? "default" : "outline"}
            size="sm"
            onClick={() => setSkipStartupAnimation(!skipStartupAnimation)}
          >
            Skip startup animation: {skipStartupAnimation ? "On" : "Off"}
          </Button>
          <Button
            variant={reducedMotion ? "default" : "outline"}
            size="sm"
            onClick={() => setReducedMotion(!reducedMotion)}
          >
            Reduced motion: {reducedMotion ? "On" : "Off"}
          </Button>
          <Button
            variant={disableGlassEffects ? "default" : "outline"}
            size="sm"
            onClick={() => setDisableGlassEffects(!disableGlassEffects)}
          >
            Disable glass effects: {disableGlassEffects ? "On" : "Off"}
          </Button>
        </div>
      </div>

      {replaying && <StartupSequence onComplete={() => setReplaying(false)} />}
    </div>
  );
}
