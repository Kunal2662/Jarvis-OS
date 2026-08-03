import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

interface PreferenceToggleProps {
  label: string;
  description: string;
  checked: boolean;
  onToggle: () => void;
}

function PreferenceToggle({ label, description, checked, onToggle }: PreferenceToggleProps) {
  return (
    <div className="flex items-center justify-between gap-4 py-2">
      <div>
        <p className="font-medium text-secondary">{label}</p>
        <p className="text-caption text-muted-foreground">{description}</p>
      </div>
      <Button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        variant={checked ? "default" : "outline"}
        size="sm"
        onClick={onToggle}
      >
        {checked ? "On" : "Off"}
      </Button>
    </div>
  );
}

/**
 * The Settings module's real route element -- replaces `routes/
 * placeholder-route.tsx`'s generic screen for `settings`, but only for
 * the one section that's real today: Accessibility (Task Group K). The
 * three toggles below read and write the exact same, real, persisted
 * `accessibility-preferences.store.ts` every other real consumer does
 * (`MotionConfig` via `AccessibleMotionConfig`, `StartupGate`, every
 * glass surface Task Group J shipped) -- this page is a second UI over
 * the same source of truth, not a separate one, and Developer Mode's
 * Startup Preview panel keeps working unchanged as a QA convenience.
 *
 * The other sections `IMPLEMENTATION_ROADMAP.md` Phase 5's Dynamic
 * Settings lists (General, Appearance, Voice, AI Models, ...) have no
 * real backing settings yet, so -- per this project's "no fake data"
 * rule applied to entire UI sections, not just widget content -- they
 * simply aren't rendered here at all, rather than shown as empty or
 * "coming soon" stubs. This file grows a new section only once that
 * section has something real to show.
 */
export function SettingsPage() {
  const skipStartupAnimation = useAccessibilityPreferencesStore((s) => s.skipStartupAnimation);
  const setSkipStartupAnimation = useAccessibilityPreferencesStore((s) => s.setSkipStartupAnimation);
  const reducedMotion = useAccessibilityPreferencesStore((s) => s.reducedMotion);
  const setReducedMotion = useAccessibilityPreferencesStore((s) => s.setReducedMotion);
  const disableGlassEffects = useAccessibilityPreferencesStore((s) => s.disableGlassEffects);
  const setDisableGlassEffects = useAccessibilityPreferencesStore((s) => s.setDisableGlassEffects);

  return (
    <div className="flex flex-col gap-4">
      {/* No page title here -- `components/layout/header.tsx` already
          renders the active module's displayName ("Settings") as the
          page's one <h1>, same convention `DashboardGrid` follows. */}
      <Card>
        <CardHeader>
          <CardTitle>Accessibility</CardTitle>
          <CardDescription>
            Real, persisted preferences -- changes here take effect immediately and survive restarts.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col divide-y divide-border">
          <PreferenceToggle
            label="Skip startup animation"
            description="Launch straight into the dashboard instead of the cinematic startup sequence."
            checked={skipStartupAnimation}
            onToggle={() => setSkipStartupAnimation(!skipStartupAnimation)}
          />
          <PreferenceToggle
            label="Reduced motion"
            description="Turn animation down throughout JARVIS, even if your system setting doesn't."
            checked={reducedMotion}
            onToggle={() => setReducedMotion(!reducedMotion)}
          />
          <PreferenceToggle
            label="Disable glass effects"
            description="Replace translucent, blurred surfaces (Sidebar, Cards, Command Palette) with solid backgrounds."
            checked={disableGlassEffects}
            onToggle={() => setDisableGlassEffects(!disableGlassEffects)}
          />
        </CardContent>
      </Card>
    </div>
  );
}
