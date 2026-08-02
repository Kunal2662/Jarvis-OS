import { useEffect, useState } from "react";

/**
 * The one reusable viewport-breakpoint hook for the app -- built for
 * Sidebar's responsive-collapse requirement (Phase 3, Task Group C),
 * the first thing that needed JS-level viewport detection (Tailwind's
 * own responsive classes handle pure-CSS cases; toggling a stored
 * boolean like `isCollapsed`'s effective value needs this). Every
 * future responsive need should reuse this rather than rolling its own
 * `matchMedia` listener.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const mediaQueryList = window.matchMedia(query);
    const listener = () => setMatches(mediaQueryList.matches);
    listener();
    // `MediaQueryList`'s own "change" event is the primary signal, but
    // isn't dispatched reliably for every kind of viewport resize (e.g.
    // programmatic/emulated resizes, confirmed missing one in browser
    // verification) -- the plain window "resize" event is listened to
    // as a fallback, re-checking the same query, so the effective state
    // never goes stale regardless of how the resize happened.
    mediaQueryList.addEventListener("change", listener);
    window.addEventListener("resize", listener);
    return () => {
      mediaQueryList.removeEventListener("change", listener);
      window.removeEventListener("resize", listener);
    };
  }, [query]);

  return matches;
}
