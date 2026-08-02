import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { Dock } from "@/components/layout/dock";
import { applicationRegistry } from "@/core/application-registry";
import { TestApplication } from "@/core/test-utils/test-application";
import { useDockStore } from "@/stores/dock.store";
import { useModuleEnablementStore } from "@/stores/module-enablement.store";
import { useWorkspaceStore } from "@/stores/workspace.store";

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

describe("Dock", () => {
  beforeEach(async () => {
    for (const module of applicationRegistry.getAll()) {
      applicationRegistry.unregister(module.manifest.name);
    }
    useDockStore.setState({ pinnedItemIds: [] });
    useModuleEnablementStore.setState({ enabledModuleIds: [] });
    useWorkspaceStore.setState({ activeModuleId: null });

    await registerTestModule({ name: "home", displayName: "Dashboard", icon: "home", routes: ["/"], isCore: true });
    await registerTestModule({ name: "gmail", displayName: "Gmail", icon: "mail", routes: ["/gmail"] });
    await registerTestModule({ name: "calendar", displayName: "Calendar", icon: "calendar", routes: ["/calendar"] });
  });

  it("renders nothing when nothing is pinned -- no fake/default data", () => {
    const { container } = render(
      <MemoryRouter>
        <Dock />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("renders a pinned, enabled module", () => {
    useDockStore.setState({ pinnedItemIds: ["gmail"] });
    useModuleEnablementStore.setState({ enabledModuleIds: ["gmail"] });

    render(
      <MemoryRouter>
        <Dock />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Gmail" })).toBeInTheDocument();
  });

  it("hides a pinned module that is not enabled -- pinning doesn't override enablement", () => {
    useDockStore.setState({ pinnedItemIds: ["gmail"] });
    // Deliberately not enabled.

    const { container } = render(
      <MemoryRouter>
        <Dock />
      </MemoryRouter>,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("always shows a pinned core module regardless of the enablement store", () => {
    useDockStore.setState({ pinnedItemIds: ["home"] });

    render(
      <MemoryRouter>
        <Dock />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Dashboard" })).toBeInTheDocument();
  });

  it("ignores a pinned id that isn't registered -- no crash on stale pin data", () => {
    useDockStore.setState({ pinnedItemIds: ["never-registered"] });

    const { container } = render(
      <MemoryRouter>
        <Dock />
      </MemoryRouter>,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("highlights the module WorkspaceManager reports active, never derived from the route", () => {
    useDockStore.setState({ pinnedItemIds: ["gmail", "calendar"] });
    useModuleEnablementStore.setState({ enabledModuleIds: ["gmail", "calendar"] });
    useWorkspaceStore.setState({ activeModuleId: "gmail" });

    render(
      <MemoryRouter initialEntries={["/calendar"]}>
        <Dock />
      </MemoryRouter>,
    );

    expect(screen.getByRole("link", { name: "Gmail" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Calendar" })).not.toHaveAttribute("aria-current");
  });

  it("has an accessible landmark label", () => {
    useDockStore.setState({ pinnedItemIds: ["gmail"] });
    useModuleEnablementStore.setState({ enabledModuleIds: ["gmail"] });

    render(
      <MemoryRouter>
        <Dock />
      </MemoryRouter>,
    );

    expect(screen.getByLabelText("Pinned shortcuts")).toBeInTheDocument();
  });
});
