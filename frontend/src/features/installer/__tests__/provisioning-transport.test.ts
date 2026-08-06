import { afterEach, describe, expect, it, vi } from "vitest";
import {
  PROVISION_COMMAND,
  PROVISION_EVENT,
  isHostBridgeAvailable,
  parseEventLine,
  runProvisioningViaHost,
} from "@/features/installer/provisioning-transport";
import { classifyFailure } from "@/features/installer/provisioning-types";
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
