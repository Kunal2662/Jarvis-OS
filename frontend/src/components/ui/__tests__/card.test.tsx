import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { Card } from "@/components/ui/card";
import { useStartupPreferencesStore } from "@/stores/startup-preferences.store";

describe("Card", () => {
  beforeEach(() => {
    useStartupPreferencesStore.setState({ disableGlassEffects: false });
  });

  it("renders a translucent, blurred background by default (Task Group J)", () => {
    render(<Card data-testid="card">content</Card>);
    expect(screen.getByTestId("card")).toHaveClass("bg-card/85", "backdrop-blur-md");
  });

  it("falls back to a solid background when the real disableGlassEffects preference is set", () => {
    useStartupPreferencesStore.setState({ disableGlassEffects: true });
    render(<Card data-testid="card">content</Card>);
    const card = screen.getByTestId("card");
    expect(card).toHaveClass("bg-card");
    expect(card).not.toHaveClass("backdrop-blur-md");
  });

  it("still lets a caller override the background via className", () => {
    render(
      <Card data-testid="card" className="bg-destructive">
        content
      </Card>,
    );
    expect(screen.getByTestId("card")).toHaveClass("bg-destructive");
  });
});
