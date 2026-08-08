import { afterEach, describe, expect, it, vi } from "vitest";
import dependenciesFixture from "./dependencies.personal.fixture.json";
import statusFixture from "./status.resumable.fixture.json";
import verifyFixture from "./verify.fixture.json";
import repairFixture from "./repair.fixture.json";
import repairUnknownStepFixture from "./repair.unknown-step.fixture.json";
import {
  DEPENDENCIES_COMMAND,
  OPEN_LOG_FOLDER_COMMAND,
  PROVISION_COMMAND,
  PROVISION_EVENT,
  REPAIR_COMMAND,
  STATUS_COMMAND,
  VERIFY_COMMAND,
  checkDependenciesViaHost,
  getInstallationStatusViaHost,
  isHostBridgeAvailable,
  openLogFolderViaHost,
  parseEventLine,
  repairInstallationViaHost,
  runProvisioningViaHost,
  verifyInstallationViaHost,
} from "@/features/installer/provisioning-transport";
import { classifyFailure, installationPresence } from "@/features/installer/provisioning-types";
import type { InstallationStatus } from "@/features/installer/provisioning-types";
import type { ProvisioningEvent } from "@/features/installer/provisioning-types";

/** A stand-in for Tauri's injected global. */
function installHost(options: {
  invoke?: (command: string, args?: unknown) => Promise<unknown>;
  emit?: (relay: (payload: unknown) => void) => void;
}) {
  let relay: ((payload: unknown) => void) | null = null;
  const unlisten = vi.fn();

  vi.stubGlobal("__TAURI__", {
    core: { invoke: options.invoke ?? vi.fn().mockResolvedValue(undefined) },
    event: {
      listen: vi.fn(async (_name: string, handler: (message: { payload: unknown }) => void) => {
        relay = (payload) => handler({ payload });
        options.emit?.(relay);
        return unlisten;
      }),
    },
  });

  return { unlisten, send: (payload: unknown) => relay?.(payload) };
}

afterEach(() => vi.unstubAllGlobals());

describe("host bridge detection", () => {
  it("is absent in a plain browser", () => {
    expect(isHostBridgeAvailable()).toBe(false);
  });

  it("is present when the host injects both halves", () => {
    installHost({});
    expect(isHostBridgeAvailable()).toBe(true);
  });

  it("is absent when the host injects only part of it", () => {
    // Half a bridge is not a bridge; treating it as one would fail
    // later and less clearly.
    vi.stubGlobal("__TAURI__", { core: { invoke: vi.fn() } });
    expect(isHostBridgeAvailable()).toBe(false);
  });
});

describe("without a host bridge", () => {
  it("rejects with a reason instead of hanging", async () => {
    // A stub that resolved quietly would leave the installer on
    // "Preparing…" forever, which is worse than a clear failure.
    await expect(
      runProvisioningViaHost({ location: "C:/JARVIS", accountType: "personal", onEvent: vi.fn() }),
    ).rejects.toThrow(/desktop application/i);
  });

  it("its message classifies into friendly copy with a retry", () => {
    const described = classifyFailure(
      "Installation needs the JARVIS desktop application. Open the installer from the desktop app to continue.",
    );

    expect(described.title).toBeTruthy();
    expect(described.retryable).toBe(true);
    // The user is never shown the raw sentence.
    expect(described.detail).not.toContain("__TAURI__");
  });
});

describe("with a host bridge", () => {
  it("invokes the agreed command with the user's choices", async () => {
    const invoke = vi.fn().mockResolvedValue(undefined);
    installHost({ invoke });

    await runProvisioningViaHost({
      location: "C:/JARVIS",
      accountType: "administrator",
      onEvent: vi.fn(),
    });

    expect(invoke).toHaveBeenCalledWith(PROVISION_COMMAND, {
      location: "C:/JARVIS",
      accountType: "administrator",
    });
  });

  it("relays events the host emits", async () => {
    const onEvent = vi.fn();
    const events: ProvisioningEvent[] = [
      {
        event: "progress",
        step: "dependencies",
        label: "Preparing…",
        completed_steps: 0,
        total_steps: 8,
        percent: 0,
      },
      {
        event: "result",
        root: "C:/JARVIS",
        resumed: false,
        succeeded: true,
        completed_steps: [],
        skipped_steps: [],
        errors: [],
      },
    ];

    installHost({
      emit: (relay) => {
        for (const event of events) relay(JSON.stringify(event));
      },
    });

    await runProvisioningViaHost({ location: "C:/J", accountType: "personal", onEvent });

    expect(onEvent).toHaveBeenCalledTimes(2);
    expect(onEvent).toHaveBeenLastCalledWith(expect.objectContaining({ event: "result" }));
  });

  it("accepts an already-parsed payload as well as a line", async () => {
    const onEvent = vi.fn();
    installHost({
      emit: (relay) =>
        relay({
          event: "progress",
          step: "manifest",
          label: "Finalizing…",
          completed_steps: 7,
          total_steps: 8,
          percent: 87.5,
        }),
    });

    await runProvisioningViaHost({ location: "C:/J", accountType: "personal", onEvent });

    expect(onEvent).toHaveBeenCalledOnce();
  });

  it("detaches the listener even when the run fails", async () => {
    // A listener surviving a failed run would deliver a later
    // installation's events into a dead screen.
    const { unlisten } = installHost({
      invoke: vi.fn().mockRejectedValue(new Error("spawn failed")),
    });

    await expect(
      runProvisioningViaHost({ location: "C:/J", accountType: "personal", onEvent: vi.fn() }),
    ).rejects.toThrow();

    expect(unlisten).toHaveBeenCalledOnce();
  });

  it("uses the agreed event name", () => {
    expect(PROVISION_EVENT).toBe("provisioning://event");
  });
});

describe("parseEventLine", () => {
  it("parses a progress and a result line", () => {
    expect(parseEventLine('{"event":"progress","percent":10}')?.event).toBe("progress");
    expect(parseEventLine('{"event":"result","succeeded":true}')?.event).toBe("result");
  });

  it("skips a malformed or partial line rather than throwing", () => {
    // Losing one progress update is recoverable; aborting an
    // installation over a truncated line is not.
    expect(parseEventLine('{"event":"prog')).toBeNull();
    expect(parseEventLine("")).toBeNull();
    expect(parseEventLine("   ")).toBeNull();
  });

  it("ignores a line that is valid JSON but not an event", () => {
    expect(parseEventLine('{"hello":"world"}')).toBeNull();
    expect(parseEventLine('{"event":"something-else"}')).toBeNull();
  });
});

/**
 * M22 Task Group D's five transport functions. Each is a thin
 * `invokeJson` call, so these tests focus on the two things that shape
 * matters for: the exact command name and argument shape sent, and
 * that the promise resolves to real captured data (the fixtures, not
 * hand-written stand-ins) rather than something reshaped along the way.
 */
describe("checkDependenciesViaHost", () => {
  it("invokes the agreed command with location and account type", async () => {
    const invoke = vi.fn().mockResolvedValue(dependenciesFixture);
    installHost({ invoke });

    await checkDependenciesViaHost({ location: "C:/JARVIS", accountType: "personal" });

    expect(invoke).toHaveBeenCalledWith(DEPENDENCIES_COMMAND, {
      location: "C:/JARVIS",
      accountType: "personal",
    });
  });

  it("resolves to the report the host returns", async () => {
    installHost({ invoke: vi.fn().mockResolvedValue(dependenciesFixture) });

    const report = await checkDependenciesViaHost({ location: "C:/JARVIS", accountType: "personal" });

    expect(report).toEqual(dependenciesFixture);
  });

  it("rejects with a reason when the bridge is absent", async () => {
    await expect(
      checkDependenciesViaHost({ location: "C:/JARVIS", accountType: "personal" }),
    ).rejects.toThrow(/desktop application/i);
  });
});

describe("getInstallationStatusViaHost", () => {
  it("invokes the agreed command with only a location", async () => {
    const invoke = vi.fn().mockResolvedValue(statusFixture);
    installHost({ invoke });

    await getInstallationStatusViaHost("C:/JARVIS");

    expect(invoke).toHaveBeenCalledWith(STATUS_COMMAND, { location: "C:/JARVIS" });
  });

  it("resolves to the status the host returns", async () => {
    installHost({ invoke: vi.fn().mockResolvedValue(statusFixture) });

    const status = await getInstallationStatusViaHost("C:/JARVIS");

    expect(status).toEqual(statusFixture);
  });

  it("rejects with a reason when the bridge is absent", async () => {
    await expect(getInstallationStatusViaHost("C:/JARVIS")).rejects.toThrow(/desktop application/i);
  });
});

describe("verifyInstallationViaHost", () => {
  it("invokes the agreed command with location and account type", async () => {
    const invoke = vi.fn().mockResolvedValue(verifyFixture);
    installHost({ invoke });

    await verifyInstallationViaHost({ location: "C:/JARVIS", accountType: "administrator" });

    expect(invoke).toHaveBeenCalledWith(VERIFY_COMMAND, {
      location: "C:/JARVIS",
      accountType: "administrator",
    });
  });

  it("resolves to the report the host returns", async () => {
    installHost({ invoke: vi.fn().mockResolvedValue(verifyFixture) });

    const report = await verifyInstallationViaHost({ location: "C:/JARVIS", accountType: "personal" });

    expect(report).toEqual(verifyFixture);
  });

  it("rejects with a reason when the bridge is absent", async () => {
    await expect(
      verifyInstallationViaHost({ location: "C:/JARVIS", accountType: "personal" }),
    ).rejects.toThrow(/desktop application/i);
  });
});

describe("repairInstallationViaHost", () => {
  it("invokes the agreed command with location, account type and step", async () => {
    const invoke = vi.fn().mockResolvedValue(repairFixture);
    installHost({ invoke });

    await repairInstallationViaHost({
      location: "C:/JARVIS",
      accountType: "personal",
      step: "directories",
    });

    expect(invoke).toHaveBeenCalledWith(REPAIR_COMMAND, {
      location: "C:/JARVIS",
      accountType: "personal",
      step: "directories",
    });
  });

  it("resolves to the result the host returns", async () => {
    installHost({ invoke: vi.fn().mockResolvedValue(repairFixture) });

    const result = await repairInstallationViaHost({
      location: "C:/JARVIS",
      accountType: "personal",
      step: "directories",
    });

    expect(result).toEqual(repairFixture);
  });

  it("rejects with a reason when the bridge is absent", async () => {
    await expect(
      repairInstallationViaHost({ location: "C:/JARVIS", accountType: "personal", step: "directories" }),
    ).rejects.toThrow(/desktop application/i);
  });

  /**
   * `repair_installation` never sends an unrecognised step in practice
   * -- every `step` this UI passes comes from a verification report's
   * own `repair_step`, which the backend only ever populates with a
   * real journal step key. Captured anyway (`repair bogus_step`, real
   * CLI output, exit code 2) because the host bridge's `run_json_command`
   * treats exit 2 as "a valid document", so this transport function
   * resolves rather than rejects for a target the CLI itself refused --
   * a caller reaching this path some other way gets back
   * `{ error: "…" }` verbatim rather than a thrown exception. Documented
   * here rather than defended against in code that no reachable caller
   * can trigger.
   */
  it("resolves, not rejects, when the host reports an unrecognised step", async () => {
    installHost({ invoke: vi.fn().mockResolvedValue(repairUnknownStepFixture) });

    const result = await repairInstallationViaHost({
      location: "C:/JARVIS",
      accountType: "personal",
      step: "bogus_step",
    });

    expect(result).toEqual(repairUnknownStepFixture);
  });
});

describe("openLogFolderViaHost", () => {
  it("invokes the agreed command", async () => {
    const invoke = vi.fn().mockResolvedValue(undefined);
    installHost({ invoke });

    await openLogFolderViaHost();

    expect(invoke).toHaveBeenCalledWith(OPEN_LOG_FOLDER_COMMAND);
  });

  it("resolves rather than rejects when the bridge is absent", async () => {
    // Same rule as `cancelProvisioningViaHost`: a convenience action on
    // a diagnostics screen should not itself become a second error.
    await expect(openLogFolderViaHost()).resolves.toBeUndefined();
  });

  it("resolves rather than rejects when the host call itself fails", async () => {
    installHost({ invoke: vi.fn().mockRejectedValue(new Error("Explorer is not available")) });

    await expect(openLogFolderViaHost()).resolves.toBeUndefined();
  });
});

/**
 * `installationPresence` -- a pure classification the installer wizard
 * and the diagnostics dialog both now call, added after they disagreed:
 * one checked `manifest || journal progress`, the other checked
 * `manifest` alone, so a partially-completed install read as "found" on
 * one screen and "none found" on the other for the same location. One
 * function, tested directly against its three branches (rather than
 * only indirectly through a fixture, since a real "complete" manifest
 * needs a full network-dependent provisioning run this environment
 * cannot produce).
 */
describe("installationPresence", () => {
  const baseJournal = {
    started_at: null,
    is_resume: false,
    completed: [] as InstallationStatus["journal"]["completed"],
    remaining: [] as InstallationStatus["journal"]["remaining"],
  };

  it("is 'none' when nothing has run and no manifest exists", () => {
    expect(installationPresence({ install_location: "C:/J", journal: baseJournal, manifest: false })).toBe(
      "none",
    );
  });

  it("is 'partial' when the journal has progress but no manifest yet", () => {
    const status: InstallationStatus = {
      install_location: "C:/J",
      journal: { ...baseJournal, completed: ["dependencies"] },
      manifest: false,
    };
    expect(installationPresence(status)).toBe("partial");
  });

  it("is 'complete' when a manifest exists, regardless of journal detail", () => {
    const status: InstallationStatus = {
      install_location: "C:/J",
      journal: baseJournal,
      manifest: true,
    };
    expect(installationPresence(status)).toBe("complete");
  });
});
