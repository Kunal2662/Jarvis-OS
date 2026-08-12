import { beforeEach, describe, expect, it } from "vitest";
import {
  atLeast,
  canReveal,
  progressPhraseFor,
  PROGRESS_PHRASES,
  RESTRICTED_INFORMATION,
  USER_MODES,
} from "@/core/user-mode";
import { useDeveloperModeStore } from "@/stores/developer-mode.store";
import {
  resetUserModeForTesting,
  resolveUserMode,
  setAdministrator,
} from "@/stores/user-mode.store";

/**
 * `ARCHITECTURE.md` §22.12 is a product rule with a security flavour:
 * a personal user's JARVIS does not contain provider names, routing or
 * internal agent names. These tests pin it as a checklist so a future
 * surface cannot quietly widen what "personal" may see.
 */

beforeEach(resetUserModeForTesting);

describe("mode ordering", () => {
  it("ranks personal below developer below administrator", () => {
    expect(atLeast("personal", "personal")).toBe(true);
    expect(atLeast("personal", "developer")).toBe(false);
    expect(atLeast("personal", "administrator")).toBe(false);
    expect(atLeast("developer", "personal")).toBe(true);
    expect(atLeast("developer", "administrator")).toBe(false);
    expect(atLeast("administrator", "developer")).toBe(true);
  });

  it("lists modes least- to most-privileged", () => {
    expect([...USER_MODES]).toEqual(["personal", "developer", "administrator"]);
  });
});

describe("§22.12 restrictions", () => {
  it("hides every restricted class from a personal user", () => {
    // The whole point: not one of them leaks. Asserted over the list so
    // adding a category without a rule fails here.
    for (const information of RESTRICTED_INFORMATION) {
      expect(canReveal("personal", information)).toBe(false);
    }
  });

  it("covers exactly the seven classes the decision names", () => {
    expect([...RESTRICTED_INFORMATION]).toEqual([
      "provider_names",
      "provider_routing",
      "internal_agents",
      "backend_execution",
      "api_names",
      "backend_services",
      "raw_debug",
    ]);
  });

  it("reveals everything to developer and administrator", () => {
    for (const information of RESTRICTED_INFORMATION) {
      expect(canReveal("developer", information)).toBe(true);
      expect(canReveal("administrator", information)).toBe(true);
    }
  });
});

describe("progress vocabulary", () => {
  it("is the wording the architecture decision fixes", () => {
    expect([...PROGRESS_PHRASES]).toEqual([
      "Working…",
      "Thinking…",
      "Preparing response…",
      "Checking information…",
      "Almost ready…",
    ]);
  });

  it("is deterministic for a given step", () => {
    // A phrase picked at random would change on every re-render, which
    // reads as flickering rather than progress.
    expect(progressPhraseFor(3)).toBe(progressPhraseFor(3));
  });

  it("advances with the step and wraps", () => {
    expect(progressPhraseFor(0)).toBe("Working…");
    expect(progressPhraseFor(1)).toBe("Thinking…");
    expect(progressPhraseFor(5)).toBe("Working…");
  });

  it("survives a negative step rather than indexing out of bounds", () => {
    expect(PROGRESS_PHRASES).toContain(progressPhraseFor(-2));
  });
});

describe("resolveUserMode", () => {
  it("is personal by default", () => {
    expect(resolveUserMode()).toBe("personal");
  });

  it("follows Developer Mode's existing session unlock", () => {
    useDeveloperModeStore.getState().unlock();
    expect(resolveUserMode()).toBe("developer");

    useDeveloperModeStore.getState().lock();
    expect(resolveUserMode()).toBe("personal");
  });

  it("administrator outranks developer", () => {
    setAdministrator(true);
    expect(resolveUserMode()).toBe("administrator");

    // Still administrator with developer mode locked -- the two are not
    // the same switch.
    useDeveloperModeStore.getState().lock();
    expect(resolveUserMode()).toBe("administrator");
  });

  it("derives from the existing store rather than a second copy", () => {
    // Two independent flags that can disagree about whether provider
    // names may be shown will eventually disagree permissively.
    useDeveloperModeStore.getState().unlock();
    expect(resolveUserMode()).toBe("developer");
    useDeveloperModeStore.setState({ isUnlocked: false });
    expect(resolveUserMode()).toBe("personal");
  });
});
