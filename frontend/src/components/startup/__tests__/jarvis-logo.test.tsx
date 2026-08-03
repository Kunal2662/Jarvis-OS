import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JarvisLogo } from "@/components/startup/jarvis-logo";

describe("JarvisLogo", () => {
  it("renders for every phase without throwing", () => {
    for (const phase of ["hidden", "assembling", "pulsing"] as const) {
      expect(() => render(<JarvisLogo phase={phase} />)).not.toThrow();
    }
  });

  it("renders only the center dot while assembling", () => {
    const { container } = render(<JarvisLogo phase="assembling" />);
    expect(container.querySelectorAll("circle")).toHaveLength(1);
  });

  it("renders an additional pulse-burst ring while pulsing", () => {
    const { container } = render(<JarvisLogo phase="pulsing" />);
    expect(container.querySelectorAll("circle")).toHaveLength(2);
  });

  it("is purely decorative -- aria-hidden, no accessible text", () => {
    const { container } = render(<JarvisLogo phase="assembling" />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });
});
