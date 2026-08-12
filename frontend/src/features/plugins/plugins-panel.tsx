import { useState } from "react";
import { Puzzle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ResourceView } from "@/components/common/resource-view";
import { useBackendResource } from "@/hooks/use-backend-resource";
import { pluginsApi, type PluginSummary } from "@/services/api/endpoints";
import { reportError, reportSuccess } from "@/services/error-reporting";
import { syncPluginPermissions } from "@/services/permissions-sync";

/**
 * The Plugins panel -- M8 Phase 5, on M9 Task Group D's real routes.
 *
 * Lists what is installed, enables and disables it, and pulls each
 * plugin's permission state into the existing
 * `core/permission-framework.ts` through
 * `services/permissions-sync.ts` — the write-through path M8 Phase 2
 * built, not a second permission mechanism.
 *
 * Install and uninstall are deliberately absent. Both take a
 * `source_path` on the *backend's own filesystem*
 * (`POST /plugins/install`), which a browser cannot supply and a Tauri
 * file dialog would need real plumbing to; offering a button that cannot
 * work is worse than not offering it. Enabling and disabling are the
 * operations that make sense from here, and they are complete.
 */
export function PluginsPanel() {
  const [busyId, setBusyId] = useState<string | null>(null);
  const { state, refresh } = useBackendResource(() => pluginsApi.list(), []);

  async function toggle(plugin: PluginSummary) {
    setBusyId(plugin.plugin_id);
    try {
      if (plugin.enabled) {
        await pluginsApi.disable(plugin.plugin_id);
        reportSuccess(`${plugin.name} disabled`);
      } else {
        await pluginsApi.enable(plugin.plugin_id);
        reportSuccess(`${plugin.name} enabled`);
      }
      // Permissions can change with enablement, so the local framework is
      // re-synced from the backend rather than assumed unchanged.
      await syncPluginPermissions(plugin.plugin_id).catch(() => undefined);
      refresh();
    } catch (error) {
      reportError(error, { context: `Couldn't update ${plugin.name}` });
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="h-full overflow-auto">
      <ResourceView
        state={state}
        label="Plugins"
        onRetry={refresh}
        emptyMessage="No plugins installed."
      >
        {(plugins) => (
          <ul className="divide-y divide-border/60">
            {plugins.map((plugin) => (
              <li key={plugin.plugin_id} className="flex items-center gap-3 px-3 py-2">
                <Puzzle className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium text-secondary">{plugin.name || plugin.plugin_id}</p>
                  <p className="truncate text-muted-foreground text-xs">
                    v{plugin.version} · {plugin.state}
                    {plugin.permissions?.length > 0 && ` · ${plugin.permissions.length} permission(s)`}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  className="h-7 shrink-0 text-xs"
                  disabled={busyId === plugin.plugin_id}
                  onClick={() => void toggle(plugin)}
                >
                  {busyId === plugin.plugin_id ? "Working…" : plugin.enabled ? "Disable" : "Enable"}
                </Button>
              </li>
            ))}
          </ul>
        )}
      </ResourceView>
    </div>
  );
}
