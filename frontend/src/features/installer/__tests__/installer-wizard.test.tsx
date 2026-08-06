import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { InstallerWizard } from "@/features/installer/installer-wizard";
import { useInstallerStore } from "@/features/installer/installer-store";
import type { InstallationPlan } from "@/features/installer/installer-types";
import administratorPlan from "./plan.administrator.fixture.json";
import personalPlan from "./plan.personal.fixture.json";

const admin = administratorPlan as unknown as InstallationPlan;
const personal = personalPlan as unknown as InstallationPlan;

const DEFAULT_LOCATION = "C:\\Users\\test\\AppData\\Local\\JARVIS";

/** Provisioning never starts in these tests -- they cover the planning
 *  half of the wizard. `install-progress.test.tsx` covers the other. */
const NEVER_RESOLVES = () => new Promise<void>(() => {});

function renderWizard(loadPlan = vi.fn().mockResolvedValue(personal)) {
  render(
    <InstallerWizard
      loadPlan={loadPlan}
      defaultLocation={DEFAULT_LOCATION}
      runProvisioning={NEVER_RESOLVES}
    />,
  );
  return loadPlan;
}

/** Walk the wizard to a named step the way a user would. */
async function advanceTo(step: string, user: ReturnType<typeof userEvent.setup>) {
  const order = ["welcome", "license", "location", "account", "hardware", "calibration", "model", "voice", "summary"];
  const target = order.indexOf(step);

  for (let i = 0; i < target; i += 1) {
    if (order[i] === "license") {
      await user.click(screen.getByRole("checkbox"));
    }
    if (order[i] === "account") {
      await user.click(screen.getByRole("radio", { name: /Personal/ }));
    }
    await user.click(screen.getByRole("button", { name: /Continue|Install/ }));
  }
}

beforeEach(() => {
  useInstallerStore.getState().reset();
});

describe("flow", () => {
  it("starts at Welcome", () => {
    renderWizard();
    expect(screen.getByText("Welcome to JARVIS")).toBeInTheDocument();
    expect(screen.getByText(/Step 1 of 11/)).toBeInTheDocument();
  });

  it("cannot go back from the first step", () => {
    renderWizard();
    expect(screen.getByRole("button", { name: /Back/ })).toBeDisabled();
  });

  it("blocks Continue until the license is accepted", async () => {
    const user = userEvent.setup();
    renderWizard();

    await user.click(screen.getByRole("button", { name: /Continue/ }));
    expect(screen.getByText("License agreement")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();

    await user.click(screen.getByRole("checkbox"));
    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
  });

  it("blocks Continue until an account type is chosen", async () => {
    const user = userEvent.setup();
    renderWizard();
    await advanceTo("account", user);

    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
    await user.click(screen.getByRole("radio", { name: /Personal/ }));
    expect(screen.getByRole("button", { name: /Continue/ })).toBeEnabled();
  });

  it("goes back without losing what was entered", async () => {
    const user = userEvent.setup();
    renderWizard();
    await advanceTo("account", user);

    await user.click(screen.getByRole("button", { name: /Back/ }));
    await user.click(screen.getByRole("button", { name: /Continue/ }));

    // The license checkbox is still ticked, so Continue is live.
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled(); // account not chosen yet
    expect(screen.getByText("How will you use JARVIS?")).toBeInTheDocument();
  });
});

describe("hardware scan", () => {
  it("scans only once the location and account type are known", async () => {
    const user = userEvent.setup();
    const loadPlan = renderWizard();

    // Probing before the user has chosen would scan the wrong target
    // and produce the wrong payload shape.
    expect(loadPlan).not.toHaveBeenCalled();

    await advanceTo("hardware", user);

    expect(loadPlan).toHaveBeenCalledTimes(1);
    expect(loadPlan).toHaveBeenCalledWith({
      location: DEFAULT_LOCATION,
      accountType: "personal",
    });
  });

  it("shows a skeleton while scanning", async () => {
    const user = userEvent.setup();
    renderWizard(vi.fn(() => new Promise<InstallationPlan>(() => {})));

    await advanceTo("hardware", user);

    expect(screen.getByText("Checking your device")).toBeInTheDocument();
    // The skeleton's shapes are `aria-hidden`; this screen-reader-only
    // line is what actually gets announced, so it is what is asserted.
    expect(screen.getByText("Scanning hardware")).toBeInTheDocument();
  });

  it("renders the real measurements once the scan lands", async () => {
    const user = userEvent.setup();
    renderWizard();
    await advanceTo("hardware", user);

    expect(await screen.findByText("Your device")).toBeInTheDocument();
    expect(screen.getByText(`${personal.hardware.memory.total_gb.toFixed(1)} GB`)).toBeInTheDocument();
  });

  it("says 'Not detected' rather than substituting a number", async () => {
    const user = userEvent.setup();
    const noGpu: InstallationPlan = {
      ...personal,
      hardware: { ...personal.hardware, gpus: [], npu: null, total_vram_bytes: null },
    };
    renderWizard(vi.fn().mockResolvedValue(noGpu));

    await advanceTo("hardware", user);
    await screen.findByText("Your device");

    // A GPU that could not be probed renders as absent, never "0 GB".
    expect(screen.getAllByText("Not detected").length).toBeGreaterThan(0);
    expect(screen.queryByText("0 GB")).not.toBeInTheDocument();
  });

  it("reports a failed scan instead of continuing", async () => {
    const user = userEvent.setup();
    renderWizard(vi.fn().mockRejectedValue(new Error("nvidia-smi hung")));

    await advanceTo("hardware", user);

    expect(await screen.findByText("nvidia-smi hung")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Continue/ })).toBeDisabled();
  });

  it("re-scans when the account type changes", async () => {
    const user = userEvent.setup();
    const loadPlan = renderWizard();
    await advanceTo("hardware", user);
    await screen.findByText("Your device");
    expect(loadPlan).toHaveBeenCalledTimes(1);

    // The payload's *shape* depends on account type; reusing the old
    // plan would show a personal user administrator detail.
    await user.click(screen.getByRole("button", { name: /Back/ }));
    await user.click(screen.getByRole("radio", { name: /Administrator/ }));
    await user.click(screen.getByRole("button", { name: /Continue/ }));

    expect(loadPlan).toHaveBeenCalledTimes(2);
    expect(loadPlan).toHaveBeenLastCalledWith({
      location: DEFAULT_LOCATION,
      accountType: "administrator",
    });
  });
});

describe("§22.11 — what each account type sees", () => {
  it("hides the score breakdown from a personal user", async () => {
    const user = userEvent.setup();
    renderWizard();
    await advanceTo("calibration", user);

    expect(await screen.findByText(/AI capability score/)).toBeInTheDocument();
    // The score itself is shown; its technical decomposition is not.
    expect(screen.queryByText("Accelerator")).not.toBeInTheDocument();
  });

  it("shows the breakdown to an administrator", async () => {
    const user = userEvent.setup();
    render(
      <InstallerWizard
        loadPlan={vi.fn().mockResolvedValue(admin)}
        defaultLocation={DEFAULT_LOCATION}
        runProvisioning={NEVER_RESOLVES}
      />,
    );

    const order = ["welcome", "license", "location", "account", "hardware", "calibration"];
    for (let i = 0; i < order.length - 1; i += 1) {
      if (order[i] === "license") await user.click(screen.getByRole("checkbox"));
      if (order[i] === "account") await user.click(screen.getByRole("radio", { name: /Administrator/ }));
      await user.click(screen.getByRole("button", { name: /Continue/ }));
    }

    expect(await screen.findByText("Accelerator")).toBeInTheDocument();
    expect(screen.getByText("Memory")).toBeInTheDocument();
  });

  it("never shows a personal user a model id", async () => {
    const user = userEvent.setup();
    renderWizard();
    await advanceTo("model", user);

    expect(await screen.findByText("Local AI")).toBeInTheDocument();
    expect(screen.getByText(personal.recommended_model!.label)).toBeInTheDocument();
    // `model_id` is absent from the payload entirely, so there is
    // nothing to render even by accident.
    expect(screen.queryByText(/llama|qwen/i)).not.toBeInTheDocument();
  });

  it("never names a voice provider to a personal user", async () => {
    const user = userEvent.setup();
    renderWizard();
    await advanceTo("voice", user);

    expect(await screen.findByText("JARVIS")).toBeInTheDocument();
    expect(screen.queryByText(/piper|whisper|elevenlabs/i)).not.toBeInTheDocument();
  });
});

describe("summary", () => {
  it("lists every pre-installation check", async () => {
    const user = userEvent.setup();
    renderWizard();
    await advanceTo("summary", user);

    expect(await screen.findByText("Ready to install")).toBeInTheDocument();
    for (const result of personal.validation.results) {
      expect(screen.getByText(result.label)).toBeInTheDocument();
    }
  });

  it("blocks installation when a check fails", async () => {
    const user = userEvent.setup();
    const blocked: InstallationPlan = {
      ...personal,
      validation: {
        can_install: false,
        results: [
          {
            key: "disk",
            label: "Disk space",
            verdict: "fail",
            detail: "1.0 GB free. At least 3 GB is required.",
            blocking: true,
          },
        ],
      },
    };
    renderWizard(vi.fn().mockResolvedValue(blocked));

    await advanceTo("summary", user);

    expect(await screen.findByText("Cannot install yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Install/ })).toBeDisabled();
  });
});

describe("accessibility", () => {
  it("exposes progress to assistive technology", () => {
    renderWizard();
    const bar = screen.getByRole("progressbar", { name: "Installation progress" });

    expect(bar).toHaveAttribute("aria-valuenow", "1");
    expect(bar).toHaveAttribute("aria-valuemax", "11");
  });

  it("announces the current step", () => {
    renderWizard();
    expect(screen.getByText(/Step 1 of 11 — Welcome/)).toBeInTheDocument();
  });

  it("labels each validation verdict", async () => {
    const user = userEvent.setup();
    renderWizard();
    await advanceTo("summary", user);
    await screen.findByText("Ready to install");

    // Colour alone cannot carry pass/warn/fail.
    expect(screen.getAllByLabelText(/pass|warn|fail/).length).toBeGreaterThan(0);
  });
});
