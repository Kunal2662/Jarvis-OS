import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { useGlassEffectsEnabled } from "@/hooks/use-glass-effects";
import { useStartupPreferencesStore } from "@/stores/startup-preferences.store";

function Harness() {
  const enabled = useGlassEffectsEnabled();
  return <span>{enabled ? "enabled" : "disabled"}</span>;
}

describe("useGlassEffectsEnabled", () => {
  beforeEach(() => {
    useStartupPreferencesStore.setState({ disableGlassEffects: false });
  });

  it("is enabled by default, since disableGlassEffects defaults to false", () => {
    render(<Harness />);
    expect(screen.getByText("enabled")).toBeInTheDocument();
  });

  it("reflects the real disableGlassEffects preference when set", () => {
    useStartupPreferencesStore.setState({ disableGlassEffects: true });
    render(<Harness />);
    expect(screen.getByText("disabled")).toBeInTheDocument();
  });
});
