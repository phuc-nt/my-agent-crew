import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// The bundle lands inside the Python package so `python -m my_agent_crew` serves it.
export default defineConfig({
  plugins: [react()],
  build: { outDir: "../my_agent_crew/server/static", emptyOutDir: true },
  server: { proxy: { "/api": "http://127.0.0.1:8765" } },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
