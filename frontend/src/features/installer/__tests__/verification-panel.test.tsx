import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import verifyFixture from "./verify.fixture.json";
import { VerificationPanel } from "@/features/installer/verification-panel";
import type { VerificationReport } from "@/features/installer/provisioning-types";

/**
 * `VerificationPanel` -- M22 Task Group D. `verifyFixture` is real
 * output (`python -m jarvis.installer verify` against an empty target),
 * not hand-written: four of its nine checks are repairable failures
 * that all point at only two distinct repair steps
 * (`directories`, `configuration`), which is exactly the shape worth
 * testing against -- a hand-written fixture would have been tempted to
 * give every failure its own step.
 */
const report = verifyFixture as unknown as VerificationReport;

describe("VerificationPanel", () => {
  it("renders every check in the report", () => {
    render(<VerificationPanel report={report} onRepair={null} />);

    expect(screen.getAllByRole("listitem")).toHaveLength(9);
  });

  it("offers Repair only on repairable failures", () => {
    render(<VerificationPanel report={report} onRepair={vi.fn()} />);

    // 4 of 9 rows are repairable (directories, configuration, database,
    // memory_storage); the other 5 (permissions, disk, models, voice,
    // version) are not.
    expect(screen.getAllByRole("button", { name: /^Repair$/ })).toHaveLength(4);
  });

  it("offers no Repair action when the host cannot repair", () => {
    render(<VerificationPanel report={report} onRepair={null} />);

    expect(screen.queryByRole("button")).toBeNull();
  });

  it("repairs the specific step the clicked row names, not a fixed default", async () => {
    const user = userEvent.setup();
    const onRepair = vi.fn().mockResolvedValue(undefined);
    render(<VerificationPanel report={report} onRepair={onRepair} />);

    const configurationRow = screen.getByText("Configuration").closest("li");
    if (!configurationRow) throw new Error("row not found");
    await user.click(within(configurationRow).getByRole("button", { name: /^Repair$/ }));

    expect(onRepair).toHaveBeenCalledWith("configuration");
  });

  it("shows a busy state on the row being repaired and disables the others meanwhile", async () => {
    const user = userEvent.setup();
    let resolveRepair: () => void = () => {};
    const onRepair = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveRepair = resolve;
        }),
    );
    render(<VerificationPanel report={report} onRepair={onRepair} />);

    const directoriesRow = screen.getByText("Application folders").closest("li");
    if (!directoriesRow) throw new Error("row not found");
    await user.click(within(directoriesRow).getByRole("button", { name: /^Repair$/ }));

    // The clicked row now reads "Repairing…"; the other repairable rows
    // are disabled rather than independently clickable -- only one
    // repair runs at a time.
    expect(within(directoriesRow).getByRole("button", { name: /Repairing/ })).toBeDisabled();
    for (const button of screen.getAllByRole("button")) {
      expect(button).toBeDisabled();
    }

    resolveRepair();
    await waitFor(() => {
      expect(screen.getAllByRole("button", { name: /^Repair$/ }).length).toBeGreaterThan(0);
    });
  });
});
