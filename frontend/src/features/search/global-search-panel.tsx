import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FileQuestion, Search, WifiOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { LoadingState } from "@/components/common/loading-spinner";
import { VirtualList } from "@/components/common/virtual-list";
import { searchApi, type SearchResult } from "@/services/api/endpoints";
import { describeError } from "@/services/error-reporting";
import { useBackendStatus } from "@/hooks/use-backend-status";

/**
 * Global Search -- M8 Phase 3.
 *
 * Backed by the **real** `POST /api/v1/search`, the M10A universal search
 * endpoint that fans out across the 13 registered search sources
 * (workspaces, projects, notes, tasks, reminders, files, knowledge,
 * memory, integrations…). This component adds no index and no client-side
 * corpus of its own — searching is a backend capability that already
 * exists, and a second one here would return different answers to the
 * same question.
 *
 * **Distinct from the Command Palette.** `Ctrl+K` navigates *this app* —
 * modules and registered commands, resolved locally and instantly. This
 * panel searches the user's *content*, over the network. Merging them
 * would put a network round-trip in front of "go to Settings".
 *
 * Offline is a first-class state, not an error: `useBackendStatus()` is
 * consulted before a query is attempted, so an unreachable backend says
 * so instead of firing a request that is going to fail.
 */

const DEBOUNCE_MS = 250;
const MIN_QUERY_LENGTH = 2;

type SearchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "ready"; results: SearchResult[] }
  | { status: "error"; message: string };

function ResultRow({ result }: { result: SearchResult }) {
  return (
    <li className="border-border/60 border-b px-3 py-2.5">
      <div className="flex items-baseline justify-between gap-2">
        <p className="truncate font-medium text-secondary">{result.title || "Untitled"}</p>
        <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-muted-foreground text-xs">
          {result.source}
        </span>
      </div>
      {result.content && (
        <p className="line-clamp-2 text-muted-foreground text-xs">{result.content}</p>
      )}
    </li>
  );
}

export function GlobalSearchPanel() {
  const [query, setQuery] = useState("");
  const [state, setState] = useState<SearchState>({ status: "idle" });
  const { isLive, isOffline } = useBackendStatus();

  // Tracks the newest request so a slow earlier response cannot
  // overwrite a faster later one -- the classic out-of-order-results bug
  // in any search-as-you-type box.
  const requestId = useRef(0);

  const runSearch = useCallback(
    async (text: string) => {
      const id = ++requestId.current;
      setState({ status: "loading" });
      try {
        const results = await searchApi.query(text, { top_k: 30 });
        if (id !== requestId.current) return;
        setState({ status: "ready", results });
      } catch (error) {
        if (id !== requestId.current) return;
        const { title, detail } = describeError(error);
        setState({ status: "error", message: detail ? `${title} ${detail}` : title });
      }
    },
    [],
  );

  useEffect(() => {
    const trimmed = query.trim();
    if (trimmed.length < MIN_QUERY_LENGTH) {
      requestId.current += 1; // cancel anything in flight
      setState({ status: "idle" });
      return;
    }
    if (!isLive) return;

    const timer = setTimeout(() => void runSearch(trimmed), DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [query, isLive, runSearch]);

  const body = useMemo(() => {
    if (isOffline) {
      return (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          <WifiOff className="size-icon-lg text-muted-foreground" aria-hidden="true" />
          <p className="font-medium text-secondary">Search is offline</p>
          <p className="max-w-xs text-muted-foreground text-xs">
            Searching needs the JARVIS backend, which isn&apos;t reachable right now.
          </p>
        </div>
      );
    }
    if (state.status === "idle") {
      return (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          <Search className="size-icon-lg text-muted-foreground" aria-hidden="true" />
          <p className="max-w-xs text-muted-foreground text-xs">
            Search across your workspaces, notes, tasks, files and memory.
          </p>
        </div>
      );
    }
    if (state.status === "loading") {
      return <LoadingState label="Searching" />;
    }
    if (state.status === "error") {
      return (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          <FileQuestion className="size-icon-lg text-muted-foreground" aria-hidden="true" />
          <p className="font-medium text-secondary">Search failed</p>
          <p className="max-w-xs text-muted-foreground text-xs">{state.message}</p>
        </div>
      );
    }
    if (state.results.length === 0) {
      return (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
          <FileQuestion className="size-icon-lg text-muted-foreground" aria-hidden="true" />
          <p className="font-medium text-secondary">No matches</p>
          <p className="max-w-xs text-muted-foreground text-xs">
            Nothing matched &ldquo;{query.trim()}&rdquo;.
          </p>
        </div>
      );
    }
    return (
      <VirtualList
        items={state.results}
        estimatedItemHeight={64}
        className="min-h-0 flex-1"
        renderItem={(result) => <ResultRow key={`${result.source}:${result.id}`} result={result} />}
      />
    );
  }, [state, isOffline, query]);

  return (
    <div className="flex h-full flex-col">
      <div className="border-border/60 border-b p-2">
        <Input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search everything…"
          aria-label="Search across JARVIS"
          className="h-8"
        />
      </div>
      {body}
    </div>
  );
}
