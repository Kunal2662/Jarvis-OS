import { afterEach, describe, expect, it, vi } from "vitest";
import {
  getAllCommandPaletteEntries,
  getSearchableModuleIds,
  registerNavigation,
  type NavigationContribution,
} from "@/core/interfaces/navigation-interface";

function contribution(overrides: Partial<NavigationContribution> = {}): NavigationContribution {
  return {
    moduleId: "test-module",
    sidebarVisible: false,
    dockEligible: false,
    commandPaletteEntries: [],
    searchable: false,
    keyboardShortcuts: [],
    ...overrides,
  };
}

describe("navigation-interface", () => {
  const unregisterFns: Array<() => void> = [];

  afterEach(() => {
    for (const unregister of unregisterFns.splice(0)) unregister();
  });

  it("registers a contribution whose command palette entries become visible", () => {
    const entry = { id: "gmail.search", label: "Search email", action: vi.fn() };
    unregisterFns.push(registerNavigation(contribution({ moduleId: "gmail", commandPaletteEntries: [entry] })));

    expect(getAllCommandPaletteEntries()).toContainEqual(entry);
  });

  it("aggregates command palette entries across multiple registered modules", () => {
    const gmailEntry = { id: "gmail.search", label: "Search email", action: vi.fn() };
    const filesEntry = { id: "files.open", label: "Open file", action: vi.fn() };
    unregisterFns.push(registerNavigation(contribution({ moduleId: "gmail", commandPaletteEntries: [gmailEntry] })));
    unregisterFns.push(registerNavigation(contribution({ moduleId: "files", commandPaletteEntries: [filesEntry] })));

    const entries = getAllCommandPaletteEntries();
    expect(entries).toContainEqual(gmailEntry);
    expect(entries).toContainEqual(filesEntry);
  });

  it("getSearchableModuleIds returns only modules that opted into search", () => {
    unregisterFns.push(registerNavigation(contribution({ moduleId: "memory", searchable: true })));
    unregisterFns.push(registerNavigation(contribution({ moduleId: "settings", searchable: false })));

    const searchable = getSearchableModuleIds();
    expect(searchable).toContain("memory");
    expect(searchable).not.toContain("settings");
  });

  it("the returned unregister function removes the contribution", () => {
    const entry = { id: "gmail.search", label: "Search email", action: vi.fn() };
    const unregister = registerNavigation(contribution({ moduleId: "gmail", commandPaletteEntries: [entry] }));

    unregister();

    expect(getAllCommandPaletteEntries()).not.toContainEqual(entry);
  });

  it("re-registering the same moduleId replaces the previous contribution rather than throwing", () => {
    const firstEntry = { id: "gmail.search-v1", label: "Old", action: vi.fn() };
    const secondEntry = { id: "gmail.search-v2", label: "New", action: vi.fn() };
    unregisterFns.push(registerNavigation(contribution({ moduleId: "gmail", commandPaletteEntries: [firstEntry] })));

    expect(() =>
      unregisterFns.push(
        registerNavigation(contribution({ moduleId: "gmail", commandPaletteEntries: [secondEntry] })),
      ),
    ).not.toThrow();

    const entries = getAllCommandPaletteEntries();
    expect(entries).toContainEqual(secondEntry);
    expect(entries).not.toContainEqual(firstEntry);
  });

  describe("keyboard shortcuts", () => {
    it("triggers the shortcut's action on a matching keydown", () => {
      const action = vi.fn();
      unregisterFns.push(
        registerNavigation(
          contribution({
            moduleId: "developer",
            keyboardShortcuts: [{ keys: "ctrl+shift+d", description: "Toggle Developer Mode", action }],
          }),
        ),
      );

      window.dispatchEvent(new KeyboardEvent("keydown", { key: "d", ctrlKey: true, shiftKey: true }));

      expect(action).toHaveBeenCalledOnce();
    });

    it("does not trigger the action when modifiers don't match", () => {
      const action = vi.fn();
      unregisterFns.push(
        registerNavigation(
          contribution({
            moduleId: "developer",
            keyboardShortcuts: [{ keys: "ctrl+shift+d", description: "Toggle Developer Mode", action }],
          }),
        ),
      );

      window.dispatchEvent(new KeyboardEvent("keydown", { key: "d", ctrlKey: true, shiftKey: false }));

      expect(action).not.toHaveBeenCalled();
    });

    it("removes its keydown listener on unregister -- no leaked global listener", () => {
      const action = vi.fn();
      const unregister = registerNavigation(
        contribution({
          moduleId: "developer",
          keyboardShortcuts: [{ keys: "ctrl+shift+d", description: "Toggle Developer Mode", action }],
        }),
      );

      unregister();
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "d", ctrlKey: true, shiftKey: true }));

      expect(action).not.toHaveBeenCalled();
    });
  });
});
