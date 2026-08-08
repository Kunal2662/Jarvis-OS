import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import rawStream from "./provision-stream.fixture.ndjson?raw";
import personalPlan from "./plan.personal.fixture.json";
import { CompletionStep } from "@/features/installer/completion-step";
import { InstallProgressStep } from "@/features/installer/install-progress-step";
import { InstallerWizard } from "@/features/installer/installer-wizard";
import { useInstallerStore } from "@/features/installer/installer-store";
import {
  setProvisioningClockForTesting,
  useProvisioningStore,
} from "@/features/installer/provisioning-store";
import type { InstallationPlan } from "@/features/installer/installer-types";
import type {
  DownloadItemState,
  ProgressEvent,
  ProvisioningEvent,
  ResultEvent,
} from "@/features/installer/provisioning-types";

const personal = personalPlan as unknown as InstallationPlan;

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

function download(state: DownloadItemState, name = "Local AI", kind: "model" | "voice" = "model") {
  return {
    name,
    kind,
    state,
    downloaded_bytes: 512,
    total_bytes: 1024,
    percent: 50,
    verified: state === "completed",
  };
}

beforeEach(() => {
  useProvisioningStore.getState().reset();
  useInstallerStore.getState().reset();
  setProvisioningClockForTesting(null);
});

describe("progress rendering", () => {
  it("shows the backend's phase, not a step id", () => {
    store().begin();
    store().ingest(progress({ label: "Downloading…", step: "model_download" }));

    render(<InstallProgressStep onRetry={vi.fn()} />);

    expect(screen.getByText("Downloading…")).toBeInTheDocument();
    expect(screen.queryByText(/model_download/)).not.toBeInTheDocument();
  });

  it("exposes overall progress to assistive technology", () => {
    store().begin();
    store().ingest(progress({ percent: 62.5 }));

    render(<InstallProgressStep onRetry={vi.fn()} />);

    const bar = screen.getByRole("progressbar", { name: "Installation progress" });
    expect(bar).toHaveAttribute("aria-valuenow", "63");
    expect(screen.getByText("63%")).toBeInTheDocument();
  });

  it("shows steps, bytes, speed and time remaining", () => {
    let now = 0;
    setProvisioningClockForTesting(() => now);
    store().begin();

    store().ingest(progress({ download: { ...download("running"), downloaded_bytes: 1000, total_bytes: 10_000 } }));
    now = 1000;
    store().ingest(progress({ download: { ...download("running"), downloaded_bytes: 3000, total_bytes: 10_000 } }));

    render(<InstallProgressStep onRetry={vi.fn()} />);

    expect(screen.getByText("3 of 8")).toBeInTheDocument();
    expect(screen.getByText(/2\.9 KB of 9\.8 KB/)).toBeInTheDocument();
    expect(screen.getByText(/KB\/s/)).toBeInTheDocument();
    expect(screen.getByText("less than a minute")).toBeInTheDocument();
  });

  it("says '—' rather than inventing a speed before one is known", () => {
    store().begin();
    store().ingest(progress({ download: download("running") }));

    render(<InstallProgressStep onRetry={vi.fn()} />);

    // "0 B/s" would read as stalled.
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("renders an indeterminate bar when the size is unknown", () => {
    store().begin();
    store().ingest(
      progress({
        download: { ...download("running"), total_bytes: null, percent: null },
      }),
    );

    render(<InstallProgressStep onRetry={vi.fn()} />);

    const bar = screen.getByRole("progressbar", { name: "Local AI download progress" });
    expect(bar).not.toHaveAttribute("aria-valuenow");
  });
});

describe("download view", () => {
  it("groups models and voices", () => {
    store().begin();
    store().ingest(progress({ download: download("running", "Local AI", "model") }));
    store().ingest(progress({ download: download("queued", "Local speech", "voice") }));

    render(<InstallProgressStep onRetry={vi.fn()} />);

    expect(screen.getByText("Models", { selector: "h3" })).toBeInTheDocument();
    expect(screen.getByText("Voices", { selector: "h3" })).toBeInTheDocument();
  });

  it.each<[DownloadItemState, string]>([
    ["queued", "Waiting"],
    ["running", "Downloading"],
    ["verifying", "Checking"],
    ["completed", "Ready"],
    ["skipped", "Already installed"],
    ["failed", "Failed"],
    ["cancelled", "Cancelled"],
  ])("shows %s as %j", (state, label) => {
    store().begin();
    store().ingest(progress({ download: download(state) }));

    render(<InstallProgressStep onRetry={vi.fn()} />);

    // Both the text and the icon's accessible label, so the state is
    // never carried by colour alone.
    expect(screen.getAllByText(label).length).toBeGreaterThan(0);
    expect(screen.getByLabelText(label)).toBeInTheDocument();
  });

  it("names items by their friendly label only", () => {
    store().begin();
    for (const event of REAL_EVENTS) store().ingest(event);

    render(<InstallProgressStep onRetry={vi.fn()} />);

    const rendered = document.body.textContent?.toLowerCase() ?? "";
    for (const leak of ["llama", "qwen", "piper", "whisper", "http", "c:\\"]) {
      expect(rendered, `rendered "${leak}"`).not.toContain(leak);
    }
  });
});

describe("resume UI", () => {
  it("says it is resuming when the backend reports a resumed run", () => {
    store().begin();
    store().ingest({
      event: "result",
      root: "C:/JARVIS",
      resumed: true,
      succeeded: false,
      completed_steps: [],
      skipped_steps: ["dependencies", "directories"],
      errors: ["voice_download: network unreachable"],
    } as ResultEvent);
    // Back to a running phase to render the progress view.
    useProvisioningStore.setState({ phase: "running", failure: null });

    render(<InstallProgressStep onRetry={vi.fn()} />);

    expect(screen.getByText("Resuming installation…")).toBeInTheDocument();
    expect(screen.getByText(/already completed is being skipped/i)).toBeInTheDocument();
  });

  it("does not claim to resume a fresh run", () => {
    store().begin();
    store().ingest(progress());

    render(<InstallProgressStep onRetry={vi.fn()} />);

    expect(screen.getByText("Setting up JARVIS")).toBeInTheDocument();
    expect(screen.queryByText("Resuming installation…")).not.toBeInTheDocument();
  });
});

describe("failure UI", () => {
  function failWith(message: string) {
    store().begin();
    store().ingest({
      event: "result",
      root: "C:/JARVIS",
      resumed: false,
      succeeded: false,
      completed_steps: ["dependencies"],
      skipped_steps: [],
      errors: [message],
    } as ResultEvent);
  }

  it.each([
    ["URLError: connection refused", "Connection lost"],
    ["Checksum did not match", "A download was damaged"],
    ["No space left on device", "Not enough space"],
    ["PermissionError: access is denied", "JARVIS can’t write here"],
    ["Required dependencies are missing: Git", "Something JARVIS needs is missing"],
    ["Cancelled. Progress kept for resume.", "Installation cancelled"],
    ["a thing nobody predicted", "Installation stopped"],
  ])("shows a friendly title for %j", (message, title) => {
    failWith(message);

    render(<InstallProgressStep onRetry={vi.fn()} />);

    expect(screen.getByText(title)).toBeInTheDocument();
    // The raw cause never reaches the screen.
    expect(screen.queryByText(message)).not.toBeInTheDocument();
  });

  it("offers a retry that continues rather than restarts", () => {
    const onRetry = vi.fn();
    failWith("network unreachable");

    render(<InstallProgressStep onRetry={onRetry} />);

    // Worded as continuing, because the journal makes it a resume.
    const button = screen.getByRole("button", { name: /Continue installation/ });
    return userEvent.setup().click(button).then(() => {
      expect(onRetry).toHaveBeenCalledOnce();
    });
  });

  it("keeps completed work visible so 'progress saved' is credible", () => {
    store().begin();
    store().ingest(progress({ download: download("completed") }));
    store().ingest({
      event: "result",
      root: "C:/JARVIS",
      resumed: false,
      succeeded: false,
      completed_steps: [],
      skipped_steps: [],
      errors: ["voice_download: network unreachable"],
    } as ResultEvent);

    render(<InstallProgressStep onRetry={vi.fn()} />);

    expect(screen.getByText("Local AI")).toBeInTheDocument();
    expect(screen.getByLabelText("Ready")).toBeInTheDocument();
  });
});

describe("completion UI", () => {
  function completeRun() {
    store().begin();
    store().ingest(progress({ download: download("completed") }));
    store().ingest({
      event: "result",
      root: "C:/JARVIS",
      resumed: false,
      succeeded: true,
      completed_steps: ["manifest"],
      skipped_steps: [],
      errors: [],
      verification: {
        healthy: true,
        results: [
          {
            key: "models",
            label: "Local AI",
            verdict: "warn",
            detail: "All present, but 1 could not be integrity-checked.",
            repairable: false,
            repair_step: null,
          },
        ],
      },
    } as ResultEvent);
  }

  it("confirms completion with the version and components", () => {
    completeRun();

    render(
      <CompletionStep
        plan={personal}
        version="0.34.0"
        onLaunch={vi.fn()}
        onOpenFolder={vi.fn()}
        onRepair={null}
      />,
    );

    expect(screen.getByText("Installation complete")).toBeInTheDocument();
    expect(screen.getByText("0.34.0")).toBeInTheDocument();
    // Appears twice on this screen now: once as an installed-component
    // pill, once as the verification panel's check label for the same
    // component (the fixture's `models` check is also labelled "Local
    // AI") -- both are real, both are correct, so this asserts there
    // are two rather than picking one and making the query ambiguous.
    expect(screen.getAllByText("Local AI").length).toBe(2);
  });

  it("surfaces a warning rather than implying everything was verified", () => {
    completeRun();

    render(<CompletionStep
        plan={personal}
        version="0.34.0"
        onLaunch={null}
        onOpenFolder={null}
        onRepair={null}
      />,
    );

    expect(screen.getByText(/could not be integrity-checked/)).toBeInTheDocument();
  });

  it("wires both actions", async () => {
    const user = userEvent.setup();
    const onLaunch = vi.fn();
    const onOpenFolder = vi.fn();
    completeRun();

    render(
      <CompletionStep
        plan={personal}
        version="0.34.0"
        onLaunch={onLaunch}
        onOpenFolder={onOpenFolder}
        onRepair={null}
      />,
    );

    await user.click(screen.getByRole("button", { name: /Launch JARVIS/ }));
    await user.click(screen.getByRole("button", { name: /Open installation folder/ }));

    expect(onLaunch).toHaveBeenCalledOnce();
    expect(onOpenFolder).toHaveBeenCalledOnce();
  });

  it("disables an action the host cannot perform, with a reason", () => {
    completeRun();

    render(<CompletionStep
        plan={personal}
        version="0.34.0"
        onLaunch={null}
        onOpenFolder={null}
        onRepair={null}
      />,
    );

    const launch = screen.getByRole("button", { name: /Launch JARVIS/ });
    expect(launch).toBeDisabled();
    expect(launch).toHaveAttribute("title", expect.stringContaining("desktop application"));
  });

  it("never shows an installation path", () => {
    completeRun();

    render(<CompletionStep
        plan={personal}
        version="0.34.0"
        onLaunch={vi.fn()}
        onOpenFolder={vi.fn()}
        onRepair={null}
      />,
    );

    expect(document.body.textContent).not.toContain("C:/JARVIS");
  });
});

describe("wizard integration", () => {
  /** Walk to the Install step the way a user would. */
  async function reachInstall(
    user: ReturnType<typeof userEvent.setup>,
    runProvisioning: InstallerWizardProps["runProvisioning"],
  ) {
    render(
      <InstallerWizard
        loadPlan={vi.fn().mockResolvedValue(personal)}
        defaultLocation="C:/JARVIS"
        runProvisioning={runProvisioning}
        version="0.34.0"
      />,
    );

    for (const step of ["welcome", "license", "location", "account", "hardware", "calibration", "model", "voice", "summary"]) {
      if (step === "license") await user.click(screen.getByRole("checkbox"));
      if (step === "account") await user.click(screen.getByRole("radio", { name: "Personal" }));
      if (step === "hardware") await screen.findByText("Your device");
      await user.click(screen.getByRole("button", { name: /Continue|Install/ }));
    }
  }

  type InstallerWizardProps = Parameters<typeof InstallerWizard>[0];

  it("starts provisioning on reaching the Install step", async () => {
    const user = userEvent.setup();
    const runProvisioning = vi.fn(() => new Promise<void>(() => {}));

    await reachInstall(user, runProvisioning);

    await waitFor(() => expect(runProvisioning).toHaveBeenCalledOnce());
    expect(runProvisioning).toHaveBeenCalledWith(
      expect.objectContaining({ location: "C:/JARVIS", accountType: "personal" }),
    );
  });

  it("renders the real stream end to end and advances to completion", async () => {
    const user = userEvent.setup();
    const runProvisioning = vi.fn(async ({ onEvent }: { onEvent: (e: ProvisioningEvent) => void }) => {
      for (const event of REAL_EVENTS) onEvent(event);
    });

    await reachInstall(user, runProvisioning);

    // Success advances by itself -- a finished progress screen with a
    // Continue button looks stalled.
    expect(await screen.findByText("Installation complete")).toBeInTheDocument();
    expect(screen.getByText("0.34.0")).toBeInTheDocument();
  });

  it("shows a friendly failure when the transport itself breaks", async () => {
    const user = userEvent.setup();
    const runProvisioning = vi.fn().mockRejectedValue(new Error("spawn ENOENT"));

    await reachInstall(user, runProvisioning);

    expect(await screen.findByText("Installation stopped")).toBeInTheDocument();
    expect(screen.queryByText(/ENOENT/)).not.toBeInTheDocument();
  });

  it("retrying calls the backend again rather than restarting the wizard", async () => {
    const user = userEvent.setup();
    const runProvisioning = vi
      .fn()
      .mockRejectedValueOnce(new Error("network unreachable"))
      .mockImplementation(async ({ onEvent }: { onEvent: (e: ProvisioningEvent) => void }) => {
        for (const event of REAL_EVENTS) onEvent(event);
      });

    await reachInstall(user, runProvisioning);
    await screen.findByText("Connection lost");

    await user.click(screen.getByRole("button", { name: /Continue installation/ }));

    expect(await screen.findByText("Installation complete")).toBeInTheDocument();
    expect(runProvisioning).toHaveBeenCalledTimes(2);
  });

  it("does not start a second run over one already in flight", async () => {
    const user = userEvent.setup();
    const runProvisioning = vi.fn(() => new Promise<void>(() => {}));

    await reachInstall(user, runProvisioning);
    await waitFor(() => expect(runProvisioning).toHaveBeenCalledOnce());

    // A re-render must not launch provisioning again.
    useProvisioningStore.setState({ percent: 50 });
    await waitFor(() => expect(runProvisioning).toHaveBeenCalledOnce());
  });
});

describe("cancelled installation", () => {
  it("is reported as cancelled, not as an error", async () => {
    store().begin();
    store().ingest(progress({ download: download("cancelled") }));
    store().ingest({
      event: "result",
      root: "C:/JARVIS",
      resumed: false,
      succeeded: false,
      completed_steps: [],
      skipped_steps: [],
      errors: ["model_download: Cancelled. Progress kept for resume."],
    } as ResultEvent);

    render(<InstallProgressStep onRetry={vi.fn()} />);

    expect(screen.getByText("Installation cancelled")).toBeInTheDocument();
    expect(screen.getByText(/pick up where you left off/i)).toBeInTheDocument();
    // Still offers a way forward.
    expect(screen.getByRole("button", { name: /Continue installation/ })).toBeEnabled();
  });

  it("shows the cancelled item's own state in the list", () => {
    store().begin();
    store().ingest(progress({ download: download("cancelled") }));

    render(<InstallProgressStep onRetry={vi.fn()} />);

    const list = screen.getByRole("list");
    expect(within(list).getByLabelText("Cancelled")).toBeInTheDocument();
  });

  /**
   * The control that reaches the host -- M22 Task Group C.
   *
   * Until TG-C the cancelled state was unreachable: the classifier, the
   * label and the icon all existed and nothing could ever trigger them.
   * These cover the wiring, not the state.
   */
  it("offers Cancel while running, and asks the host when pressed", async () => {
    const onCancel = vi.fn();
    store().begin();
    store().ingest(progress());

    render(<InstallProgressStep onRetry={vi.fn()} onCancel={onCancel} />);

    const button = screen.getByRole("button", { name: /Cancel installation/ });
    await userEvent.click(button);

    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("tells the user cancelling is safe, since the journal makes it so", () => {
    store().begin();
    store().ingest(progress());

    render(<InstallProgressStep onRetry={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByText(/continue later from where it stops/i)).toBeInTheDocument();
  });

  it("offers no Cancel control when the host cannot stop a run", () => {
    // A button that cannot act is worse than no button: it invites a
    // press that silently does nothing, on the one screen where the
    // user is already anxious about interrupting.
    store().begin();
    store().ingest(progress());

    render(<InstallProgressStep onRetry={vi.fn()} onCancel={null} />);

    expect(screen.queryByRole("button", { name: /Cancel installation/ })).toBeNull();
  });

  it("does not offer Cancel once the run has already failed", () => {
    store().begin();
    store().fail("Connection lost.");

    render(<InstallProgressStep onRetry={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.queryByRole("button", { name: /Cancel installation/ })).toBeNull();
  });
});
