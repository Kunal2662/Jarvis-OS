import { useRef, useState } from "react";
import {
  Check,
  Copy,
  Download,
  LayoutGrid,
  Plus,
  RotateCcw,
  Trash2,
  Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { panelRegistry } from "@/core/panel-registry";
import { atLeast } from "@/core/user-mode";
import { reportError, reportSuccess } from "@/services/error-reporting";
import { useUserMode } from "@/stores/user-mode.store";
import {
  selectActiveWorkspace,
  useWorkspaceLayoutStore,
  WorkspaceImportError,
} from "@/stores/workspace-layout.store";

/**
 * Workspace switching and management -- the seven workspace operations
 * M8 Phase 3 requires (create, rename, delete, duplicate, reset, import,
 * export) plus the "add panel" menu.
 *
 * One toolbar rather than a settings screen: every one of these acts on
 * the layout the user is looking at, and making them travel to a
 * different screen to rearrange this one is the wrong shape.
 *
 * Export downloads a file and import reads one, both through a hidden
 * `<input type="file">` — no backend round trip, because a layout is
 * device-local state and there is no endpoint for it (the backend
 * contract is frozen, and rightly: panel geometry is not the server's
 * business).
 */
export function WorkspaceToolbar() {
  const workspaces = useWorkspaceLayoutStore((s) => s.workspaces);
  const active = useWorkspaceLayoutStore(selectActiveWorkspace);
  const setActiveWorkspace = useWorkspaceLayoutStore((s) => s.setActiveWorkspace);
  const createWorkspace = useWorkspaceLayoutStore((s) => s.createWorkspace);
  const renameWorkspace = useWorkspaceLayoutStore((s) => s.renameWorkspace);
  const deleteWorkspace = useWorkspaceLayoutStore((s) => s.deleteWorkspace);
  const duplicateWorkspace = useWorkspaceLayoutStore((s) => s.duplicateWorkspace);
  const resetWorkspace = useWorkspaceLayoutStore((s) => s.resetWorkspace);
  const exportWorkspace = useWorkspaceLayoutStore((s) => s.exportWorkspace);
  const importWorkspace = useWorkspaceLayoutStore((s) => s.importWorkspace);
  const openPanel = useWorkspaceLayoutStore((s) => s.openPanel);

  const [renaming, setRenaming] = useState(false);
  const [draftName, setDraftName] = useState(active.name);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const openPanelIds = new Set(active.panels.map((panel) => panel.panelId));
  const mode = useUserMode();
  // A personal user is never *offered* a restricted panel. The panel
  // components check again themselves -- this filter is about not
  // advertising something that would refuse to render, not about
  // security (`ARCHITECTURE.md` §22.12).
  const available = panelRegistry
    .getAll()
    .filter((panel) => atLeast(mode, panel.requiredMode ?? "personal"));

  function commitRename() {
    renameWorkspace(active.id, draftName);
    setRenaming(false);
  }

  function handleExport() {
    const json = exportWorkspace(active.id);
    const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = `${active.name.replace(/[^\w-]+/g, "-").toLowerCase()}.jarvis-workspace.json`;
    link.click();
    // Revoking immediately is safe -- the click has already handed the
    // blob to the download, and leaking object URLs is how a long
    // session ends up holding every export it ever made.
    URL.revokeObjectURL(url);
  }

  async function handleImportFile(file: File) {
    try {
      importWorkspace(await file.text());
      reportSuccess("Workspace imported");
    } catch (error) {
      // A bad file is the user's problem to fix, so it gets a toast with
      // the real reason rather than a silent no-op.
      reportError(error, { context: "Couldn't import that workspace" });
      if (!(error instanceof WorkspaceImportError)) throw error;
    }
  }

  return (
    <div className="flex shrink-0 items-center gap-1 border-border/60 border-b px-2 py-1.5">
      {renaming ? (
        <Input
          autoFocus
          value={draftName}
          onChange={(event) => setDraftName(event.target.value)}
          onBlur={commitRename}
          onKeyDown={(event) => {
            if (event.key === "Enter") commitRename();
            if (event.key === "Escape") setRenaming(false);
          }}
          aria-label="Workspace name"
          className="h-7 w-44"
        />
      ) : (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="sm" className="h-7 gap-1.5">
              <LayoutGrid className="size-3.5" aria-hidden="true" />
              {active.name}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="w-56">
            <DropdownMenuLabel>Switch workspace</DropdownMenuLabel>
            {workspaces.map((workspace) => (
              <DropdownMenuItem
                key={workspace.id}
                onSelect={() => setActiveWorkspace(workspace.id)}
              >
                {workspace.id === active.id ? (
                  <Check className="size-3.5" aria-hidden="true" />
                ) : (
                  <span className="size-3.5" aria-hidden="true" />
                )}
                {workspace.name}
              </DropdownMenuItem>
            ))}
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => createWorkspace()}>
              <Plus className="size-3.5" aria-hidden="true" />
              New workspace
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                setDraftName(active.name);
                setRenaming(true);
              }}
            >
              Rename &ldquo;{active.name}&rdquo;
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => duplicateWorkspace(active.id)}>
              <Copy className="size-3.5" aria-hidden="true" />
              Duplicate
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => resetWorkspace(active.id)}>
              <RotateCcw className="size-3.5" aria-hidden="true" />
              Reset layout
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={handleExport}>
              <Download className="size-3.5" aria-hidden="true" />
              Export…
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => fileInputRef.current?.click()}>
              <Upload className="size-3.5" aria-hidden="true" />
              Import…
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              // The last workspace cannot be deleted -- an app with no
              // workspace has nothing to render. Disabled rather than
              // hidden so the reason is visible.
              disabled={workspaces.length <= 1}
              onSelect={() => deleteWorkspace(active.id)}
            >
              <Trash2 className="size-3.5" aria-hidden="true" />
              Delete workspace
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}

      <div className="flex-1" />

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="h-7 gap-1.5">
            <Plus className="size-3.5" aria-hidden="true" />
            Panel
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-52">
          <DropdownMenuLabel>Add a panel</DropdownMenuLabel>
          {available.length === 0 ? (
            <DropdownMenuItem disabled>No panels registered</DropdownMenuItem>
          ) : (
            available.map((panel) => (
              <DropdownMenuItem
                key={panel.id}
                // Already-open panels stay listed but disabled: hiding
                // them would make the menu's contents change shape as
                // panels open, which is harder to scan than a stable
                // list with state.
                disabled={openPanelIds.has(panel.id)}
                onSelect={() => openPanel(panel.id)}
              >
                {panel.title}
              </DropdownMenuItem>
            ))
          )}
        </DropdownMenuContent>
      </DropdownMenu>

      <input
        ref={fileInputRef}
        type="file"
        accept="application/json,.json"
        className="hidden"
        aria-hidden="true"
        onChange={(event) => {
          const file = event.target.files?.[0];
          // Reset first so re-picking the same file fires `change` again.
          event.target.value = "";
          if (file) void handleImportFile(file);
        }}
      />
    </div>
  );
}
