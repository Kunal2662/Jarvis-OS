import { render } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { CommandPaletteProvider } from "@/providers/command-palette-provider";
import { useCommandPaletteStore } from "@/stores/command-palette.store";

describe("CommandPaletteProvider", () => {
  beforeEach(() => {
    useCommandPaletteStore.setState({ isOpen: false });
  });

  it("Ctrl+K toggles the palette open", () => {
    render(
      <CommandPaletteProvider>
        <div>content</div>
      </CommandPaletteProvider>,
    );

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));

    expect(useCommandPaletteStore.getState().isOpen).toBe(true);
  });

  it("Ctrl+Shift+P toggles the palette open", () => {
    render(
      <CommandPaletteProvider>
        <div>content</div>
      </CommandPaletteProvider>,
    );

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "p", ctrlKey: true, shiftKey: true }));

    expect(useCommandPaletteStore.getState().isOpen).toBe(true);
  });

  it("Ctrl+K again closes it (toggle, not open-only)", () => {
    render(
      <CommandPaletteProvider>
        <div>content</div>
      </CommandPaletteProvider>,
    );

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));

    expect(useCommandPaletteStore.getState().isOpen).toBe(false);
  });

  it("Ctrl+Shift+K (neither exact binding) does not toggle", () => {
    render(
      <CommandPaletteProvider>
        <div>content</div>
      </CommandPaletteProvider>,
    );

    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true, shiftKey: true }));

    expect(useCommandPaletteStore.getState().isOpen).toBe(false);
  });

  it("removes its keydown listener on unmount -- no leaked global listener", () => {
    const { unmount } = render(
      <CommandPaletteProvider>
        <div>content</div>
      </CommandPaletteProvider>,
    );

    unmount();
    window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", ctrlKey: true }));

    expect(useCommandPaletteStore.getState().isOpen).toBe(false);
  });
});
