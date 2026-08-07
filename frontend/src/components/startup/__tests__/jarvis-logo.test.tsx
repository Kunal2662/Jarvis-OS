/// <reference types="node" />
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JarvisLogo } from "@/components/startup/jarvis-logo";

/**
 * `JarvisLogo` -- rebuilt on the approved master logo's geometry (M22
 * Task Group E), replacing the earlier hexagon placeholder. These
 * assertions cover structure and props, which is what a synchronous
 * DOM test can verify; the animation timing itself needs a real
 * browser's compositor to observe (see MILESTONE_REPORT.md's Task
 * Group E entry for why that could not be confirmed live in this
 * environment, and what was checked instead).
 */

describe("JarvisLogo", () => {
  it("renders for every phase without throwing", () => {
    for (const phase of ["hidden", "assembling", "pulsing"] as const) {
      expect(() => render(<JarvisLogo phase={phase} />)).not.toThrow();
    }
  });

  it("renders the center blade and both side blades in every phase", () => {
    // Always mounted; only the *animate target* differs by phase, so
    // "hidden" still renders the same five paths, just faded out.
    for (const phase of ["hidden", "assembling", "pulsing"] as const) {
      const { container } = render(<JarvisLogo phase={phase} />);
      expect(container.querySelectorAll("path")).toHaveLength(5);
    }
  });

  it("mirrors the left and right side blades around the vertical center", () => {
    const { container } = render(<JarvisLogo phase="assembling" />);
    const paths = [...container.querySelectorAll("path")].map((p) => p.getAttribute("d") ?? "");

    // Center blade: symmetric around x=64, the viewBox's own center.
    expect(paths.some((d) => d.startsWith("M64,10"))).toBe(true);
    // Left and right outer/inner side-blade pairs.
    expect(paths.some((d) => d.startsWith("M49,18"))).toBe(true);
    expect(paths.some((d) => d.startsWith("M79,18"))).toBe(true);
    expect(paths.some((d) => d.startsWith("M51,25"))).toBe(true);
    expect(paths.some((d) => d.startsWith("M77,25"))).toBe(true);
  });

  it("renders only the glow circle while assembling", () => {
    const { container } = render(<JarvisLogo phase="assembling" />);
    expect(container.querySelectorAll("circle")).toHaveLength(1);
  });

  it("adds the pulse-burst ring and breathing dot while pulsing", () => {
    const { container } = render(<JarvisLogo phase="pulsing" />);
    // Glow + pulse burst + breathing dot.
    expect(container.querySelectorAll("circle")).toHaveLength(3);
  });

  it("is purely decorative -- aria-hidden, no accessible text", () => {
    const { container } = render(<JarvisLogo phase="assembling" />);
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("never animates a layout-triggering property", () => {
    // Grep-level guard against a regression this file's own docstring
    // promises against: only opacity/transform/pathLength should ever
    // appear as an animated key, never width/height/top/left. Reads the
    // source as text -- same discipline as `host-bridge-contract.test.ts`
    // -- resolved from `process.cwd()` (this vitest config's root is
    // `frontend/`) rather than `import.meta.url`, which is not a file
    // URL under this config.
    const source = readFileSync(
      resolve(process.cwd(), "src/components/startup/jarvis-logo.tsx"),
      "utf8",
    );
    for (const forbidden of ["width:", "height:", "top:", "left:"]) {
      expect(source, `found layout-triggering "${forbidden}" in an animated prop`).not.toContain(forbidden);
    }
  });
});
