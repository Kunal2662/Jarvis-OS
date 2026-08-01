import { defineConfig, devices } from "@playwright/test";

/**
 * Testing foundation (Task 18) -- E2E config only, no application tests
 * yet (there are no real modules to exercise). `e2e/` holds the actual
 * spec files, kept separate from Vitest's `src/**` unit/component tests
 * (vitest.config.ts explicitly excludes this directory).
 */
export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: "list",
  use: {
    baseURL: "http://localhost:5173",
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: "npm run dev",
    url: "http://localhost:5173",
    reuseExistingServer: !process.env.CI,
    timeout: 30_000,
  },
});
