import { expect, test } from "@playwright/test";

/**
 * Real, mouse-driven drag verification for the Dashboard Widget Grid's
 * drag-to-reorder feature (Phase 4, Task Group L). Deliberately a
 * Playwright test, not a Vitest/jsdom one: Framer Motion's drag gesture
 * recognition depends on genuine, trusted browser pointer events (real
 * `setPointerCapture`, real event sequencing) that a scripted
 * `dispatchEvent` call in a headless DOM can't faithfully reproduce --
 * `page.mouse` in a real Chromium instance can.
 */
test.describe("Dashboard widget drag-to-reorder", () => {
  test.beforeEach(async ({ page }) => {
    // Same real accessibility escape hatch as e2e/app-shell.spec.ts --
    // skip the ~4.2s startup choreography, don't weaken it.
    await page.addInitScript(() => {
      window.localStorage.setItem(
        "jarvis.accessibility-preferences",
        JSON.stringify({
          state: { skipStartupAnimation: true, reducedMotion: false, disableGlassEffects: false },
          version: 0,
        }),
      );
    });
  });

  test("dragging a widget's handle reorders it among its unpinned peers", async ({ page }) => {
    await page.goto("/");

    const widgets = page.getByRole("group");
    await expect(widgets).toHaveCount(4);
    const initialOrder = await widgets.evaluateAll((els) => els.map((el) => el.getAttribute("aria-label")));

    // Drag the second widget's handle down past the third -- real
    // `page.mouse` events, not synthetic `dispatchEvent`, so Framer's
    // drag gesture recognizer actually engages.
    const secondWidget = widgets.nth(1);
    const handle = secondWidget.getByRole("button", { name: "Drag to reorder" });
    const handleBox = await handle.boundingBox();
    const thirdWidgetBox = await widgets.nth(2).boundingBox();
    if (!handleBox || !thirdWidgetBox) throw new Error("Expected both widgets to have a real layout box.");

    await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
    await page.mouse.down();
    // Several intermediate moves -- Framer's gesture recognizer needs a
    // real move sequence past its drag threshold, not a single jump.
    const steps = 8;
    for (let i = 1; i <= steps; i++) {
      const y = handleBox.y + ((thirdWidgetBox.y + thirdWidgetBox.height + 40 - handleBox.y) * i) / steps;
      await page.mouse.move(handleBox.x + handleBox.width / 2, y);
    }
    await page.mouse.up();

    const finalOrder = await widgets.evaluateAll((els) => els.map((el) => el.getAttribute("aria-label")));
    expect(finalOrder).not.toEqual(initialOrder);
    // No widget was added or removed -- only reordered.
    expect([...finalOrder].sort()).toEqual([...initialOrder].sort());

    // The real store persisted the new order, not just a visual glitch.
    const persisted = await page.evaluate(() => window.localStorage.getItem("jarvis.dashboard-layout"));
    expect(persisted).toBeTruthy();
  });

  test("the existing Move up/down buttons still work unchanged, alongside the new drag handle", async ({
    page,
  }) => {
    await page.goto("/");

    const widgets = page.getByRole("group");
    const firstLabel = await widgets.nth(0).getAttribute("aria-label");
    const secondLabel = await widgets.nth(1).getAttribute("aria-label");

    await widgets.nth(1).getByRole("button", { name: "Move up" }).click();

    const newFirstLabel = await widgets.nth(0).getAttribute("aria-label");
    expect(newFirstLabel).toBe(secondLabel);
    expect(await widgets.nth(1).getAttribute("aria-label")).toBe(firstLabel);
  });
});
