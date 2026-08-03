import { render, screen } from "@testing-library/react";
import { useReducedMotionConfig } from "motion/react";
import { beforeEach, describe, expect, it } from "vitest";
import { AccessibleMotionConfig } from "@/providers/app-providers";
import { useAccessibilityPreferencesStore } from "@/stores/accessibility-preferences.store";

function ReducedMotionProbe() {
  // `useReducedMotionConfig()`, not the public `useReducedMotion()` --
  // the latter only ever reads the OS-level media query and completely
  // ignores `MotionConfig`'s own `reducedMotion` prop; the former is
  // the hook Motion itself uses internally to combine the two, which is
  // exactly what every real call site in this app (`startup-gate.tsx`,
  // `voice-waveform-renderer.tsx`) now uses instead of the public hook.
  const reduced = useReducedMotionConfig();
  return <span>{reduced ? "reduced" : "normal"}</span>;
}

/**
 * Only the real, non-obvious logic in `app-providers.tsx` -- mapping
 * the persisted `reducedMotion` preference onto Motion's own
 * `reducedMotion` mode -- is unit-tested here. The rest of the file is
 * pure composition, already exercised end-to-end by every other test
 * that renders through `AppProviders`.
 */
describe("AccessibleMotionConfig", () => {
  beforeEach(() => {
    useAccessibilityPreferencesStore.setState({ reducedMotion: false });
  });

  it("leaves Motion in OS-controlled 'user' mode by default", () => {
    render(
      <AccessibleMotionConfig>
        <ReducedMotionProbe />
      </AccessibleMotionConfig>,
    );
    // jsdom's matchMedia mock reports no OS-level preference either way.
    expect(screen.getByText("normal")).toBeInTheDocument();
  });

  it("forces every useReducedMotion() consumer to true when the real preference is set", () => {
    useAccessibilityPreferencesStore.setState({ reducedMotion: true });
    render(
      <AccessibleMotionConfig>
        <ReducedMotionProbe />
      </AccessibleMotionConfig>,
    );
    expect(screen.getByText("reduced")).toBeInTheDocument();
  });
});
