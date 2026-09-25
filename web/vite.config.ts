import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The bundle lands inside the Python package so `python -m my_agent_crew` serves it.
// Third-party code goes in chunks of its own: the server marks hashed assets immutable,
// so a release that only touches app code leaves the React and markdown chunks cached.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "../my_agent_crew/server/static",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes("/node_modules/")) return undefined;
          if (/\/(react|react-dom|scheduler)\//.test(id)) return "react";
          return "vendor";
        },
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
