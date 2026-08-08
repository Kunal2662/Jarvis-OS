import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import dependenciesFixture from "./dependencies.personal.fixture.json";
import statusFreshFixture from "./status.fresh.fixture.json";
import statusResumableFixture from "./status.resumable.fixture.json";
import verifyFixture from "./verify.fixture.json";
import { DiagnosticsDialog } from "@/features/installer/installer-diagnostics";
import type {
  DependencyReport,
  InstallationStatus,
  VerificationReport,
} from "@/features/installer/provisioning-types";

/**
 * `DiagnosticsDialog` -- M22 Task Group D. All three fixtures involved
 * are real captured CLI output; `statusFreshFixture` in particular is
 * what makes the "nothing to verify yet" branch testable honestly --
 * it is the actual shape `status` returns for a location nobody has
 * installed to, not a guess at what that would look like.
 */
const fresh = statusFreshFixture as unknown as InstallationStatus;
const resumable = statusResumableFixture as unknown as InstallationStatus;
const dependencies = dependenciesFixture as unknown as DependencyReport;
const verification = verifyFixture as unknown as VerificationReport;

function renderDialog(overrides: Partial<React.ComponentProps<typeof DiagnosticsDialog>> = {}) {
  const props: React.ComponentProps<typeof DiagnosticsDialog> = {
    open: true,
    onOpenChange: vi.fn(),
    location: "C:/JARVIS",
    accountType: "personal",
    getStatus: vi.fn().mockResolvedValue(fresh),
    verify: vi.fn().mockResolvedValue(verification),
    checkDependencies: vi.fn().mockResolvedValue(dependencies),
    onRepair: null,
    onOpenLogFolder: null,
    ...overrides,
  };
  return { ...render(<DiagnosticsDialog {...props} />), props };
}

describe("DiagnosticsDialog", () => {
  it("does nothing while closed", () => {
    const getStatus = vi.fn().mockResolvedValue(fresh);
    renderDialog({ open: false, getStatus });

    expect(getStatus).not.toHaveBeenCalled();
  });

  it("shows a busy state while checking", () => {
    renderDialog({ getStatus: vi.fn(() => new Promise<InstallationStatus>(() => {})) });

    expect(screen.getByText("Checking…")).toBeInTheDocument();
  });

  it("reports no existing installation for a fresh location", async () => {
    renderDialog({ getStatus: vi.fn().mockResolvedValue(fresh) });

    expect(await screen.findByText("None found here")).toBeInTheDocument();
  });

  it("reports a partial installation and its journal progress", async () => {
    // `resumable` has journal entries but no manifest -- an install
    // interrupted before finishing, not a completed one, and the two
    // are worth telling apart rather than both reading as "Found".
    renderDialog({ getStatus: vi.fn().mockResolvedValue(resumable) });

    expect(await screen.findByText("Partially installed")).toBeInTheDocument();
    expect(screen.getByText("2 of 8")).toBeInTheDocument();
  });

  it("skips verification for a location with nothing installed", async () => {
    const verify = vi.fn();
    renderDialog({ getStatus: vi.fn().mockResolvedValue(fresh), verify });

    expect(await screen.findByText(/Nothing installed at this location yet/)).toBeInTheDocument();
    expect(verify).not.toHaveBeenCalled();
  });

  it("verifies once status shows something to check", async () => {
    const verify = vi.fn().mockResolvedValue(verification);
    renderDialog({ getStatus: vi.fn().mockResolvedValue(resumable), verify });

    await waitFor(() => expect(verify).toHaveBeenCalledWith({ location: "C:/JARVIS", accountType: "personal" }));
    expect(await screen.findByText("Installation health")).toBeInTheDocument();
    // 4 repairable failures in this fixture -- onRepair is null here,
    // so none of them should render a button.
    expect(screen.queryByRole("button", { name: /^Repair$/ })).toBeNull();
  });

  it("fetches dependencies alongside status", async () => {
    renderDialog({ getStatus: vi.fn().mockResolvedValue(fresh) });

    expect(await screen.findByText("This device")).toBeInTheDocument();
    expect(screen.getByText("Python runtime")).toBeInTheDocument();
  });

  it("skips dependencies and verification when no account type is chosen yet", async () => {
    const checkDependencies = vi.fn();
    const verify = vi.fn();
    renderDialog({
      accountType: null,
      getStatus: vi.fn().mockResolvedValue(resumable),
      checkDependencies,
      verify,
    });

    await screen.findByText("Partially installed");
    expect(checkDependencies).not.toHaveBeenCalled();
    expect(verify).not.toHaveBeenCalled();
  });

  it("shows a readable error rather than an empty dialog when status fails", async () => {
    renderDialog({ getStatus: vi.fn().mockRejectedValue(new Error("Target is unreadable")) });

    expect(await screen.findByText("Target is unreadable")).toBeInTheDocument();
  });

  it("repairs the clicked step and replaces the shown report with the fresh one returned", async () => {
    const user = userEvent.setup();
    const refreshedReport: VerificationReport = {
      healthy: true,
      results: verification.results.map((result) => ({ ...result, verdict: "pass", repairable: false })),
    };
    const onRepair = vi.fn().mockResolvedValue(refreshedReport);

    renderDialog({ getStatus: vi.fn().mockResolvedValue(resumable), onRepair });

    const configurationRow = (await screen.findByText("Configuration")).closest("li");
    if (!configurationRow) throw new Error("row not found");
    await user.click(within(configurationRow).getByRole("button", { name: /^Repair$/ }));

    expect(onRepair).toHaveBeenCalledWith("configuration");
    // The panel now reflects the fresh, healthy report -- not the stale
    // one the dialog fetched before the repair ran.
    await waitFor(() => {
      expect(screen.queryByRole("button", { name: /^Repair$/ })).toBeNull();
    });
  });

  it("offers Open log folder only when the host can", async () => {
    const onOpenLogFolder = vi.fn();
    renderDialog({ onOpenLogFolder });

    const button = await screen.findByRole("button", { name: /Open log folder/ });
    await userEvent.setup().click(button);

    expect(onOpenLogFolder).toHaveBeenCalledOnce();
  });

  it("hides Open log folder when the host cannot open one", async () => {
    renderDialog({ onOpenLogFolder: null });

    await screen.findByText("None found here");
    expect(screen.queryByRole("button", { name: /Open log folder/ })).toBeNull();
  });
});
