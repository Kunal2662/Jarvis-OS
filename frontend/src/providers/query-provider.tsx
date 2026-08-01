import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/**
 * Every backend-sourced value flows through this client (ARCHITECTURE.md
 * section 5/13) -- no component calls `fetch` directly. Defaults are
 * conservative: a failed request doesn't hammer a backend that's still
 * starting up (see the Runtime's `runtime.ready` state, section 3), and
 * nothing refetches on window focus by default since a desktop app's
 * "focus" semantics differ from a browser tab's.
 */
export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 2,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 0,
    },
  },
});

export function QueryProvider({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}
