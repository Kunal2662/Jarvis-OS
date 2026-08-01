import { expect, test } from "@playwright/test";

/**
 * Foundation smoke test only (Task 18) -- proves the Playwright harness
 * itself works against a real running app. No application/module
 * behavior is tested here since no real module exists yet; a future
 * feature-module phase adds its own spec file under this directory.
 */
test.describe("App shell foundation", () => {
  test("loads, defaults to Home, and shows the full nav rail", async ({ page }) => {
    await page.goto("/");

    await expect(page.getByRole("heading", { name: "Home", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Home", exact: true })).toHaveAttribute("aria-current", "page");

    const nav = page.getByRole("navigation", { name: "Primary" });
    await expect(nav.getByRole("link")).toHaveCount(14);
  });

  test("navigating the sidebar updates the route and active state", async ({ page }) => {
    await page.goto("/");

    await page.getByRole("link", { name: "Gmail" }).click();

    await expect(page).toHaveURL(/\/gmail$/);
    await expect(page.getByRole("heading", { name: "Gmail", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Gmail" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("link", { name: "Home", exact: true })).not.toHaveAttribute("aria-current", "page");
  });

  test("the status bar reports an honest, non-fake connection state", async ({ page }) => {
    await page.goto("/");

    // No backend WebSocket route exists yet (see services/websocket) --
    // this must never read "Connected".
    await expect(page.getByText("Not connected")).toBeVisible();
  });
});
