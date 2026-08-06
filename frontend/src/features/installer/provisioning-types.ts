/**
 * The provisioning event contract -- M22 installer UI.
 *
 * Mirrors what `python -m jarvis.installer provision --stream` emits:
 * newline-delimited JSON, one `progress` event per engine callback and a
 * final `result`. Written against a **captured real stream**
 * (`provision-stream.fixture.ndjson`), not from the brief — the same
 * discipline that M8 Phase 2 adopted after a hand-written contract
 * shipped eleven event names the backend had never emitted.
 *
 * **The backend is authoritative.** Nothing here re-derives a fact the
 * engine already reports: step, percent, byte counts and per-item state
 * all come from the stream verbatim. The two values the UI *does*
 * compute — transfer speed and estimated time remaining — are computed
 * because the engine deliberately does not carry them (a rate is a
 * property of an observer, not of a download), and they are derived from
 * the authoritative byte counts rather than counted independently.
 *
 * **Personal payloads are structurally smaller.** `detail`, `key`,
 * `source_name` and `attempts` are present only for an administrator,
 * because the Python side omits them entirely (`ARCHITECTURE.md`
 * §22.11/§22.12). That is why they are optional properties: absent, not
 * merely hidden.
 */

/** The engine's own step ids, in execution order. */
export const PROVISIONING_STEPS = [
  "dependencies",
  "directories",
  "configuration",
  "model_download",
  "voice_download",
  "first_run",
  "verification",
  "manifest",
] as const;

export type ProvisioningStep = (typeof PROVISIONING_STEPS)[number];

/** The §22.12 phrases the engine emits. Never a step id. */
export type ProvisioningLabel =
  | "Preparing…"
  | "Installing…"
  | "Downloading…"
  | "Optimizing…"
  | "Verifying…"
  | "Finalizing…";

/** `DownloadState` from `jarvis/installer/download.py`. */
export type DownloadItemState =
  | "queued"
  | "running"
  | "paused"
  | "verifying"
  | "completed"
  | "failed"
  | "cancelled"
  | "skipped";

export type ArtifactKind = "model" | "voice";

export interface DownloadEvent {
  /** Friendly label — "Local AI", "Local speech synthesis". Never an id. */
  name: string;
  kind: ArtifactKind | "";
  state: DownloadItemState;
  downloaded_bytes: number;
  total_bytes: number | null;
  /** `null` when the server sent no `Content-Length`; the UI then shows
   *  an indeterminate bar rather than inventing a denominator. */
  percent: number | null;
  verified: boolean;
  /** Administrator only. */
  key?: string;
  source_name?: string | null;
  attempts?: number;
  message?: string;
}

export interface ProgressEvent {
  event: "progress";
  step: ProvisioningStep;
  label: ProvisioningLabel;
  completed_steps: number;
  total_steps: number;
  percent: number;
  download?: DownloadEvent;
  /** Administrator only. */
  detail?: string;
}

export interface VerificationResultEvent {
  key: string;
  label: string;
  verdict: "pass" | "warn" | "fail";
  detail: string;
  repairable: boolean;
  repair_step: string | null;
}

export interface ResultEvent {
  event: "result";
  root: string;
  resumed: boolean;
  succeeded: boolean;
  completed_steps: string[];
  skipped_steps: string[];
  errors: string[];
  verification?: {
    healthy: boolean;
    results: VerificationResultEvent[];
  };
  /** Administrator only. */
  downloads?: Record<string, DownloadEvent>;
  manifest_path?: string | null;
}

export type ProvisioningEvent = ProgressEvent | ResultEvent;

export function isProgressEvent(event: ProvisioningEvent): event is ProgressEvent {
  return event.event === "progress";
}

export function isResultEvent(event: ProvisioningEvent): event is ResultEvent {
  return event.event === "result";
}

// --- Failure classification -------------------------------------------

/**
 * The failure categories the brief requires friendly messages for.
 *
 * Classified from the engine's error text rather than from an error
 * code, because the engine raises real exceptions with real messages and
 * inventing a parallel code enum would be a second source of truth for
 * the same fact. The matching is deliberately broad — a misclassified
 * failure still shows a truthful message, since every category's copy is
 * accurate about what the user can do.
 */
export type FailureKind =
  | "network"
  | "checksum"
  | "disk_full"
  | "permission"
  | "dependency"
  | "cancelled"
  | "unknown";

export interface FailureDescription {
  kind: FailureKind;
  title: string;
  detail: string;
  /** Whether retrying without user action could plausibly succeed. */
  retryable: boolean;
}

const FAILURE_PATTERNS: Array<[FailureKind, RegExp]> = [
  ["cancelled", /cancel/i],
  ["checksum", /checksum|integrity|corrupt/i],
  ["disk_full", /no space|disk full|enospc|not enough space/i],
  ["permission", /permission|denied|access is denied|eacces|read-only/i],
  ["dependency", /dependenc|required .* missing|missing: /i],
  ["network", /network|connection|urlerror|httperror|timeout|unreachable|dns|refused|socket/i],
];

export function classifyFailure(message: string): FailureDescription {
  const kind = FAILURE_PATTERNS.find(([, pattern]) => pattern.test(message))?.[0] ?? "unknown";

  switch (kind) {
    case "network":
      return {
        kind,
        title: "Connection lost",
        detail:
          "JARVIS couldn’t reach the download service. Check your connection — your progress has been saved.",
        retryable: true,
      };
    case "checksum":
      return {
        kind,
        title: "A download was damaged",
        detail:
          "One of the files didn’t arrive intact. JARVIS will fetch it again from the start.",
        retryable: true,
      };
    case "disk_full":
      return {
        kind,
        title: "Not enough space",
        detail: "Free up some disk space, then continue. Nothing already installed will be lost.",
        // Retryable, but only after the user acts -- the copy says so
        // rather than the button implying a retry would work as-is.
        retryable: true,
      };
    case "permission":
      return {
        kind,
        title: "JARVIS can’t write here",
        detail:
          "The installation folder isn’t writable. Choose a different location, or grant permission and try again.",
        retryable: true,
      };
    case "dependency":
      return {
        kind,
        title: "Something JARVIS needs is missing",
        detail:
          "A required component isn’t available on this device. Install it and continue — the rest of your installation is intact.",
        retryable: true,
      };
    case "cancelled":
      return {
        kind,
        title: "Installation cancelled",
        detail: "You can pick up where you left off — completed steps won’t be repeated.",
        retryable: true,
      };
    default:
      return {
        kind: "unknown",
        title: "Installation stopped",
        detail:
          "Something unexpected happened. Your progress has been saved, so continuing will resume from here.",
        retryable: true,
      };
  }
}
