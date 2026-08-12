import { CircleCheck, CircleX, Loader2 } from "lucide-react";
import { useBackendStatus } from "@/hooks/use-backend-status";
import { useCanReveal } from "@/stores/user-mode.store";
import {
  formatBytes,
  formatUptime,
  selectAiWorkspaceStatus,
  selectFilesStatus,
  selectOverallStatus,
  selectSearchSources,
  useHealthStore,
} from "@/stores/health.store";

/**
 * Diagnostics -- M8 Phase 5. Available to every audience, but it shows a
 * personal user a different, smaller truth than it shows a developer.
 *
 * That split is `ARCHITECTURE.md` §22.12 applied to a panel rather than
 * to a whole page: "is JARVIS working?" is a question a personal user is
 * entitled to ask, and answering it does not require naming the services
 * that answer it. So connection state, overall health, uptime and memory
 * are unrestricted; **service names and search-source names are not**,
 * because they name backend services, and they appear only for
 * Developer Mode and above.
 *
 * The alternative — a Diagnostics panel gated entirely behind Developer
 * Mode — would leave a personal user with no way to tell "JARVIS is
 * broken" from "JARVIS is thinking", which is precisely the confusion
 * §22.12's progress vocabulary exists to prevent.
 */
export function DiagnosticsPanel() {
  const { state: backendState, detail, socket, isOffline } = useBackendStatus();
  const snapshot = useHealthStore((s) => s.snapshot);
  const receivedAt = useHealthStore((s) => s.receivedAt);
  const overall = useHealthStore(selectOverallStatus);
  const aiWorkspace = useHealthStore(selectAiWorkspaceStatus);
  const files = useHealthStore(selectFilesStatus);
  const sources = useHealthStore(selectSearchSources);
  const maySeeServices = useCanReveal("backend_services");

  return (
    <div className="h-full overflow-auto p-3 text-secondary">
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Row label="Connection" value={isOffline ? "Offline" : backendState} state={isOffline ? "bad" : backendState === "ready" ? "good" : "busy"} />
        <Row label="Live updates" value={socket} state={socket === "connected" ? "good" : "busy"} />
        <Row label="Backend health" value={overall} state={overall === "healthy" ? "good" : overall === "degraded" ? "bad" : "busy"} />
        <Row label="Uptime" value={formatUptime(snapshot?.uptime_seconds)} />
        <Row label="Memory" value={formatBytes(snapshot?.memory_rss_bytes)} />
        <Row
          label="CPU"
          value={snapshot?.cpu_percent === undefined ? "—" : `${snapshot.cpu_percent.toFixed(0)}%`}
        />
        <Row label="AI workspace" value={aiWorkspace} state={aiWorkspace === "healthy" ? "good" : aiWorkspace === "degraded" ? "bad" : "busy"} />
        <Row label="File storage" value={files} state={files === "healthy" ? "good" : files === "degraded" ? "bad" : "busy"} />
      </dl>

      {detail && <p className="pt-3 text-muted-foreground text-xs">{detail}</p>}

      {maySeeServices && snapshot && (
        <div className="mt-4 border-border/60 border-t pt-3">
          <p className="pb-1 font-medium text-muted-foreground text-xs uppercase tracking-wide">
            Services &amp; sources
          </p>
          <p className="text-muted-foreground text-xs">
            Running: {snapshot.active_services?.join(", ") || "—"}
          </p>
          {snapshot.failed_services && snapshot.failed_services.length > 0 && (
            <p className="text-destructive text-xs">Failed: {snapshot.failed_services.join(", ")}</p>
          )}
          <p className="text-muted-foreground text-xs">Search sources: {sources.join(", ") || "—"}</p>
        </div>
      )}

      {receivedAt && (
        <p className="pt-3 text-muted-foreground text-xs">
          Health last reported {new Date(receivedAt).toLocaleTimeString()}.
        </p>
      )}
      {!snapshot && !isOffline && (
        <p className="pt-3 text-muted-foreground text-xs">
          Waiting for the first health report from the backend.
        </p>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  state,
}: {
  label: string;
  value: string;
  state?: "good" | "bad" | "busy";
}) {
  const Icon = state === "good" ? CircleCheck : state === "bad" ? CircleX : Loader2;
  const colour =
    state === "good" ? "text-emerald-500" : state === "bad" ? "text-destructive" : "text-muted-foreground";

  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="flex items-center gap-1.5 font-medium">
        {state && <Icon className={`size-3.5 shrink-0 ${colour}`} aria-hidden="true" />}
        <span className="truncate">{value}</span>
      </dd>
    </div>
  );
}
