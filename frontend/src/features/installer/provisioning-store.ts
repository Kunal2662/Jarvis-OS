import { create } from "zustand";
import {
  classifyFailure,
  isProgressEvent,
  isResultEvent,
  type DownloadEvent,
  type DownloadItemState,
  type FailureDescription,
  type ProgressEvent,
  type ProvisioningEvent,
  type ProvisioningLabel,
  type ProvisioningStep,
  type ResultEvent,
} from "@/features/installer/provisioning-types";

/**
 * Provisioning state, fed by the backend's event stream -- M22
 * installer UI.
 *
 * **The backend is authoritative and this store does not second-guess
 * it.** Step, percentage, per-item state and byte counts are stored as
 * received. There is no local notion of "which step should be running"
 * and no client-side step machine — a UI that tracked its own idea of
 * progress alongside the engine's would eventually disagree with it,
 * and the engine would be right.
 *
 * **Two things are derived, for a reason.** Transfer speed and time
 * remaining are computed here because the engine deliberately does not
 * emit them: a rate is a property of an observer over an interval, not a
 * fact about a download, and putting a stopwatch in the provisioning
 * engine would make it report different numbers to two consumers. They
 * are derived *from* the authoritative byte counts, never counted
 * independently.
 */

/** Speed is smoothed over a short window rather than computed from the
 *  last two events. Chunk arrival is bursty, so an instantaneous rate
 *  swings wildly and renders as a number that is unreadable and looks
 *  broken. */
const SPEED_WINDOW_MS = 3_000;
const MIN_SAMPLES_FOR_SPEED = 2;

interface Sample {
  at: number;
  bytes: number;
}

export interface DownloadItem extends DownloadEvent {
  /** Stable identity across events. The friendly name, since a personal
   *  payload carries no id — two items never share a name in practice
   *  because the engine labels one model and distinct voice components. */
  id: string;
}

export type ProvisioningPhase = "idle" | "running" | "succeeded" | "failed";

interface ProvisioningState {
  phase: ProvisioningPhase;
  /** `true` once the engine reports a resumed run. Drives "Resuming
   *  installation…" — read from the result, and inferred from skipped
   *  steps while the run is still in flight. */
  resuming: boolean;

  step: ProvisioningStep | null;
  label: ProvisioningLabel | null;
  completedSteps: number;
  totalSteps: number;
  percent: number;

  /** Ordered by first appearance, so the list does not reshuffle. */
  downloads: DownloadItem[];

  bytesDownloaded: number;
  bytesTotal: number | null;
  /** Bytes per second, or `null` before there is enough signal to say. */
  speedBytesPerSecond: number | null;
  /** Seconds, or `null` when the total is unknown or the rate is not yet
   *  established. Never a guess. */
  etaSeconds: number | null;

  result: ResultEvent | null;
  failure: FailureDescription | null;
  /** Administrator-only text, when the payload carried it. */
  detail: string | null;

  ingest: (event: ProvisioningEvent) => void;
  begin: () => void;
  fail: (message: string) => void;
  reset: () => void;
}

const INITIAL = {
  phase: "idle" as ProvisioningPhase,
  resuming: false,
  step: null,
  label: null,
  completedSteps: 0,
  totalSteps: 8,
  percent: 0,
  downloads: [] as DownloadItem[],
  bytesDownloaded: 0,
  bytesTotal: null as number | null,
  speedBytesPerSecond: null as number | null,
  etaSeconds: null as number | null,
  result: null as ResultEvent | null,
  failure: null as FailureDescription | null,
  detail: null as string | null,
};

/**
 * Samples live outside the store deliberately.
 *
 * They are a measurement buffer, not application state: nothing renders
 * them, and putting them in the store would re-render every subscriber
 * on each chunk while adding nothing to the screen.
 */
let samples: Sample[] = [];
let clock: () => number = () => Date.now();

function recordSample(totalBytes: number): { speed: number | null } {
  const now = clock();
  samples.push({ at: now, bytes: totalBytes });
  samples = samples.filter((sample) => now - sample.at <= SPEED_WINDOW_MS);

  if (samples.length < MIN_SAMPLES_FOR_SPEED) return { speed: null };

  const oldest = samples[0];
  const elapsedSeconds = (now - oldest.at) / 1000;
  const deltaBytes = totalBytes - oldest.bytes;

  // A window with no elapsed time or no new bytes yields no rate. `0`
  // would render as "0 B/s", which reads as stalled rather than as
  // "not yet known".
  if (elapsedSeconds <= 0 || deltaBytes <= 0) return { speed: null };

  return { speed: deltaBytes / elapsedSeconds };
}

/** Merge a download event into the ordered list, matching on name. */
function mergeDownload(existing: DownloadItem[], event: DownloadEvent): DownloadItem[] {
  const id = event.name || event.kind || "item";
  const index = existing.findIndex((item) => item.id === id);
  const merged: DownloadItem = { ...event, id };

  if (index === -1) return [...existing, merged];
  const next = [...existing];
  next[index] = merged;
  return next;
}

function totalsFrom(downloads: DownloadItem[]): { downloaded: number; total: number | null } {
  let downloaded = 0;
  let total = 0;
  let everyTotalKnown = true;

  for (const item of downloads) {
    downloaded += item.downloaded_bytes;
    if (item.total_bytes === null) everyTotalKnown = false;
    else total += item.total_bytes;
  }

  // One unknown size makes the *aggregate* unknown. Summing the ones we
  // do know would produce a total smaller than reality and a progress
  // bar that runs past its own end.
  return { downloaded, total: everyTotalKnown && downloads.length > 0 ? total : null };
}

export const useProvisioningStore = create<ProvisioningState>()((set, get) => ({
  ...INITIAL,

  begin: () => {
    samples = [];
    set({ ...INITIAL, phase: "running" });
  },

  ingest: (event) => {
    if (isProgressEvent(event)) {
      const progress: ProgressEvent = event;
      const state = get();

      const downloads = progress.download
        ? mergeDownload(state.downloads, progress.download)
        : state.downloads;

      const { downloaded, total } = totalsFrom(downloads);
      const { speed } = progress.download ? recordSample(downloaded) : { speed: null };

      const remaining = total === null ? null : Math.max(0, total - downloaded);
      const eta =
        speed !== null && speed > 0 && remaining !== null ? remaining / speed : null;

      set({
        phase: "running",
        step: progress.step,
        label: progress.label,
        completedSteps: progress.completed_steps,
        totalSteps: progress.total_steps,
        percent: progress.percent,
        downloads,
        bytesDownloaded: downloaded,
        bytesTotal: total,
        // Keep the last known rate while a step that is not downloading
        // runs, rather than blanking it and making the display flicker.
        speedBytesPerSecond: speed ?? (progress.download ? state.speedBytesPerSecond : null),
        etaSeconds: eta ?? (progress.download ? state.etaSeconds : null),
        detail: progress.detail ?? state.detail,
      });
      return;
    }

    if (isResultEvent(event)) {
      const result: ResultEvent = event;
      set({
        phase: result.succeeded ? "succeeded" : "failed",
        resuming: result.resumed,
        result,
        percent: result.succeeded ? 100 : get().percent,
        speedBytesPerSecond: null,
        etaSeconds: null,
        failure: result.succeeded ? null : classifyFailure(result.errors.join(" ")),
      });
    }
  },

  fail: (message) =>
    set({
      phase: "failed",
      failure: classifyFailure(message),
      speedBytesPerSecond: null,
      etaSeconds: null,
    }),

  reset: () => {
    samples = [];
    set({ ...INITIAL });
  },
}));

/** Test seam: makes speed and ETA deterministic without faking the
 *  arithmetic they are meant to prove. */
export function setProvisioningClockForTesting(source: (() => number) | null): void {
  clock = source ?? (() => Date.now());
  samples = [];
}

// --- Selectors --------------------------------------------------------

/**
 * Items grouped for the download view.
 *
 * **Not a zustand selector.** It builds a new object on every call, and
 * zustand compares selector results by reference, so passing this to
 * `useProvisioningStore` makes every render look like a state change and
 * loops until React aborts with "Maximum update depth exceeded". Call it
 * from a `useMemo` over the stable `downloads` array instead.
 *
 * Dependencies are not downloads and appear via the result's own checks,
 * not here.
 */
export function groupByKind(downloads: DownloadItem[]): {
  models: DownloadItem[];
  voices: DownloadItem[];
  other: DownloadItem[];
} {
  return {
    models: downloads.filter((item) => item.kind === "model"),
    voices: downloads.filter((item) => item.kind === "voice"),
    other: downloads.filter((item) => item.kind !== "model" && item.kind !== "voice"),
  };
}

export function selectIsResuming(state: ProvisioningState): boolean {
  // While a run is in flight the result has not arrived yet, so a run
  // that has already skipped a step is the earliest honest signal.
  return state.resuming || (state.result?.skipped_steps.length ?? 0) > 0;
}

// --- Formatting -------------------------------------------------------

export function formatBytes(bytes: number | null): string {
  if (bytes === null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value.toFixed(value < 10 && unit > 0 ? 1 : 0)} ${units[unit]}`;
}

export function formatSpeed(bytesPerSecond: number | null): string {
  if (bytesPerSecond === null) return "—";
  return `${formatBytes(bytesPerSecond)}/s`;
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return "less than a minute";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `about ${minutes} minute${minutes === 1 ? "" : "s"}`;
  const hours = Math.round(minutes / 60);
  return `about ${hours} hour${hours === 1 ? "" : "s"}`;
}

/** What each per-item state is called on screen. Data rather than a
 *  switch so the download view and its tests read the same table. */
export const DOWNLOAD_STATE_LABEL: Record<DownloadItemState, string> = {
  queued: "Waiting",
  running: "Downloading",
  paused: "Paused",
  verifying: "Checking",
  completed: "Ready",
  skipped: "Already installed",
  failed: "Failed",
  cancelled: "Cancelled",
};
