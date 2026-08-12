import { describe, expect, it } from "vitest";

/**
 * A source-level guard for `ARCHITECTURE.md` §22.12 -- M8 Phase 7.
 *
 * The other §22.12 tests check *behaviour*: given a personal user, this
 * component renders that. They cannot catch the failure that actually
 * worries me, which is a **new** surface added six months from now that
 * reads provider names and simply never gets a gate — no existing test
 * would fail, because no existing test knows about it.
 *
 * So this test scans the source instead: any module that imports a
 * restricted data source must also import the gate. It is a blunt
 * instrument and deliberately so — it cannot be satisfied by accident,
 * and its failure message says exactly what to do.
 *
 * The M8 Phase 3 leak (the Activity Center rendering `planner` /
 * `tool_executor` to everyone) is precisely the class of mistake this
 * catches, and it went unnoticed for a whole milestone without it.
 */

/**
 * Sources are read through Vite's `import.meta.glob` with `?raw` rather
 * than `node:fs`. Same result, but it stays inside the app's own
 * TypeScript project, which targets the browser and has no Node types —
 * a `node:fs` import here type-checks fine under vitest and fails
 * `npm run typecheck`, which is how this was caught.
 */
const MODULES = import.meta.glob("/src/**/*.{ts,tsx}", {
  query: "?raw",
  eager: true,
  import: "default",
}) as Record<string, string>;

/** Reading any of these means handling §22.12-restricted information:
 *  provider names, routing, internal agents, backend services, raw
 *  debug state. */
const RESTRICTED_SOURCES = [
  "selectProviders",
  "selectEgressStats",
  "mcpApi",
  "devtoolsApi",
  "auditApi",
] as const;

/** Importing any of these means the module consults the audience gate. */
const GATE_MARKERS = ["useHasMode", "useCanReveal", "atLeast(", "canReveal("] as const;

/** Modules that legitimately *name* the restricted sources without
 *  rendering them, each for a stated reason. */
const EXEMPT = new Set([
  // Declares the typed clients. A gate here would be a second gate that
  // could disagree with the real one; the rule is that *surfaces* gate.
  "services/api/endpoints.ts",
  // Declares the selectors and marks them restricted in its own doc
  // comments. Reading the store is not rendering it.
  "stores/health.store.ts",
  // This file.
  "core/__tests__/restricted-surface.test.ts",
]);

const FILES = Object.entries(MODULES).map(([path, text]) => ({
  // `/src/core/user-mode.ts` -> `core/user-mode.ts`
  path: path.replace(/^\/src\//, ""),
  text,
}));

describe("§22.12 restricted surfaces", () => {
  it("finds source files to scan at all", () => {
    // Guards the guard: a broken path would make every assertion below
    // pass vacuously, which is the worst possible failure for a test
    // whose whole job is catching omissions.
    expect(FILES.length).toBeGreaterThan(50);
    expect(FILES.some((file) => file.path === "core/user-mode.ts")).toBe(true);
  });

  it("every module reading restricted data also consults the gate", () => {
    const offenders = FILES.filter((file) => {
      if (EXEMPT.has(file.path)) return false;
      if (file.path.includes("__tests__")) return false;

      const reads = RESTRICTED_SOURCES.some((source) =>
        new RegExp(`\\b${source}\\b`).test(file.text),
      );
      if (!reads) return false;

      return !GATE_MARKERS.some((marker) => file.text.includes(marker));
    }).map((file) => file.path);

    expect(
      offenders,
      `These modules read §22.12-restricted data without consulting the audience gate.\n` +
        `Import useHasMode/useCanReveal from "@/stores/user-mode.store" and gate the surface,\n` +
        `or add the file to EXEMPT with a reason if it only declares rather than renders.\n` +
        `Offenders: ${offenders.join(", ")}`,
    ).toEqual([]);
  });

  it("the two dashboards gate at the mode they claim", () => {
    const developer = FILES.find((f) => f.path === "features/developer/developer-dashboard.tsx");
    const administrator = FILES.find((f) => f.path === "features/admin/administrator-dashboard.tsx");

    expect(developer?.text).toContain('useHasMode("developer")');
    expect(administrator?.text).toContain('useHasMode("administrator")');
    // An administrator dashboard gated only at "developer" would be a
    // silent privilege widening that reads fine in review.
    expect(administrator?.text).not.toContain('useHasMode("developer")');
  });

  it("no module renders an agent step's raw node field ungated", () => {
    // The exact M8 Phase 3 leak, pinned by name so it cannot come back.
    const offenders = FILES.filter((file) => {
      if (file.path.includes("__tests__")) return false;
      if (!/\.tsx$/.test(file.path)) return false;
      const usesNode = /\bstep\.node\b/.test(file.text);
      if (!usesNode) return false;
      return !GATE_MARKERS.some((marker) => file.text.includes(marker));
    }).map((file) => file.path);

    expect(offenders).toEqual([]);
  });
});
