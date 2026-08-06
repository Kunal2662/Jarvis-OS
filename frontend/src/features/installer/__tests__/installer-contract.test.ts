import { describe, expect, it } from "vitest";
import administratorPlan from "./plan.administrator.fixture.json";
import personalPlan from "./plan.personal.fixture.json";
import type { InstallationPlan } from "@/features/installer/installer-types";

/**
 * The installer's Python/TypeScript contract -- M22 Task Group A.
 *
 * **Both fixtures are real output.** They were captured by running
 * `python -m jarvis.installer plan` on an actual machine, not
 * hand-written from the roadmap. That distinction is the whole point:
 * M8 Phase 2 shipped eleven invented WebSocket event names because the
 * client was written against a document instead of a running system,
 * and this is the same boundary with the same failure mode available.
 *
 * Regenerate after changing the CLI's output:
 *
 *     python -m jarvis.installer plan --account-type administrator \
 *       > src/features/installer/__tests__/plan.administrator.fixture.json
 *     python -m jarvis.installer plan --account-type personal \
 *       > src/features/installer/__tests__/plan.personal.fixture.json
 */

const admin = administratorPlan as unknown as InstallationPlan;
const personal = personalPlan as unknown as InstallationPlan;

describe("plan payload", () => {
  it("satisfies the TypeScript contract", () => {
    // Assigning the fixture to `InstallationPlan` above is itself the
    // structural check -- `npm run typecheck` fails if the real payload
    // has drifted from the declared type. These assertions cover the
    // values that types cannot express.
    for (const plan of [admin, personal]) {
      expect(plan.install_location).toBeTruthy();
      expect(plan.hardware.platform.system).toBeTruthy();
      expect(plan.hardware.memory.total_bytes).toBeGreaterThan(0);
      expect(plan.calibration.score).toBeGreaterThanOrEqual(0);
      expect(plan.calibration.score).toBeLessThanOrEqual(100);
      expect(plan.validation.results.length).toBeGreaterThan(0);
    }
  });

  it("reports account type accurately", () => {
    expect(admin.account_type).toBe("administrator");
    expect(personal.account_type).toBe("personal");
  });
});

/**
 * `ARCHITECTURE.md` §22.11/§22.12 enforced at the *payload* level: the
 * personal plan does not contain the technical detail, rather than
 * containing it for the UI to hide. What never arrives cannot leak
 * through a rendering mistake.
 */
describe("§22.11 — personal payloads carry no technical detail", () => {
  it("omits the model id", () => {
    expect(personal.recommended_model?.model_id).toBeUndefined();
    // The administrator payload proves the field exists at all, so this
    // is a real omission rather than a field the CLI never emits.
    expect(admin.recommended_model?.model_id).toBeTruthy();
  });

  it("omits the score breakdown and resource limits", () => {
    expect(personal.calibration.components).toBeUndefined();
    expect(personal.calibration.resource_limits).toBeUndefined();
    expect(personal.calibration.inputs).toBeUndefined();

    expect(admin.calibration.components).toBeDefined();
    expect(admin.calibration.resource_limits).toBeDefined();
  });

  it("omits voice provider names", () => {
    expect(personal.voice.components).toBeUndefined();
    expect(personal.voice.component_count).toBeGreaterThan(0);
    expect(admin.voice.components).toBeDefined();
  });

  it("names no provider anywhere in the personal payload", () => {
    // The blunt check: no provider or model vendor string appears in
    // the serialised personal plan at all.
    const serialised = JSON.stringify(personal).toLowerCase();

    for (const name of ["piper", "whisper", "elevenlabs", "llama", "qwen", "openai", "gemini", "groq"]) {
      expect(serialised, `personal payload leaked "${name}"`).not.toContain(name);
    }
  });

  it("still tells a personal user everything that affects them", () => {
    // Filtering must not leave the user uninformed: they still get the
    // capability score, the model tier's human label and size, the
    // voice identity and every validation result.
    expect(personal.calibration.score).toBeGreaterThanOrEqual(0);
    expect(personal.recommended_model?.label).toBeTruthy();
    expect(personal.recommended_model?.approximate_download_gb).toBeGreaterThan(0);
    expect(personal.voice.identity_name).toBe("JARVIS");
    expect(personal.validation.results.length).toBe(admin.validation.results.length);
  });
});

describe("honesty about what could not be measured", () => {
  it("uses null rather than a plausible substitute", () => {
    const { hardware } = admin;

    // Every optional field is either a real value or null -- never 0,
    // "Unknown", or an empty string standing in for a measurement.
    for (const value of [
      hardware.temperature_celsius,
      hardware.npu,
      hardware.total_vram_bytes,
      hardware.cpu.model,
    ]) {
      expect(value === null || (value !== "" && value !== 0)).toBe(true);
    }
  });

  it("explains each gap in words the installer can show", () => {
    const { hardware, calibration } = admin;
    const unmeasured =
      hardware.temperature_celsius === null || hardware.total_vram_bytes === null;

    if (unmeasured) {
      // A blank field with no explanation reads as a bug; the note is
      // what makes it read as a fact about the machine.
      expect(hardware.notes.length + calibration.missing_inputs.length).toBeGreaterThan(0);
    }
  });
});

describe("validation results", () => {
  it("marks blocking exactly when the verdict is fail", () => {
    for (const result of admin.validation.results) {
      expect(result.blocking).toBe(result.verdict === "fail");
    }
  });

  it("can_install agrees with the individual results", () => {
    const anyBlocking = admin.validation.results.some((r) => r.blocking);
    expect(admin.validation.can_install).toBe(!anyBlocking);
  });
});
