import { fileURLToPath } from "node:url";
import { mergeConfig, defineConfig as defineViteConfig } from "vite";
import { defineConfig as defineVitestConfig } from "vitest/config";
import viteConfig from "./vite.config.ts";

/**
 * Testing foundation (Task 18) -- Vitest + React Testing Library. Kept as
 * a separate file (merged with vite.config.ts) rather than inlined there,
 * so `vite build`/`vite dev` never pull in Vitest's types.
 */
export default mergeConfig(
  defineViteConfig(viteConfig),
  defineVitestConfig({
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: [fileURLToPath(new URL("./src/test/setup.ts", import.meta.url))],
      css: true,
      exclude: ["node_modules", "dist", "src-tauri", "e2e"],
    },
  }),
);
