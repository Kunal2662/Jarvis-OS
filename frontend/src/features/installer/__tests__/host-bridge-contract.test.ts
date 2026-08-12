/// <reference types="node" />
//
// The only file under `src/` that touches Node built-ins -- reading
// `installer.rs` as text needs a filesystem, and this app otherwise
// targets the browser, so `tsconfig.app.json`'s `types` array does not
// include `node` globally. A file-scoped reference pulls in `@types/node`
// (already a devDependency) for this one file rather than widening the
// whole app's ambient types to add `process`/`Buffer`/etc. everywhere.
// Fixes a real gap this task group found: `tsc -b --noEmit` -- the
// project's actual `npm run typecheck` -- failed on this file before this
// line existed, which `vitest run` alone never caught, since vite-node
// resolves Node builtins at runtime independently of TypeScript's `types`
// option.
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import {
  CANCEL_COMMAND,
  DEPENDENCIES_COMMAND,
  OPEN_LOG_FOLDER_COMMAND,
  PROVISION_COMMAND,
  PROVISION_EVENT,
  REPAIR_COMMAND,
  STATUS_COMMAND,
  VERIFY_COMMAND,
} from "@/features/installer/provisioning-transport";

/**
 * The TypeScript/Rust contract -- M22 Task Group C.
 *
 * `provisioning-transport.ts` is the specification and
 * `src-tauri/src/installer.rs` satisfies it. Nothing enforced that:
 * the two halves agree only by having been written on the same day,
 * and a command renamed on one side fails at runtime, in a packaged
 * installer, on a user's machine — the least recoverable place a
 * name mismatch can surface.
 *
 * The Rust is read as **text** rather than compiled. That is a weaker
 * check than a real integration test and is chosen deliberately: it
 * needs no Rust toolchain, so it runs in the same `vitest` pass as
 * everything else and on machines that cannot build the desktop app.
 * It catches the failure that actually happens — a name changed on one
 * side only — which is worth more than nothing while the stronger
 * check is unavailable.
 *
 * Companion to `installer-contract.test.ts`, which does the same job
 * for the Python payload boundary.
 */

// Resolved from the vitest root (the `frontend` directory) rather than
// `import.meta.url`, which is not a file URL under this config.
const srcTauri = (file: string) => resolve(process.cwd(), "src-tauri/src", file);

const rust = readFileSync(srcTauri("installer.rs"), "utf8");

/** The commands the frontend invokes, and the arity it invokes them with. */
const INVOKED = [
  { name: PROVISION_COMMAND, takesArgs: true },
  { name: CANCEL_COMMAND, takesArgs: false },
  { name: "load_installation_plan", takesArgs: true },
  { name: "launch_application", takesArgs: false },
  { name: "open_installation_folder", takesArgs: false },
  // M22 Task Group D.
  { name: DEPENDENCIES_COMMAND, takesArgs: true },
  { name: STATUS_COMMAND, takesArgs: true },
  { name: VERIFY_COMMAND, takesArgs: true },
  { name: REPAIR_COMMAND, takesArgs: true },
  { name: OPEN_LOG_FOLDER_COMMAND, takesArgs: false },
] as const;

const declaration = (name: string) => new RegExp(`pub (?:async )?fn ${name}\\s*\\(`);

/** The parameter list of the `pub fn`/`pub async fn` with this name. */
function commandBody(name: string): string {
  const start = rust.search(declaration(name));
  expect(start, `installer.rs defines no command named ${name}`).toBeGreaterThan(-1);
  const open = rust.indexOf("(", start);
  const close = rust.indexOf(")", open);
  return rust.slice(open + 1, close);
}

/**
 * Split a Rust parameter list on top-level commas.
 *
 * A naive `split(",")` tears `State<'_, ProvisioningState>` in half and
 * reports a phantom parameter, so depth inside `<>` is tracked.
 */
function parameters(name: string): string[] {
  const body = commandBody(name);
  const parts: string[] = [];
  let depth = 0;
  let current = "";

  for (const character of body) {
    if (character === "<") depth += 1;
    else if (character === ">") depth -= 1;

    if (character === "," && depth === 0) {
      parts.push(current);
      current = "";
      continue;
    }
    current += character;
  }
  parts.push(current);

  return parts.map((part) => part.trim()).filter(Boolean);
}

describe("host bridge command names", () => {
  it.each(INVOKED.map((c) => c.name))("installer.rs defines %s", (name) => {
    expect(rust).toMatch(declaration(name));
  });

  it("registers every command it defines, so none is unreachable", () => {
    // A `#[tauri::command]` absent from `invoke_handler` compiles
    // cleanly and fails only when invoked.
    const lib = readFileSync(srcTauri("lib.rs"), "utf8");
    for (const { name } of INVOKED) {
      expect(lib, `${name} is not registered in invoke_handler`).toContain(`installer::${name}`);
    }
  });
});

describe("host bridge argument shapes", () => {
  /**
   * Tauri maps a camelCase key from JS onto a snake_case Rust
   * parameter, so `{ location, accountType }` reaches
   * `location: String, account_type: String`.
   */
  it("run_provisioning accepts the location and account type it is sent", () => {
    const body = commandBody(PROVISION_COMMAND);
    expect(body).toContain("location: String");
    expect(body).toContain("account_type: String");
  });

  it("load_installation_plan takes the same two", () => {
    const body = commandBody("load_installation_plan");
    expect(body).toContain("location: String");
    expect(body).toContain("account_type: String");
  });

  // --- M22 Task Group D ---------------------------------------------

  it("check_dependencies accepts location and account type", () => {
    const body = commandBody(DEPENDENCIES_COMMAND);
    expect(body).toContain("location: String");
    expect(body).toContain("account_type: String");
  });

  it("get_installation_status accepts location only -- status has no account-type flag in the CLI", () => {
    const body = commandBody(STATUS_COMMAND);
    expect(body).toContain("location: String");
    expect(body).not.toContain("account_type");
  });

  it("verify_installation accepts location and account type", () => {
    const body = commandBody(VERIFY_COMMAND);
    expect(body).toContain("location: String");
    expect(body).toContain("account_type: String");
  });

  /**
   * The one place this bridge's arity is easy to get wrong a second
   * time: `repair_installation` takes three arguments, and dropping any
   * one of them compiles (Rust does not know the CLI needs all three)
   * and fails only when a click reaches an unrepaired step or the wrong
   * target.
   */
  it("repair_installation accepts location, account type and the step to repair", () => {
    const body = commandBody(REPAIR_COMMAND);
    expect(body).toContain("location: String");
    expect(body).toContain("account_type: String");
    expect(body).toContain("step: String");
  });

  /**
   * The three no-argument commands.
   *
   * This is the check that earns the file's existence: the bridge was
   * first written with `launch_application(location: String)` while
   * every caller invoked it with no arguments at all. That is a clean
   * compile on both sides and a guaranteed runtime failure the moment
   * a user presses the button on the completion screen.
   *
   * `AppHandle` and `State` are injected by Tauri, not sent by the
   * caller, so they do not count as arguments here.
   */
  it.each(INVOKED.filter((c) => !c.takesArgs).map((c) => c.name))(
    "%s takes nothing the caller must supply",
    (name) => {
      const caller = parameters(name).filter(
        (part) => !/:\s*(AppHandle|State\s*<)/.test(part),
      );

      expect(caller, `${name} expects ${caller.join(", ")} but is invoked with no arguments`).toEqual([]);
    },
  );
});

describe("host bridge event name", () => {
  it("the Rust constant matches the name the frontend listens on", () => {
    expect(rust).toContain(`const PROVISION_EVENT: &str = "${PROVISION_EVENT}";`);
  });

  it("is the name Task Groups A and B documented", () => {
    // Pinned literally: the contract predates the bridge, and a rename
    // on both sides at once would still be a breaking change.
    expect(PROVISION_EVENT).toBe("provisioning://event");
  });
});
