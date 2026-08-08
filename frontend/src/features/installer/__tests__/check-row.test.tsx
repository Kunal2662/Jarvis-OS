import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { CheckRow } from "@/features/installer/check-row";

/**
 * `CheckRow` -- extracted from `installer-steps.tsx`'s `SummaryStep` in
 * M22 Task Group D so the nine post-install checks and six dependency
 * findings did not each get their own copy of the same row. These tests
 * are what makes that extraction safe to have made without a defect to
 * justify it: `installer-wizard.test.tsx` and `installer-contract.test.ts`
 * cover `SummaryStep`'s continued use of it unchanged; these cover the
 * component itself, including the states `SummaryStep` alone never
 * exercised (`fail`, and the `action` slot no pre-flight check used).
 */

describe("CheckRow", () => {
  it("renders the label and detail", () => {
    render(<CheckRow label="Disk space" verdict="pass" detail="154.5 GB free." />);

    expect(screen.getByText("Disk space")).toBeInTheDocument();
    expect(screen.getByText("154.5 GB free.")).toBeInTheDocument();
  });

  it.each<["pass" | "warn" | "fail", string]>([
    ["pass", "pass"],
    ["warn", "warn"],
    ["fail", "fail"],
  ])("carries an accessible label for the %s verdict, not colour alone", (verdict, label) => {
    render(<CheckRow label="Permissions" verdict={verdict} detail="…" />);

    expect(screen.getByLabelText(label)).toBeInTheDocument();
  });

  it("renders no action by default", () => {
    render(<CheckRow label="Version" verdict="warn" detail="…" />);

    expect(screen.queryByRole("button")).toBeNull();
  });

  it("renders an injected action after the detail text", () => {
    render(
      <CheckRow
        label="Application folders"
        verdict="fail"
        detail="9 folder(s) missing."
        action={<button type="button">Repair</button>}
      />,
    );

    expect(screen.getByRole("button", { name: "Repair" })).toBeInTheDocument();
  });
});
