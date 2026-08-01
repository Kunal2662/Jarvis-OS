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
    mediaQueryList.addEventListener("change", listener);
    return () => mediaQueryList.removeEventListener("change", listener);
  }, [query]);

  return matches;
}
