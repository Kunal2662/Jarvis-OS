import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CommandPaletteLayer } from "@/components/layout/command-palette-layer";
import { applicationRegistry } from "@/core/application-registry";
import { registerNavigation } from "@/core/interfaces/navigation-interface";
import { TestApplication } from "@/core/test-utils/test-application";
import { useCommandPaletteStore } from "@/stores/command-palette.store";
import { useModuleEnablementStore } from "@/stores/module-enablement.store";
import { useStartupPreferencesStore } from "@/stores/startup-preferences.store";

interface TestModuleOptions {
  name: string;
  displayName: string;
  icon: string;
  routes: string[];
  isCore?: boolean;
}

function registerTestModule(options: TestModuleOptions): Promise<void> {
  return new TestApplication(options).initialize();
}

function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location">{location.pathname}</div>;
}

function renderPalette() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <CommandPaletteLayer />
      <Routes>
        <Route path="*" element={<LocationDisplay />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("CommandPaletteLayer", () => {
  const unregisterFns: Array<() => void> = [];

  beforeEach(async () => {
    for (const module of applicationRegistry.getAll()) {
      applicationRegistry.unregister(module.manifest.name);
    }
    for (const unregister of unregisterFns.splice(0)) unregister();
    useModuleEnablementStore.setState({ enabledModuleIds: [] });
    useCommandPaletteStore.setState({ isOpen: false });
    useStartupPreferencesStore.setState({ disableGlassEffects: false });

    await registerTestModule({ name: "home", displayName: "Dashboard", icon: "home", routes: ["/"], isCore: true });
    await registerTestModule({ name: "gmail", displayName: "Gmail", icon: "mail", routes: ["/gmail"] });
  });

  it("renders nothing visible while closed", () => {
    renderPalette();
    expect(screen.queryByPlaceholderText("Type a command or search...")).not.toBeInTheDocument();
  });

  it("lists only registered AND enabled modules under Navigate when open", () => {
    useCommandPaletteStore.setState({ isOpen: true });
    renderPalette();

    expect(screen.getByText("Dashboard")).toBeInTheDocument(); // core, always enabled
    expect(screen.queryByText("Gmail")).not.toBeInTheDocument(); // not enabled
  });

  it("shows an enabled non-core module", () => {
    useModuleEnablementStore.setState({ enabledModuleIds: ["gmail"] });
    useCommandPaletteStore.setState({ isOpen: true });
    renderPalette();

    expect(screen.getByText("Gmail")).toBeInTheDocument();
  });

  it("selecting a Navigate entry navigates there and closes the palette", async () => {
    useModuleEnablementStore.setState({ enabledModuleIds: ["gmail"] });
    useCommandPaletteStore.setState({ isOpen: true });
    renderPalette();

    await userEvent.click(screen.getByText("Gmail"));

    expect(screen.getByTestId("location")).toHaveTextContent("/gmail");
    expect(useCommandPaletteStore.getState().isOpen).toBe(false);
  });

  it("renders no Commands group when nothing contributes real command palette entries", () => {
    useCommandPaletteStore.setState({ isOpen: true });
    renderPalette();

    expect(screen.queryByText("Commands")).not.toBeInTheDocument();
  });

  it("renders and runs a real module-contributed command, then closes the palette", async () => {
    const action = vi.fn();
    unregisterFns.push(
      registerNavigation({
        moduleId: "gmail",
        sidebarVisible: false,
        dockEligible: false,
        commandPaletteEntries: [{ id: "gmail.compose", label: "Compose email", action }],
        searchable: false,
        keyboardShortcuts: [],
      }),
    );
    useCommandPaletteStore.setState({ isOpen: true });
    renderPalette();

    expect(screen.getByText("Commands")).toBeInTheDocument();
    await userEvent.click(screen.getByText("Compose email"));

    expect(action).toHaveBeenCalledOnce();
    expect(useCommandPaletteStore.getState().isOpen).toBe(false);
  });

  describe("glass surface (Task Group J)", () => {
    it("renders a translucent, blurred dialog by default", () => {
      useCommandPaletteStore.setState({ isOpen: true });
      renderPalette();

      const dialogContent = document.querySelector('[data-slot="dialog-content"]');
      expect(dialogContent).toHaveClass("bg-popover/70", "backdrop-blur-2xl");
    });

    it("falls back to a solid dialog when the real disableGlassEffects preference is set", () => {
      useStartupPreferencesStore.setState({ disableGlassEffects: true });
      useCommandPaletteStore.setState({ isOpen: true });
      renderPalette();

      const dialogContent = document.querySelector('[data-slot="dialog-content"]');
      expect(dialogContent).toHaveClass("bg-popover");
      expect(dialogContent).not.toHaveClass("backdrop-blur-2xl");
    });
  });
});
