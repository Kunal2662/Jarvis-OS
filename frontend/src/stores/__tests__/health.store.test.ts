import { beforeEach, describe, expect, it } from "vitest";
import {
  formatBytes,
  formatUptime,
  selectAiWorkspaceStatus,
  selectEgressStats,
  selectFilesStatus,
  selectOverallStatus,
  selectProviders,
  selectSearchSources,
  selectServiceStatus,
  selectSourceStatus,
  useHealthStore,
  type HealthSnapshot,
} from "@/stores/health.store";

/**
 * The snapshot shape below is the real one — read off
 * `HealthMonitor.snapshot()` and the two `register_collector` calls in
 * `app.py`, not invented. If the backend's collectors change, these
 * tests are where the frontend finds out.
 */
const SNAPSHOT: HealthSnapshot = {
  cpu_percent: 12.5,
  memory_rss_bytes: 268_435_456,
  disk_free_bytes: 10_737_418_240,
  uptime_seconds: 93_600,
  startup_duration_ms: 1_450,
  active_services: ["voice", "automation"],
  failed_services: [],
  restart_count: 0,
  status: "healthy",
  mcp: { providers: { google: { state: "connected" } } },
  workspace_platform: {
    files: { storage_root: "/data/files", storage_root_exists: true, indexing_enabled: true },
    ai_workspace: { enabled: true, assist_enabled: true, context_budget_chars: 8000 },
    egress: { calls: 42, failures: 1 },
    search_sources: ["memory", "knowledge", "files"],
  },
};

const state = () => useHealthStore.getState();

beforeEach(() => useHealthStore.setState({ snapshot: null, receivedAt: null }));

describe("lifecycle", () => {
  it("starts with no snapshot rather than an optimistic default", () => {
    // A health display that invents a green light is the worst possible
    // lie this store could tell.
    expect(state().snapshot).toBeNull();
    expect(selectOverallStatus(state())).toBe("unknown");
  });

  it("applies a snapshot with its event timestamp", () => {
    state().apply(SNAPSHOT, "2026-08-06T10:00:00.000Z");
    expect(state().snapshot?.cpu_percent).toBe(12.5);
    expect(state().receivedAt).toBe("2026-08-06T10:00:00.000Z");
  });

  it("clears on disconnect", () => {
    // A snapshot from before an outage describes a backend that is no
    // longer running.
    state().apply(SNAPSHOT);
    state().clear();
    expect(state().snapshot).toBeNull();
    expect(selectOverallStatus(state())).toBe("unknown");
  });
});

describe("selectors", () => {
  beforeEach(() => state().apply(SNAPSHOT));

  it("reports overall status", () => {
    expect(selectOverallStatus(state())).toBe("healthy");
    state().apply({ ...SNAPSHOT, status: "degraded" });
    expect(selectOverallStatus(state())).toBe("degraded");
  });

  it("reads a service from the running and failed lists", () => {
    expect(selectServiceStatus("voice")(state())).toBe("healthy");
    state().apply({ ...SNAPSHOT, failed_services: ["voice"] });
    expect(selectServiceStatus("voice")(state())).toBe("degraded");
  });

  it("returns unknown for a service the backend never mentions", () => {
    // Not "degraded": a service absent from both lists has not failed,
    // it simply is not reporting.
    expect(selectServiceStatus("vision")(state())).toBe("unknown");
  });

  it("reads knowledge and memory from the search-source registry", () => {
    expect(selectSearchSources(state())).toEqual(["memory", "knowledge", "files"]);
    expect(selectSourceStatus("knowledge")(state())).toBe("healthy");
    // Reporting, and this source is genuinely absent from the list.
    expect(selectSourceStatus("goals")(state())).toBe("degraded");
  });

  it("distinguishes an absent collector from an unregistered source", () => {
    // A backend running without the `workspace_platform` collector (the
    // API-only runtime, say) used to light up Memory and Knowledge
    // Graph amber, which reads as a fault where there is none. Found
    // against a live backend in the M8 Phase 7 pass.
    state().apply({ status: "healthy" });

    expect(selectSourceStatus("memory")(state())).toBe("unknown");
    expect(selectSourceStatus("knowledge")(state())).toBe("unknown");
  });

  it("still reports degraded when the collector reports an empty list", () => {
    // Reporting zero sources *is* a real degradation -- every source
    // unregistered itself.
    state().apply({
      ...SNAPSHOT,
      workspace_platform: { ...SNAPSHOT.workspace_platform, search_sources: [] },
    });

    expect(selectSourceStatus("memory")(state())).toBe("degraded");
  });

  it("distinguishes AI workspace disabled from degraded", () => {
    expect(selectAiWorkspaceStatus(state())).toBe("healthy");

    state().apply({
      ...SNAPSHOT,
      workspace_platform: { ...SNAPSHOT.workspace_platform, ai_workspace: { enabled: false } },
    });
    expect(selectAiWorkspaceStatus(state())).toBe("disabled");

    state().apply({
      ...SNAPSHOT,
      workspace_platform: {
        ...SNAPSHOT.workspace_platform,
        ai_workspace: { enabled: true, assist_enabled: false },
      },
    });
    expect(selectAiWorkspaceStatus(state())).toBe("degraded");
  });

  it("surfaces an unwritable storage root", () => {
    // The failure this collector was added to make visible.
    state().apply({
      ...SNAPSHOT,
      workspace_platform: {
        ...SNAPSHOT.workspace_platform,
        files: { storage_root_exists: false },
      },
    });
    expect(selectFilesStatus(state())).toBe("degraded");
  });

  it("exposes egress counters and providers for restricted surfaces", () => {
    expect(selectEgressStats(state())).toEqual({ calls: 42, failures: 1 });
    expect(selectProviders(state())).toEqual({ google: { state: "connected" } });
  });

  it("returns null rather than an empty object when a collector is absent", () => {
    state().apply({ status: "healthy" });
    expect(selectEgressStats(state())).toBeNull();
    expect(selectProviders(state())).toBeNull();
  });

  it("every selector answers 'unknown' with no snapshot", () => {
    useHealthStore.setState({ snapshot: null, receivedAt: null });
    expect(selectServiceStatus("voice")(state())).toBe("unknown");
    expect(selectSourceStatus("memory")(state())).toBe("unknown");
    expect(selectAiWorkspaceStatus(state())).toBe("unknown");
    expect(selectFilesStatus(state())).toBe("unknown");
  });
});

describe("formatting", () => {
  it("formats bytes at a sensible scale", () => {
    expect(formatBytes(undefined)).toBe("—");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(268_435_456)).toBe("256 MB");
    expect(formatBytes(1_610_612_736)).toBe("1.5 GB");
  });

  it("formats uptime by the largest meaningful unit", () => {
    expect(formatUptime(undefined)).toBe("—");
    expect(formatUptime(300)).toBe("5m");
    expect(formatUptime(7_200)).toBe("2h 0m");
    expect(formatUptime(93_600)).toBe("1d 2h");
  });
});
