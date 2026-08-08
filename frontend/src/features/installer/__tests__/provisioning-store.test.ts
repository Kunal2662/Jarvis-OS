import { afterEach, beforeEach, describe, expect, it } from "vitest";
import rawStream from "./provision-stream.fixture.ndjson?raw";
import {
  formatBytes,
  formatDuration,
  formatSpeed,
  groupByKind,
  selectIsResuming,
  setProvisioningClockForTesting,
  useProvisioningStore,
} from "@/features/installer/provisioning-store";
import {
  classifyFailure,
  type ProgressEvent,
  type ProvisioningEvent,
  type ResultEvent,
} from "@/features/installer/provisioning-types";

/**
 * The fixture is a **real captured stream** from
 * `python -m jarvis.installer provision --stream`, not a hand-written
 * approximation. Mapping backend events is exactly the boundary where
 * M8 Phase 2 shipped eleven invented event names, so it is tested
 * against what the backend actually emitted.
 */
const REAL_EVENTS: ProvisioningEvent[] = rawStream
  .split("\n")
  .filter((line) => line.trim())
  .map((line) => JSON.parse(line) as ProvisioningEvent);

const store = () => useProvisioningStore.getState();

function progress(overrides: Partial<ProgressEvent> = {}): ProgressEvent {
  return {
    event: "progress",
    step: "model_download",
    label: "Downloading…",
    completed_steps: 3,
    total_steps: 8,
    percent: 37.5,
    ...overrides,
  };
}

beforeEach(() => {
  useProvisioningStore.getState().reset();
  setProvisioningClockForTesting(null);
});

afterEach(() => setProvisioningClockForTesting(null));

describe("real backend stream", () => {
  it("the fixture is a genuine multi-event stream ending in a result", () => {
    // Guards the guard: an empty or truncated fixture would make every
    // assertion below pass vacuously.
    expect(REAL_EVENTS.length).toBeGreaterThan(5);
    expect(REAL_EVENTS.at(-1)?.event).toBe("result");
  });

  it("ingests the whole stream and finishes succeeded", () => {
    store().begin();
    for (const event of REAL_EVENTS) store().ingest(event);

    expect(store().phase).toBe("succeeded");
    expect(store().percent).toBe(100);
    expect(store().result?.succeeded).toBe(true);
  });

  it("groups what the backend downloaded", () => {
    store().begin();
    for (const event of REAL_EVENTS) store().ingest(event);

    const { models, voices } = groupByKind(store().downloads);
    expect(models.length).toBeGreaterThan(0);
    expect(voices.length).toBeGreaterThan(0);
  });

  it("sees the verifying state the engine emits", () => {
    const states = REAL_EVENTS.filter(
      (event): event is ProgressEvent => event.event === "progress",
    )
      .map((event) => event.download?.state)
      .filter(Boolean);

    expect(states).toContain("verifying");
  });

  it("carries no internal identifier anywhere in a personal stream", () => {
    // If the backend ever starts leaking a model id, a registry key or a
    // download URL into a personal payload, this fails here rather than
    // on a user's screen.
    const serialised = JSON.stringify(REAL_EVENTS).toLowerCase();

    for (const leak of ["llama", "qwen", "piper", "faster_whisper", "http://", "file://"]) {
      expect(serialised, `stream leaked "${leak}"`).not.toContain(leak);
    }
  });

  it("carries the user's own install folder, and no other path", () => {
    /*
     * `root` is deliberately present. It is the folder the user typed on
     * the Location step -- theirs, already on screen twice before this,
     * and required by the completion screen's "Open installation
     * folder" button. Excluding it would be hiding a fact from the
     * person who supplied it.
     *
     * Every *internal* path is administrator-only and must stay absent:
     * `manifest_path`, dependency locations and download sources.
     */
    const result = REAL_EVENTS.at(-1) as ResultEvent;

    expect(result.root).toBeTruthy();
    expect(result.manifest_path).toBeUndefined();
    expect(result.downloads).toBeUndefined();

    // No progress event carries a path at all -- only the final result
    // does, and only the user's own.
    const progressEvents = REAL_EVENTS.filter(
      (event): event is ProgressEvent => event.event === "progress",
    );
    for (const event of progressEvents) {
      expect(JSON.stringify(event)).not.toMatch(/[a-z]:\\\\|\/(usr|home|opt)\//i);
      expect(event.detail).toBeUndefined();
      expect(event.download?.key).toBeUndefined();
      expect(event.download?.source_name).toBeUndefined();
    }
  });
});

describe("progress mapping", () => {
  it("stores the backend's numbers rather than recomputing them", () => {
    store().begin();
    store().ingest(progress({ percent: 62.5, completed_steps: 5 }));

    expect(store().percent).toBe(62.5);
    expect(store().completedSteps).toBe(5);
    expect(store().label).toBe("Downloading…");
  });

  it("merges repeated events for one item instead of appending", () => {
    store().begin();
    for (const bytes of [10, 20, 30]) {
      store().ingest(
        progress({
          download: {
            name: "Local AI",
            kind: "model",
            state: "running",
            downloaded_bytes: bytes,
            total_bytes: 100,
            percent: bytes,
            verified: false,
          },
        }),
      );
    }

    expect(store().downloads).toHaveLength(1);
    expect(store().downloads[0].downloaded_bytes).toBe(30);
  });

  it("keeps items in first-appearance order so the list does not reshuffle", () => {
    store().begin();
    for (const name of ["Local AI", "Voice A", "Voice B"]) {
      store().ingest(
        progress({
          download: {
            name,
            kind: name === "Local AI" ? "model" : "voice",
            state: "running",
            downloaded_bytes: 1,
            total_bytes: 10,
            percent: 10,
            verified: false,
          },
        }),
      );
    }
    // Update the first one again.
    store().ingest(
      progress({
        download: {
          name: "Local AI",
          kind: "model",
          state: "completed",
          downloaded_bytes: 10,
          total_bytes: 10,
          percent: 100,
          verified: true,
        },
      }),
    );

    expect(store().downloads.map((item) => item.name)).toEqual([
      "Local AI",
      "Voice A",
      "Voice B",
    ]);
  });

  it("treats one unknown size as an unknown aggregate", () => {
    // Summing only the known sizes would give a total smaller than
    // reality and a bar that runs past its own end.
    store().begin();
    store().ingest(
      progress({
        download: {
          name: "A",
          kind: "model",
          state: "running",
          downloaded_bytes: 5,
          total_bytes: 10,
          percent: 50,
          verified: false,
        },
      }),
    );
    store().ingest(
      progress({
        download: {
          name: "B",
          kind: "voice",
          state: "running",
          downloaded_bytes: 5,
          total_bytes: null,
          percent: null,
          verified: false,
        },
      }),
    );

    expect(store().bytesDownloaded).toBe(10);
    expect(store().bytesTotal).toBeNull();
  });
});

describe("derived speed and time remaining", () => {
  function withClock(times: number[]) {
    let index = 0;
    setProvisioningClockForTesting(() => times[Math.min(index++, times.length - 1)]);
  }

  it("is null until there is enough signal to say", () => {
    // "0 B/s" would read as stalled; "—" reads as not yet known.
    withClock([0]);
    store().begin();
    store().ingest(
      progress({
        download: {
          name: "A",
          kind: "model",
          state: "running",
          downloaded_bytes: 1000,
          total_bytes: 10_000,
          percent: 10,
          verified: false,
        },
      }),
    );

    expect(store().speedBytesPerSecond).toBeNull();
    expect(store().etaSeconds).toBeNull();
  });

  it("derives a rate from the backend's byte counts", () => {
    withClock([0, 1000]); // one second apart
    store().begin();

    for (const bytes of [1000, 3000]) {
      store().ingest(
        progress({
          download: {
            name: "A",
            kind: "model",
            state: "running",
            downloaded_bytes: bytes,
            total_bytes: 10_000,
            percent: bytes / 100,
            verified: false,
          },
        }),
      );
    }

    // 2000 bytes in 1s.
    expect(store().speedBytesPerSecond).toBeCloseTo(2000, 0);
    // 7000 remaining at 2000 B/s.
    expect(store().etaSeconds).toBeCloseTo(3.5, 1);
  });

  it("reports no ETA when the total is unknown", () => {
    withClock([0, 1000]);
    store().begin();
    for (const bytes of [1000, 3000]) {
      store().ingest(
        progress({
          download: {
            name: "A",
            kind: "model",
            state: "running",
            downloaded_bytes: bytes,
            total_bytes: null,
            percent: null,
            verified: false,
          },
        }),
      );
    }

    expect(store().speedBytesPerSecond).toBeGreaterThan(0);
    expect(store().etaSeconds).toBeNull();
  });

  it("reports no rate when no new bytes arrived", () => {
    withClock([0, 1000]);
    store().begin();
    for (let i = 0; i < 2; i += 1) {
      store().ingest(
        progress({
          download: {
            name: "A",
            kind: "model",
            state: "running",
            downloaded_bytes: 1000,
            total_bytes: 10_000,
            percent: 10,
            verified: false,
          },
        }),
      );
    }

    expect(store().speedBytesPerSecond).toBeNull();
  });

  it("clears speed and ETA once the run ends", () => {
    withClock([0, 1000]);
    store().begin();
    for (const bytes of [1000, 3000]) {
      store().ingest(
        progress({
          download: {
            name: "A",
            kind: "model",
            state: "running",
            downloaded_bytes: bytes,
            total_bytes: 10_000,
            percent: 10,
            verified: false,
          },
        }),
      );
    }
    store().ingest({
      event: "result",
      root: "C:/JARVIS",
      resumed: false,
      succeeded: true,
      completed_steps: [],
      skipped_steps: [],
      errors: [],
    });

    expect(store().speedBytesPerSecond).toBeNull();
    expect(store().etaSeconds).toBeNull();
  });
});

describe("resume", () => {
  it("is reported from the backend's own result", () => {
    store().begin();
    store().ingest({
      event: "result",
      root: "C:/JARVIS",
      resumed: true,
      succeeded: true,
      completed_steps: ["manifest"],
      skipped_steps: ["dependencies", "directories"],
      errors: [],
    });

    expect(store().resuming).toBe(true);
    expect(selectIsResuming(store())).toBe(true);
  });

  it("is not claimed on a fresh run", () => {
    store().begin();
    store().ingest(progress());
    expect(selectIsResuming(store())).toBe(false);
  });
});

describe("failure", () => {
  function failWith(...errors: string[]): ResultEvent {
    return {
      event: "result",
      root: "C:/JARVIS",
      resumed: false,
      succeeded: false,
      completed_steps: ["dependencies"],
      skipped_steps: [],
      errors,
    };
  }

  it("classifies a failed result", () => {
    store().begin();
    store().ingest(failWith("model_download: URLError: connection refused"));

    expect(store().phase).toBe("failed");
    expect(store().failure?.kind).toBe("network");
    expect(store().failure?.retryable).toBe(true);
  });

  it("classifies a transport rejection the stream never reported", () => {
    store().begin();
    store().fail("Permission denied writing to C:/Program Files");

    expect(store().phase).toBe("failed");
    expect(store().failure?.kind).toBe("permission");
  });

  it("keeps the progress already made visible", () => {
    store().begin();
    store().ingest(
      progress({
        download: {
          name: "Local AI",
          kind: "model",
          state: "completed",
          downloaded_bytes: 10,
          total_bytes: 10,
          percent: 100,
          verified: true,
        },
      }),
    );
    store().ingest(failWith("voice_download: network unreachable"));

    // "Your progress has been saved" is more convincing when the
    // completed item is still on screen.
    expect(store().downloads).toHaveLength(1);
  });
});

describe("classifyFailure", () => {
  it.each([
    ["connection refused", "network"],
    ["Checksum did not match", "checksum"],
    ["OSError: [Errno 28] No space left on device", "disk_full"],
    ["PermissionError: access is denied", "permission"],
    ["Required dependencies are missing: Visual C++ runtime", "dependency"],
    ["Cancelled. Progress kept for resume.", "cancelled"],
    ["something nobody anticipated", "unknown"],
  ])("maps %j to %s", (message, expected) => {
    expect(classifyFailure(message).kind).toBe(expected);
  });

  it("offers a way forward for every category", () => {
    // Even "unknown" is retryable, because the journal makes continuing
    // safe regardless of what went wrong.
    for (const message of ["network", "checksum", "disk", "denied", "cancel", "???"]) {
      expect(classifyFailure(message).retryable).toBe(true);
      expect(classifyFailure(message).title).toBeTruthy();
    }
  });

  it("never names an internal cause in its copy", () => {
    for (const message of ["URLError", "ENOSPC", "sha256 mismatch"]) {
      const described = classifyFailure(message);
      const copy = `${described.title} ${described.detail}`.toLowerCase();
      for (const jargon of ["urlerror", "enospc", "sha256", "traceback", "exception"]) {
        expect(copy).not.toContain(jargon);
      }
    }
  });
});

describe("formatting", () => {
  it("formats bytes, speed and duration, and says '—' for unknown", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(1_610_612_736)).toBe("1.5 GB");

    expect(formatSpeed(null)).toBe("—");
    expect(formatSpeed(1024 * 1024)).toBe("1.0 MB/s");

    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(30)).toBe("less than a minute");
    expect(formatDuration(120)).toBe("about 2 minutes");
    expect(formatDuration(7200)).toBe("about 2 hours");
  });

  it("does not render Infinity as a duration", () => {
    expect(formatDuration(Number.POSITIVE_INFINITY)).toBe("—");
  });
});
