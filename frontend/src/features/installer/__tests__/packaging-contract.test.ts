/// <reference types="node" />
//
// Touches Node builtins for the same reason `host-bridge-contract.test.ts`
// does (reading files as text/stat, not compiling anything) and needs
// the same file-scoped `<reference types="node" />` for the same
// reason -- see that file's own note on why this can't be a global
// `tsconfig.app.json` change.
import { existsSync, readFileSync, statSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/**
 * Packaging and branding asset contract -- M22 Task Group E.
 *
 * Reads repo files as text/stat rather than compiling or executing
 * anything, same discipline as `host-bridge-contract.test.ts`: no Rust
 * toolchain exists here, and `packaging/verify_tauri_build.ps1` shares
 * the same "known placeholder size" technique this file uses for the
 * icon check, kept deliberately consistent between the two rather than
 * inventing a second way to ask the same question.
 */

const srcTauri = (file: string) => resolve(process.cwd(), "src-tauri", file);
// Not `srcTauri(resolve("icons", file))`: `resolve()` treats a bare
// relative first segment as relative to `process.cwd()` and returns it
// fully resolved immediately, so the inner call alone already produces
// an *absolute* path -- passing that into `srcTauri`'s own `resolve()`
// then discards `process.cwd()` and "src-tauri" entirely, since `path
// .resolve()` drops everything before the last absolute argument it is
// given. Confirmed by running this test before fixing it: every path
// it built was missing the `src-tauri` segment. One `resolve()` call
// with every segment as its own argument avoids the nesting bug.
const iconsDir = (file: string) => resolve(process.cwd(), "src-tauri", "icons", file);

describe("tauri.conf.json bundle icon references", () => {
  const conf = JSON.parse(readFileSync(srcTauri("tauri.conf.json"), "utf8")) as {
    bundle: { icon: string[] };
  };

  it("references exactly the four icon files Task Group C established", () => {
    // Unchanged by Task Group E: new *content* went into the same four
    // files, not new paths -- `tauri.conf.json` needed no edit for the
    // icon swap, which is itself evidence the file paths are stable.
    expect(conf.bundle.icon).toEqual([
      "icons/32x32.png",
      "icons/128x128.png",
      "icons/128x128@2x.png",
      "icons/icon.ico",
    ]);
  });

  it("every referenced icon file exists on disk", () => {
    for (const relative of conf.bundle.icon) {
      expect(existsSync(srcTauri(relative)), `${relative} does not exist`).toBe(true);
    }
  });
});

describe("application icon is not Tauri's placeholder", () => {
  // Tauri's placeholder `icon.ico` was exactly 37,710 bytes in this
  // project's own git history before Task Group E replaced it -- a
  // negative match against that known value, not a magnitude
  // heuristic ("small enough to be real"). That heuristic was tried
  // first here too and broke immediately: Task Group E's real icon.ico
  // is a *hybrid* multi-resolution file (small frames from a
  // simplified variant, large frames from the approved master logo)
  // that ended up larger than the placeholder it replaced, not
  // smaller. The placeholder's own size is the one number guaranteed
  // not to change as this project's real artwork does.
  const PLACEHOLDER_ICO_SIZE = 37710;
  const PLACEHOLDER_32_SIZE = 2225;

  it("icon.ico does not match the placeholder's exact size", () => {
    const size = statSync(iconsDir("icon.ico")).size;
    expect(size).not.toBe(PLACEHOLDER_ICO_SIZE);
  });

  it("32x32.png does not match the placeholder's exact size", () => {
    const size = statSync(iconsDir("32x32.png")).size;
    expect(size).not.toBe(PLACEHOLDER_32_SIZE);
  });

  it("icon.ico is a well-formed multi-resolution ICO with the small-icon variant's frames present", () => {
    // Structural check on the binary format itself: reserved=0,
    // type=1 (icon), and at least the four small sizes Variant B was
    // built for are present in the directory. This is the same
    // ICONDIR/ICONDIRENTRY layout `packaging/verify_tauri_build.ps1`'s
    // build step wrote and this test reads back independently.
    const data = readFileSync(iconsDir("icon.ico"));
    const reserved = data.readUInt16LE(0);
    const type = data.readUInt16LE(2);
    const count = data.readUInt16LE(4);
    expect(reserved).toBe(0);
    expect(type).toBe(1);
    expect(count).toBeGreaterThanOrEqual(4);

    const sizes: number[] = [];
    for (let i = 0; i < count; i++) {
      const entryOffset = 6 + i * 16;
      const w = data[entryOffset];
      sizes.push(w === 0 ? 256 : w);
    }
    for (const expected of [16, 24, 32, 48]) {
      expect(sizes, `expected a ${expected}px frame in icon.ico`).toContain(expected);
    }
  });
});

describe("master logo and small-icon variant sources", () => {
  it("the master logo exists and is a square PNG", () => {
    const path = iconsDir("master-logo.png");
    expect(existsSync(path)).toBe(true);
    const data = readFileSync(path);
    expect(data.subarray(0, 8).toString("hex")).toBe("89504e470d0a1a0a");
    const width = data.readUInt32BE(16);
    const height = data.readUInt32BE(20);
    expect(width).toBe(height);
    expect(width).toBeGreaterThanOrEqual(1024);
  });

  it("the small-icon source SVG exists and uses the jarvis theme's real accent colour", () => {
    const svgPath = iconsDir("small-icon-source.svg");
    expect(existsSync(svgPath)).toBe(true);
    const svg = readFileSync(svgPath, "utf8");

    // Cross-referenced against the theme file rather than hard-coded
    // twice: the two are meant to be the same value, and a contract
    // test should catch it if they ever drift apart, not just assert
    // its own copy of the constant.
    const themes = readFileSync(resolve(process.cwd(), "src/styles/themes.css"), "utf8");
    const jarvisBlock = themes.slice(themes.indexOf('[data-theme="jarvis"]'));
    const accentMatch = /--accent:\s*(#[0-9a-fA-F]{6})/.exec(jarvisBlock);
    expect(accentMatch, "could not find --accent in the jarvis theme block").not.toBeNull();

    expect(svg.toLowerCase()).toContain(accentMatch![1].toLowerCase());
  });

  it("small-icon-source.svg has no double hyphen inside its comment body", () => {
    // The specific, narrow parse failure Task Group E found the hard
    // way: Tauri's icon generator panics on a double hyphen inside an
    // SVG comment (XML forbids it; this parser enforces it strictly).
    // A regression here would silently break `npx tauri icon` for
    // whoever next regenerates this file, with a confusing panic
    // rather than a normal error message.
    const svg = readFileSync(iconsDir("small-icon-source.svg"), "utf8");
    const commentBody = svg.slice(svg.indexOf("<!--") + 4, svg.indexOf("-->"));
    expect(commentBody).not.toContain("--");
  });
});

describe("favicon", () => {
  it("no longer contains the old placeholder's colour", () => {
    const favicon = readFileSync(resolve(process.cwd(), "public/favicon.svg"), "utf8");
    expect(favicon.toLowerCase()).not.toContain("#863bff");
  });

  it("uses the jarvis theme's real accent colour", () => {
    const favicon = readFileSync(resolve(process.cwd(), "public/favicon.svg"), "utf8");
    expect(favicon.toLowerCase()).toContain("#00e5ff");
  });

  it("index.html still references it at the same path", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");
    expect(html).toContain('href="/favicon.svg"');
  });
});
