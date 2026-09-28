import process from "node:process";
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
  // `npm run dev` talks to a server on its default port. The e2e suite sets API_ORIGIN to a port
  // nothing listens on, so a request a spec forgot to mock fails there rather than reaching
  // the crew that may be running on this machine.
  server: { proxy: { "/api": process.env.API_ORIGIN ?? "http://127.0.0.1:8765" } },
  test: {
    // The owner's calendar, so day boundaries test the same on a laptop here and on CI (UTC).
    env: { TZ: "Asia/Ho_Chi_Minh" },
    environment: "jsdom",
    setupFiles: ["./src/test-setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    exclude: ["e2e/**", "node_modules/**"],
  },
});
