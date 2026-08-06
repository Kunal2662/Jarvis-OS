import { useCallback, useEffect, useRef, useState } from "react";
import { describeError } from "@/services/error-reporting";
import { useBackendStatus } from "@/hooks/use-backend-status";

/**
 * One fetch, one set of honest states -- the hook every dashboard widget
 * reads its data through (M8 Phase 5 / Phase 6).
 *
 * Fifteen widgets each writing their own `useEffect` + `useState` triple
 * is fifteen chances to forget the offline case, fifteen slightly
 * different error strings, and fifteen places an out-of-order response
 * can overwrite a newer one. This is that logic once.
 *
 * **Offline is a distinct state, not an error.** The hook consults
 * `useBackendStatus()` before fetching, so a widget on a disconnected
 * backend renders "offline" rather than firing a request that is going
 * to fail and calling the failure an error. That is `ARCHITECTURE.md`'s
 * "never fake data — an explicit disconnected state" applied per widget.
 *
 * **It reconnects by itself.** When the backend comes back the effect
 * re-runs, because `isLive` is a dependency. Connection recovery is
 * therefore not a feature any widget implements — it is a consequence of
 * reading state instead of caching a verdict.
 *
 * Deliberately not TanStack Query, which *is* a dependency here: Query's
 * value is its cache, and a dashboard widget reading a live health
 * snapshot or a small collection wants the current answer rather than a
 * cached one. Where a real cache earns its keep — shared, re-fetched,
 * paginated data — Query remains the right tool and this hook is not a
 * replacement for it.
 */

export type ResourceState<T> =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; data: T }
  | { status: "empty" }
  | { status: "offline" }
  | { status: "error"; message: string };

export interface UseBackendResourceOptions {
  /** Treat a successful-but-empty result as its own state, so a widget
   *  can say "no tasks yet" rather than rendering an empty list that
   *  looks broken. */
  isEmpty?: (data: unknown) => boolean;
  /** Skip fetching entirely — for a widget whose inputs are not ready
   *  (no workspace selected yet, say). */
  enabled?: boolean;
}

export interface BackendResource<T> {
  state: ResourceState<T>;
  /** Manual refetch, for a retry button. */
  refresh: () => void;
}

function defaultIsEmpty(data: unknown): boolean {
  if (Array.isArray(data)) return data.length === 0;

  // A `Page<T>` from `apiList` is `{items, meta}` -- a *non-empty
  // object* whose `items` may well be empty. Without this branch an
  // empty collection reads as "ready" and renders an empty list where
  // the empty state belongs, and every caller has to remember to pass
  // its own `isEmpty`. Several already did; one forgot, which is how
  // this was found (M8 Phase 7). Fixing the default removes the trap
  // rather than patching the call site.
  if (data && typeof data === "object" && "items" in data && Array.isArray((data as { items: unknown[] }).items)) {
    return (data as { items: unknown[] }).items.length === 0;
  }

  if (data && typeof data === "object") return Object.keys(data).length === 0;
  return data === null || data === undefined;
}

export function useBackendResource<T>(
  fetcher: () => Promise<T>,
  deps: readonly unknown[],
  options: UseBackendResourceOptions = {},
): BackendResource<T> {
  const { isEmpty = defaultIsEmpty, enabled = true } = options;
  const { isLive, isOffline } = useBackendStatus();
  const [state, setState] = useState<ResourceState<T>>({ status: "idle" });
  const [nonce, setNonce] = useState(0);

  // Guards against an out-of-order response: a slow earlier request must
  // not overwrite a faster later one.
  const requestId = useRef(0);

  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  useEffect(() => {
    if (!enabled) {
      setState({ status: "idle" });
      return;
    }
    if (isOffline) {
      setState({ status: "offline" });
      return;
    }
    if (!isLive) {
      // Reachable but not yet authenticated — still starting up. Showing
      // "loading" is honest; showing "offline" would not be.
      setState({ status: "loading" });
      return;
    }

    const id = ++requestId.current;
    let cancelled = false;
    setState({ status: "loading" });

    fetcher()
      .then((data) => {
        if (cancelled || id !== requestId.current) return;
        setState(isEmpty(data) ? { status: "empty" } : { status: "ready", data });
      })
      .catch((error: unknown) => {
        if (cancelled || id !== requestId.current) return;
        const { title, detail } = describeError(error);
        setState({ status: "error", message: detail ? `${title} ${detail}` : title });
      });

    return () => {
      cancelled = true;
    };
    // `fetcher` is deliberately not a dependency: an inline arrow is a
    // new function every render, and depending on it would refetch in a
    // loop. The caller's `deps` are the real inputs.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isLive, isOffline, enabled, nonce, ...deps]);

  return { state, refresh };
}
