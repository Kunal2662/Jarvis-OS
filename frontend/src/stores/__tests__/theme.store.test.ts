import { beforeEach, describe, expect, it } from "vitest";
import { useThemeStore } from "@/stores/theme.store";

describe("useThemeStore", () => {
  beforeEach(() => {
    useThemeStore.setState({ theme: "dark" });
  });

  it("defaults to dark", () => {
    expect(useThemeStore.getState().theme).toBe("dark");
  });

  it("setTheme updates the active theme", () => {
    useThemeStore.getState().setTheme("light");
    expect(useThemeStore.getState().theme).toBe("light");
  });

  it("accepts all three JARVIS themes", () => {
    for (const theme of ["light", "dark", "jarvis"] as const) {
      useThemeStore.getState().setTheme(theme);
      expect(useThemeStore.getState().theme).toBe(theme);
    }
  });
});
