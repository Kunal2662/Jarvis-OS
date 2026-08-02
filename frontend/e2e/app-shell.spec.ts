import { expect, test } from "@playwright/test";

/**
 * Foundation smoke test only (Task 18) -- proves the Playwright harness
 * itself works against a real running app. No application/module
 * behavior is tested here since no real module exists yet; a future
 * feature-module phase adds its own spec file under this directory.
 *
 * Updated for the UI Architecture Update's minimal default nav: only
 * the 7 core modules (Dashboard, AI's 3 children, Automation, Files,
 * Settings) render by default -- the other 7 (including Gmail) are
 * optional and disabled until a user enables them, so this suite picks
 * a core module (Automation) to exercise navigation instead.
 */
test.describe("App shell foundation", () => {
  test("loads, defaults to Dashboard, and shows the minimal core nav", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Dashboard", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Dashboard", exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );

    const nav = page.getByRole("navigation", { name: "Primary" });
    // 7 core links (Dashboard, Conversation, Voice, Memory, Automation,
    // Files, Settings) -- the "AI" group header is a button, not a
    // link, and no optional module is enabled by default.
    await expect(nav.getByRole("link")).toHaveCount(7);
  });

  test("navigating the sidebar updates the route and active state", async ({ page }) => {
    await page.goto("/");

    // `exact: true` -- the Dashboard's Quick Actions widget (Phase 3,
    // Task Group F) has its own "Open Automation" shortcut link, whose
    // accessible name contains "Automation" as a substring; Playwright's
    // default name matching is substring-based, so an unscoped, inexact
    // match here would ambiguously resolve to both links.
    await page.getByRole("link", { name: "Automation", exact: true }).click();

    await expect(page).toHaveURL(/\/automations$/);
    await expect(page.getByRole("heading", { name: "Automation", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Automation", exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(page.getByRole("link", { name: "Dashboard", exact: true })).not.toHaveAttribute(
      "aria-current",
      "page",
    );
  });

  test("an optional module (Gmail) is hidden until enabled", async ({ page }) => {
    await page.goto("/");

    const nav = page.getByRole("navigation", { name: "Primary" });
    await expect(nav.getByRole("link", { name: "Gmail" })).toHaveCount(0);
  });

  test("the status bar reports an honest, non-fake connection state", async ({ page }) => {
    await page.goto("/");

    // No backend WebSocket route exists yet (see services/websocket) --
    // this must never read "Connected". Scoped to the status bar's own
    // <footer> landmark: the Dashboard's System Status widget (Phase 3,
    // Task Group F) honestly reports the exact same real connection
    // state via the same shared label table
    // (`lib/connection-status-display.ts`), so an unscoped text lookup
    // for "Not connected" would be ambiguous on this page, not broken.
    await expect(page.locator("footer").getByText("Not connected")).toBeVisible();
  });
});
