import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  // Tauri expects a fixed port and will fail if it is occupied.
  server: {
    port: 5173,
    strictPort: true,
  },
  // Tauri needs the built assets in `dist` (default) and benefits from
  // sourcemaps only in debug builds -- everything else uses Vite's own
  // sensible defaults.
  build: {
    outDir: "dist",
    sourcemap: !!process.env.TAURI_ENV_DEBUG,
    rollupOptions: {
      output: {
        // Performance foundation (Task 17): split large, slow-changing
        // vendor code into its own cacheable chunks instead of one
        // monolithic bundle -- a future feature-module PR then only
        // invalidates the small "app" chunk, not React/Radix/Motion too.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (/react-router|\/react\/|\/react-dom\//.test(id)) return "vendor-react";
          if (id.includes("@radix-ui")) return "vendor-radix";
          if (id.includes("@tanstack")) return "vendor-query";
          if (id.includes("/motion/") || id.includes("framer-motion")) return "vendor-motion";
          return "vendor";
        },
      },
    },
  },
});
