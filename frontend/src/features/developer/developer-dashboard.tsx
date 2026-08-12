import { useMemo } from "react";
import { Lock } from "lucide-react";
import { ResourceView } from "@/components/common/resource-view";
import { VirtualList } from "@/components/common/virtual-list";
import { useBackendResource } from "@/hooks/use-backend-resource";
import { devtoolsApi, mcpApi } from "@/services/api/endpoints";
import { RELAYED_EVENTS } from "@/services/websocket";
import { useAgentActivityStore } from "@/stores/agent-activity.store";
import { useHealthStore, selectEgressStats, selectProviders } from "@/stores/health.store";
import { useHasMode } from "@/stores/user-mode.store";

/**
 * The Developer Dashboard -- M8 Phase 5. **Developer Mode only.**
 *
 * Everything on this page is information `ARCHITECTURE.md` §22.12 puts
 * off-limits to personal users: provider names, routing, internal agent
 * node names, backend service names, API paths, raw debug state. The
 * gate is `useHasMode("developer")`, which reads
 * `stores/user-mode.store.ts` — the single place the current audience is
 * decided, so this page and every other restricted surface cannot
 * disagree about who is allowed to see what.
 *
 * The gate is a *render* gate, not a security boundary: the routes
 * behind it are session-authenticated like every other route, and a
 * determined user with a session token can call them directly. That is
 * the correct division — the backend authenticates, the frontend decides
 * what to *show*. §22.12 is a product rule about what a personal user's
 * JARVIS contains, not a claim that these endpoints are secret.
 *
 * Every panel reads a real M9 Task Group E / M10.5 route. Nothing here
 * is synthesised.
 */
export function DeveloperDashboard() {
  const allowed = useHasMode("developer");
  if (!allowed) return <Restricted />;
  return <DeveloperDashboardContent />;
}

function Restricted() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
      <Lock className="size-icon-lg text-muted-foreground" aria-hidden="true" />
      <p className="font-medium text-secondary">Developer Mode required</p>
      <p className="max-w-sm text-muted-foreground text-xs">
        This view shows internal diagnostics. Unlock Developer Mode to open it.
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

function DeveloperDashboardContent() {
  return (
    <div className="grid h-full grid-cols-1 gap-2 overflow-auto p-2 lg:grid-cols-2">
      <ProvidersPanel />
      <EgressPanel />
      <ApiDiagnosticsPanel />
      <PerformancePanel />
      <AgentActivityPanel />
      <EventVocabularyPanel />
      <RuntimeStatePanel />
    </div>
  );
}

/** Provider names and transports — §22.12's headline restriction. */
function ProvidersPanel() {
  const { state, refresh } = useBackendResource(() => mcpApi.providers(), []);
  const fromHealth = useHealthStore(selectProviders);

  return (
    <Section title="Providers & routing">
      <ResourceView state={state} label="Providers" onRetry={refresh} emptyMessage="No MCP providers registered.">
        {(providers) => (
          <ul className="text-secondary">
            {providers.map((provider) => (
              <li key={provider.provider_id} className="flex items-center gap-2 py-0.5">
                <span className="min-w-0 flex-1 truncate">{provider.name || provider.provider_id}</span>
                <span className="shrink-0 text-muted-foreground text-xs">{provider.transport}</span>
                <span className="shrink-0 text-muted-foreground text-xs">{provider.state}</span>
              </li>
            ))}
          </ul>
        )}
      </ResourceView>
      {fromHealth && (
        <p className="pt-1 text-muted-foreground text-xs">
          {Object.keys(fromHealth).length} provider(s) reporting through the health poll.
        </p>
      )}
    </Section>
  );
}

/** The audited egress gateway's own counters. `failures` climbing while
 *  `calls` climbs is the signal a vendor or credential has gone bad. */
function EgressPanel() {
  const stats = useHealthStore(selectEgressStats);

  return (
    <Section title="Outbound API calls">
      {stats === null ? (
        <p className="p-3 text-center text-muted-foreground text-xs">
          Waiting for the backend health poll.
        </p>
      ) : (
        <dl className="grid grid-cols-2 gap-2 py-1">
          {Object.entries(stats).map(([key, value]) => (
            <div key={key} className="flex flex-col">
              <dt className="text-muted-foreground text-xs">{key.replace(/_/g, " ")}</dt>
              <dd className="font-semibold tabular-nums">{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </Section>
  );
}

function ApiDiagnosticsPanel() {
  const { state, refresh } = useBackendResource(() => devtoolsApi.apiCalls(100), []);

  return (
    <Section title="API inspector">
      <ResourceView
        state={state}
        label="API calls"
        onRetry={refresh}
        emptyMessage="No calls recorded — the API inspector may be disabled."
      >
        {(calls) => (
          <VirtualList
            items={calls}
            estimatedItemHeight={26}
            className="max-h-56"
            renderItem={(call, index) => (
              <li key={`${call.at}-${index}`} className="flex items-center gap-2 py-0.5 text-xs">
                <span className="w-12 shrink-0 font-mono text-muted-foreground">{call.method}</span>
                <span className="min-w-0 flex-1 truncate font-mono">{call.path}</span>
                <span
                  className={`shrink-0 tabular-nums ${
                    call.status_code >= 500
                      ? "text-destructive"
                      : call.status_code >= 400
                        ? "text-amber-500"
                        : "text-muted-foreground"
                  }`}
                >
                  {call.status_code}
                </span>
                <span className="w-14 shrink-0 text-right tabular-nums text-muted-foreground">
                  {call.duration_ms?.toFixed?.(0) ?? "—"}ms
                </span>
              </li>
            )}
          />
        )}
      </ResourceView>
    </Section>
  );
}

function PerformancePanel() {
  const { state, refresh } = useBackendResource(() => devtoolsApi.performanceMetrics(), []);

  return (
    <Section title="Performance metrics">
      <ResourceView state={state} label="Metrics" skeleton="stats" onRetry={refresh}>
        {(metrics) => (
          <dl className="grid grid-cols-2 gap-2 py-1">
            {metrics.slice(0, 8).map((metric) => (
              <div key={metric.name} className="flex flex-col">
                <dt className="truncate text-muted-foreground text-xs">{metric.name}</dt>
                <dd className="font-semibold tabular-nums">
                  {metric.value}
                  <span className="ml-1 font-normal text-muted-foreground text-xs">{metric.unit}</span>
                </dd>
              </div>
            ))}
          </dl>
        )}
      </ResourceView>
    </Section>
  );
}

/** Internal agent node names — restricted, and the reason the personal
 *  Activity Center shows progress phrases instead. */
function AgentActivityPanel() {
  const steps = useAgentActivityStore((s) => s.agentSteps);

  return (
    <Section title="Agent trace">
      {steps.length === 0 ? (
        <p className="p-3 text-center text-muted-foreground text-xs">No agent steps this session.</p>
      ) : (
        <VirtualList
          items={steps}
          estimatedItemHeight={24}
          className="max-h-56"
          renderItem={(step) => (
            <li
              key={`${step.thread_id}:${step.step}`}
              className="flex items-center gap-2 py-0.5 text-xs"
            >
              <span className="w-8 shrink-0 text-right tabular-nums text-muted-foreground">
                {step.step}
              </span>
              <span className="w-24 shrink-0 truncate font-mono">{step.node}</span>
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{step.detail}</span>
              <span className="shrink-0 text-muted-foreground">{step.status}</span>
            </li>
          )}
        />
      )}
    </Section>
  );
}

/** The relay's real event vocabulary, generated from the backend's own
 *  `EVENT_TYPE_NAMES` (M8 Phase 2's contract gate). Grouped by category
 *  so a developer can see at a glance what the socket can deliver. */
function EventVocabularyPanel() {
  const grouped = useMemo(() => {
    const groups = new Map<string, string[]>();
    for (const name of RELAYED_EVENTS) {
      const category = name.split(".")[0];
      groups.set(category, [...(groups.get(category) ?? []), name]);
    }
    return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, []);

  return (
    <Section title={`WebSocket events (${RELAYED_EVENTS.length})`}>
      <div className="flex max-h-56 flex-wrap gap-1 overflow-auto py-1">
        {grouped.map(([category, names]) => (
          <span
            key={category}
            className="rounded bg-muted px-1.5 py-0.5 font-mono text-muted-foreground text-xs"
            title={names.join("\n")}
          >
            {category} ({names.length})
          </span>
        ))}
      </div>
    </Section>
  );
}

function RuntimeStatePanel() {
  const { state, refresh } = useBackendResource(() => devtoolsApi.state(), []);

  return (
    <Section title="Runtime state">
      <ResourceView state={state} label="Runtime state" onRetry={refresh}>
        {(runtimeState) => (
          <pre className="max-h-56 overflow-auto rounded bg-muted/40 p-2 font-mono text-xs">
            {JSON.stringify(runtimeState, null, 2)}
          </pre>
        )}
      </ResourceView>
    </Section>
  );
}
