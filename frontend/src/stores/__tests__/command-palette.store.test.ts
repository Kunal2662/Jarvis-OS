import { beforeEach, describe, expect, it } from "vitest";
import { useCommandPaletteStore } from "@/stores/command-palette.store";

describe("useCommandPaletteStore", () => {
  beforeEach(() => {
    useCommandPaletteStore.setState({ isOpen: false });
  });

  it("starts closed", () => {
    expect(useCommandPaletteStore.getState().isOpen).toBe(false);
  });

  it("open() sets isOpen true", () => {
    useCommandPaletteStore.getState().open();
    expect(useCommandPaletteStore.getState().isOpen).toBe(true);
  });

  it("close() sets isOpen false", () => {
    useCommandPaletteStore.setState({ isOpen: true });
    useCommandPaletteStore.getState().close();
    expect(useCommandPaletteStore.getState().isOpen).toBe(false);
  });

  it("toggle() flips isOpen", () => {
    useCommandPaletteStore.getState().toggle();
    expect(useCommandPaletteStore.getState().isOpen).toBe(true);
    useCommandPaletteStore.getState().toggle();
    expect(useCommandPaletteStore.getState().isOpen).toBe(false);
  });
});
