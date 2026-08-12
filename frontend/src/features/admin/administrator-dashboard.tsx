import { Lock, ShieldAlert } from "lucide-react";
import { ResourceView } from "@/components/common/resource-view";
import { VirtualList } from "@/components/common/virtual-list";
import { useBackendResource } from "@/hooks/use-backend-resource";
import { auditApi, integrationsApi, mcpApi, settingsApi } from "@/services/api/endpoints";
import { useHealthStore, formatUptime, selectOverallStatus } from "@/stores/health.store";
import { useHasMode } from "@/stores/user-mode.store";

/**
 * The Administrator Dashboard -- M8 Phase 5. **Administrator only.**
 *
 * ### Read this before adding to it
 *
 * The phase brief lists thirteen panels. **Six have a real API in the
 * frozen backend and are built. Seven do not exist and are not faked.**
 *
 * | Panel | Status |
 * |---|---|
 * | API usage | ✅ `/integrations/gateway/stats` — real call/failure counters |
 * | AI health | ✅ the `health.updated` snapshot |
 * | Provider health | ✅ `/mcp/providers` + `/mcp/providers/{id}/health` |
 * | Voice providers | ✅ `/settings` (the `tts`/`stt` sections), read-only |
 * | Audit logs | ✅ `/permissions/audit-log` — permission decisions only |
 * | Secrets status | ✅ `/settings`, server-redacted — *configured or not*, never values |
 * | Users | ❌ no user table, no roles, no route |
 * | Daily budget | ❌ |
 * | Monthly budget | ❌ |
 * | Provider priority | ❌ |
 * | Calibration status | ❌ |
 * | Analytics | ❌ |
 * | Synchronization | ❌ |
 *
 * Every ❌ belongs to `ARCHITECTURE.md` §22 — the AI/API Calibration
 * Engine (§22.2), the Cost Optimizer (§22.3), the account model
 * (§22.11) and the Oracle Cloud sync tier (§22.5). All of it is
 * **approved and not built**, and the backend is frozen, so building a
 * budget gauge here would mean inventing a number. `PendingCapabilities`
 * below names them on screen instead, which is the honest answer and
 * also the useful one: an administrator can see what this dashboard will
 * gain and why it has not yet.
 *
 * "Audit Logs" deserves its own note: the frozen backend keeps exactly
 * one audit trail — the plugin Permission Model's decision log. It is
 * not a general-purpose audit store, and this panel does not imply one.
 */
export function AdministratorDashboard() {
  const allowed = useHasMode("administrator");
  if (!allowed) return <Restricted />;
  return <AdministratorDashboardContent />;
}

function Restricted() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
      <Lock className="size-icon-lg text-muted-foreground" aria-hidden="true" />
      <p className="font-medium text-secondary">Administrator access required</p>
      <p className="max-w-sm text-muted-foreground text-xs">
        This view manages providers, budgets and audit history for a JARVIS installation.
      </p>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="flex min-h-0 flex-col gap-1 rounded-lg border border-border/60 bg-card p-2">
      <h3 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">{title}</h3>
      {children}
    </section>
  );
}

function AdministratorDashboardContent() {
  return (
    <div className="grid h-full grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-2">
      <AiHealthPanel />
      <ApiUsagePanel />
      <ProviderHealthPanel />
      <VoiceProvidersPanel />
      <SecretsStatusPanel />
      <AuditLogPanel />
      <PendingCapabilities />
    </div>
  );
}

function AiHealthPanel() {
  const snapshot = useHealthStore((s) => s.snapshot);
  const status = useHealthStore(selectOverallStatus);
  const receivedAt = useHealthStore((s) => s.receivedAt);

  return (
    <Section title="AI health">
      {!snapshot ? (
        <p className="p-3 text-center text-muted-foreground text-xs">
          Waiting for the backend health poll.
        </p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-2 py-1">
            <Field label="Status" value={status} />
            <Field label="Uptime" value={formatUptime(snapshot.uptime_seconds)} />
            <Field label="Services running" value={String(snapshot.active_services?.length ?? 0)} />
            <Field label="Services failed" value={String(snapshot.failed_services?.length ?? 0)} />
            <Field label="Restarts" value={String(snapshot.restart_count ?? 0)} />
            <Field
              label="Search sources"
              value={String(snapshot.workspace_platform?.search_sources?.length ?? 0)}
            />
          </dl>
          {receivedAt && (
            <p className="text-muted-foreground text-xs">
              Last reported {new Date(receivedAt).toLocaleTimeString()}
            </p>
          )}
        </>
      )}
    </Section>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <dt className="text-muted-foreground text-xs">{label}</dt>
      <dd className="font-semibold tabular-nums">{value}</dd>
    </div>
  );
}

/**
 * Real usage counters, explicitly *not* a budget.
 *
 * The gateway records calls, failures and cache hits. It records no
 * cost, because nothing in the frozen backend prices a call — pricing is
 * the Cost Optimizer (§22.3), which is not built. Showing a currency
 * figure derived from a call count would be a fabrication.
 */
function ApiUsagePanel() {
  const { state, refresh } = useBackendResource(() => integrationsApi.gatewayStats(), []);

  return (
    <Section title="API usage">
      <ResourceView state={state} label="API usage" skeleton="stats" onRetry={refresh}>
        {(stats) => (
          <>
            <dl className="grid grid-cols-2 gap-2 py-1">
              {Object.entries(stats).map(([key, value]) => (
                <Field key={key} label={key.replace(/_/g, " ")} value={String(value)} />
              ))}
            </dl>
            <p className="text-muted-foreground text-xs">
              Call counters from the audited egress gateway. Cost and budget tracking arrive with
              the AI Cost Optimizer.
            </p>
          </>
        )}
      </ResourceView>
    </Section>
  );
}

function ProviderHealthPanel() {
  const { state, refresh } = useBackendResource(() => mcpApi.providers(), []);

  return (
    <Section title="Provider health">
      <ResourceView
        state={state}
        label="Providers"
        onRetry={refresh}
        emptyMessage="No providers registered."
      >
        {(providers) => (
          <ul className="text-secondary">
            {providers.map((provider) => (
              <li key={provider.provider_id} className="flex items-center gap-2 py-0.5">
                <span className="min-w-0 flex-1 truncate">{provider.name || provider.provider_id}</span>
                <span className="shrink-0 text-muted-foreground text-xs">{provider.state}</span>
              </li>
            ))}
          </ul>
        )}
      </ResourceView>
    </Section>
  );
}

/**
 * Which voice backends are configured, read from the real settings tree.
 *
 * Read-only: `GET /api/v1/settings` is the whole surface, because writing
 * a setting means writing `.env` and that route deliberately does not
 * exist (M8 Phase 2 declined to add it — it is a privilege-escalation
 * surface belonging with M14). §22.6's "administrators manage providers"
 * therefore means *inspect* today and *manage* once a write path exists.
 */
function VoiceProvidersPanel() {
  const { state, refresh } = useBackendResource(() => settingsApi.all(), []);

  return (
    <Section title="Voice providers">
      <ResourceView state={state} label="Voice settings" onRetry={refresh}>
        {(tree) => {
          const rows: Array<[string, unknown]> = [];
          for (const section of ["stt", "tts", "piper", "kokoro", "edge_tts"]) {
            const value = (tree as Record<string, unknown>)[section];
            if (value && typeof value === "object") {
              const enabled = (value as Record<string, unknown>).enabled;
              const backend =
                (value as Record<string, unknown>).backend ?? (value as Record<string, unknown>).voice;
              rows.push([section, { enabled, backend }]);
            }
          }
          if (rows.length === 0) {
            return <p className="p-3 text-center text-muted-foreground text-xs">No voice settings.</p>;
          }
          return (
            <ul className="text-secondary">
              {rows.map(([section, value]) => {
                const { enabled, backend } = value as { enabled?: unknown; backend?: unknown };
                return (
                  <li key={section} className="flex items-center gap-2 py-0.5">
                    <span className="min-w-0 flex-1 truncate">{section}</span>
                    {backend !== undefined && backend !== "" && (
                      <span className="shrink-0 text-muted-foreground text-xs">{String(backend)}</span>
                    )}
                    <span className="shrink-0 text-muted-foreground text-xs">
                      {enabled ? "on" : "off"}
                    </span>
                  </li>
                );
              })}
            </ul>
          );
        }}
      </ResourceView>
    </Section>
  );
}

/**
 * Whether each secret is *configured* — never its value.
 *
 * The backend redacts secrets server-side (`SettingsService.
 * public_snapshot()`, the M8 Phase 2 security fix), so what arrives here
 * is already `**********` for anything sensitive. This panel reports
 * presence, which is the question an administrator actually has, and it
 * does no redaction of its own: a second redaction layer would imply the
 * first might be incomplete, and the fix for that would belong on the
 * server.
 */
function SecretsStatusPanel() {
  const { state, refresh } = useBackendResource(() => settingsApi.all(), []);

  return (
    <Section title="Secrets">
      <ResourceView state={state} label="Secrets" onRetry={refresh}>
        {(tree) => {
          const rows: Array<{ path: string; configured: boolean }> = [];
          const walk = (node: unknown, prefix: string) => {
            if (!node || typeof node !== "object" || Array.isArray(node)) return;
            for (const [key, value] of Object.entries(node as Record<string, unknown>)) {
              const path = prefix ? `${prefix}.${key}` : key;
              if (typeof value === "string") {
                if (/secret|password|api_key|apikey|token|credential/i.test(key)) {
                  rows.push({ path, configured: value.length > 0 });
                }
              } else {
                walk(value, path);
              }
            }
          };
          walk(tree, "");

          if (rows.length === 0) {
            return <p className="p-3 text-center text-muted-foreground text-xs">No secrets declared.</p>;
          }
          return (
            <VirtualList
              items={rows}
              estimatedItemHeight={22}
              className="max-h-48"
              renderItem={(row) => (
                <li key={row.path} className="flex items-center gap-2 py-0.5 text-xs">
                  <span className="min-w-0 flex-1 truncate font-mono">{row.path}</span>
                  <span className={row.configured ? "text-emerald-500" : "text-muted-foreground"}>
                    {row.configured ? "configured" : "not set"}
                  </span>
                </li>
              )}
            />
          );
        }}
      </ResourceView>
    </Section>
  );
}

function AuditLogPanel() {
  const { state, refresh } = useBackendResource(() => auditApi.permissionLog(), []);

  return (
    <Section title="Audit log">
      <ResourceView
        state={state}
        label="Audit entries"
        onRetry={refresh}
        emptyMessage="No permission decisions recorded."
      >
        {(entries) => (
          <>
            <VirtualList
              items={entries}
              estimatedItemHeight={22}
              className="max-h-48"
              renderItem={(entry, index) => (
                <li key={`${entry.at}-${index}`} className="flex items-center gap-2 py-0.5 text-xs">
                  <span className="w-32 shrink-0 truncate font-mono">{entry.plugin_id}</span>
                  <span className="min-w-0 flex-1 truncate">{entry.scope}</span>
                  <span className="shrink-0 text-muted-foreground">{entry.action}</span>
                </li>
              )}
            />
            <p className="text-muted-foreground text-xs">
              Permission decisions from the plugin Permission Model — the only audit trail the
              backend keeps today.
            </p>
          </>
        )}
      </ResourceView>
    </Section>
  );
}

/**
 * The seven panels that have no backend, named rather than mocked.
 *
 * This is a deliberate product decision, not an apology: an
 * administrator seeing "Budget: $0.00" would reasonably conclude nothing
 * had been spent. Seeing "budget tracking arrives with the Cost
 * Optimizer" tells them the truth.
 */
function PendingCapabilities() {
  const pending = [
    ["Users & roles", "No account model exists yet (§22.11)."],
    ["Daily & monthly budgets", "Arrives with the AI Cost Optimizer (§22.3)."],
    ["Provider priority", "Set by the AI/API Calibration Engine (§22.2)."],
    ["Calibration status", "Reported by hardware calibration (§22.8)."],
    ["Analytics", "Served by the Oracle Cloud tier (§22.5)."],
    ["Synchronization", "Served by the Oracle Cloud tier (§22.5)."],
  ];

  return (
    <Section title="Not yet available">
      <div className="flex items-start gap-2 pb-1">
        <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" aria-hidden="true" />
        <p className="text-muted-foreground text-xs">
          These are approved architecture, not yet built. Nothing below is estimated or simulated.
        </p>
      </div>
      <ul className="text-secondary">
        {pending.map(([name, why]) => (
          <li key={name} className="flex flex-col py-0.5">
            <span className="text-xs">{name}</span>
            <span className="text-muted-foreground text-xs">{why}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}
