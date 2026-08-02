import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

afterEach(() => {
  cleanup();
});

/**
 * jsdom doesn't implement `window.matchMedia` -- needed by
 * `lib/motion.ts`'s `prefersReducedMotion()`, Motion's own
 * `reducedMotion="user"` config, and any future `prefers-color-scheme`
 * check. A minimal, always-`false` stub is enough for component tests
 * that don't specifically exercise the media-query branch.
 */
if (typeof window !== "undefined" && !window.matchMedia) {
  window.matchMedia = (query: string): MediaQueryList =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList;
}

/**
 * jsdom doesn't implement `ResizeObserver` either -- needed by Radix's
 * Tooltip (`@radix-ui/react-use-size`, exercised by Sidebar's collapsed-
 * mode tooltip, Phase 3 Task Group C). A no-op stub is enough for
 * component tests; nothing here asserts on actually-observed sizes.
 */
if (typeof window !== "undefined" && !window.ResizeObserver) {
  window.ResizeObserver = class ResizeObserver {
    observe(): void {}
    unobserve(): void {}
    disconnect(): void {}
  };
}
