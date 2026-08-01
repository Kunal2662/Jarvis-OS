import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { applicationRegistry } from "@/core/application-registry";
import { TestApplication } from "@/core/test-utils/test-application";
import { workspaceManager } from "@/core/workspace-manager";
import { useWorkspaceSync } from "@/hooks/use-workspace-sync";

function Harness() {
  useWorkspaceSync();
  return null;
}

/**
 * Integration coverage for the React Router -> WorkspaceManager wire --
 * `core/__tests__/workspace-manager.test.ts` already covers the pure
 * mount/unmount logic in isolation; this file proves the hook actually
 * connects real route state to it.
 */
describe("useWorkspaceSync", () => {
  beforeEach(() => {
    for (const module of applicationRegistry.getAll()) {
      applicationRegistry.unregister(module.manifest.name);
    }
    workspaceManager.unmountActive();
  });

  it("mounts the module whose route matches the initial location", async () => {
    const app = new TestApplication({ name: "gmail", routes: ["/gmail"] });
    await app.initialize();

    render(
      <MemoryRouter initialEntries={["/gmail"]}>
        <Harness />
      </MemoryRouter>,
    );

    expect(app.calls).toContain("onMount");
  });

  it("unmounts the active module when the hook itself tears down -- no leaked mount", async () => {
    const app = new TestApplication({ name: "gmail", routes: ["/gmail"] });
    await app.initialize();

    const { unmount } = render(
      <MemoryRouter initialEntries={["/gmail"]}>
        <Harness />
      </MemoryRouter>,
    );
    unmount();

    expect(app.calls).toContain("onUnmount");
    expect(workspaceManager.activeModule).toBeNull();
  });
});
