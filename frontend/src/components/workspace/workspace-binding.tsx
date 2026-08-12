import { Check, Link2, Link2Off } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useBackendResource } from "@/hooks/use-backend-resource";
import { workspacesApi } from "@/services/api/endpoints";
import {
  selectActiveWorkspace,
  useWorkspaceLayoutStore,
} from "@/stores/workspace-layout.store";

/**
 * Binds a layout to a real backend workspace -- M8 Phase 7.
 *
 * **This closes a dead end, it does not add a feature.** M8 Phase 5
 * shipped four dashboard widgets (Recent Tasks, Projects, Pinned Notes,
 * Recent Files, Upcoming) whose empty state reads *"Bind this workspace
 * to a JARVIS workspace to see its tasks."* — and the production-
 * readiness pass found there was no control anywhere in the app that
 * could do that. `bindBackendWorkspace` existed in the store with only
 * tests calling it, and `workspacesApi` had no caller at all. Five
 * widgets instructed the user to perform an action the UI did not
 * offer.
 *
 * Every piece was already built: the store action (Phase 3), the typed
 * endpoint (Phase 2), and the widgets that read the binding (Phase 5).
 * This is the control that connects them.
 *
 * The backend workspace list is fetched, never cached into the layout:
 * `WorkspaceLayout.backendWorkspaceId` holds an **id and nothing else**,
 * so a workspace renamed on the backend shows its new name here without
 * anything going stale. That constraint is asserted by
 * `workspace-layout.store.test.ts`.
 */
export function WorkspaceBinding() {
  const layout = useWorkspaceLayoutStore(selectActiveWorkspace);
  const bind = useWorkspaceLayoutStore((s) => s.bindBackendWorkspace);
  const { state, refresh } = useBackendResource(() => workspacesApi.list({ limit: 50 }), []);

  const bound =
    state.status === "ready"
      ? state.data.items.find((workspace) => workspace.id === layout.backendWorkspaceId)
      : undefined;

  // Bound to something the backend no longer has (deleted elsewhere, or
  // a layout imported from another install). Say so rather than
  // rendering a blank name.
  const boundButMissing = layout.backendWorkspaceId !== null && state.status === "ready" && !bound;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 gap-1.5 text-xs"
          aria-label={
            layout.backendWorkspaceId
              ? `Data source: ${bound?.name ?? "unavailable"}. Change or unlink.`
              : "Link this workspace to a JARVIS workspace"
          }
        >
          {layout.backendWorkspaceId ? (
            <Link2 className="size-3.5" aria-hidden="true" />
          ) : (
            <Link2Off className="size-3.5 text-muted-foreground" aria-hidden="true" />
          )}
          <span className="max-w-32 truncate">
            {boundButMissing ? "Unavailable" : (bound?.name ?? "No data source")}
          </span>
        </Button>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="start" className="w-60">
        <DropdownMenuLabel>Data source</DropdownMenuLabel>

        {state.status === "offline" && (
          <DropdownMenuItem disabled>Backend unreachable</DropdownMenuItem>
        )}
        {state.status === "loading" && <DropdownMenuItem disabled>Loading…</DropdownMenuItem>}
        {state.status === "error" && (
          <DropdownMenuItem onSelect={refresh}>Couldn&apos;t load — retry</DropdownMenuItem>
        )}
        {state.status === "empty" && (
          <DropdownMenuItem disabled>No JARVIS workspaces yet</DropdownMenuItem>
        )}

        {state.status === "ready" &&
          state.data.items.map((workspace) => (
            <DropdownMenuItem
              key={workspace.id}
              onSelect={() => bind(layout.id, workspace.id)}
            >
              {workspace.id === layout.backendWorkspaceId ? (
                <Check className="size-3.5" aria-hidden="true" />
              ) : (
                <span className="size-3.5" aria-hidden="true" />
              )}
              <span className="truncate">{workspace.name}</span>
            </DropdownMenuItem>
          ))}

        {layout.backendWorkspaceId !== null && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => bind(layout.id, null)}>
              <Link2Off className="size-3.5" aria-hidden="true" />
              Unlink
            </DropdownMenuItem>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
