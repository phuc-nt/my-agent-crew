import process from "node:process";
import { defineConfig } from "@playwright/test";

// Every /api call is mocked inside the browser, so the dev server is enough. E2E_PORT lets
// two checkouts run the suite side by side: with a shared port the second run would reuse
// the first one's server and quietly test the other checkout's sources.
const port = Number(process.env.E2E_PORT ?? 4173);
const origin = `http://127.0.0.1:${port}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  // The owner's calendar, as in vite.config.ts, so day headers render the same on CI.
  use: { baseURL: origin, timezoneId: "Asia/Ho_Chi_Minh", trace: "retain-on-failure" },
  webServer: {
    command: `npx vite --host 127.0.0.1 --port ${port} --strictPort`,
    url: origin,
    // The discard port, which nothing serves: see vite.config.ts.
    env: { API_ORIGIN: "http://127.0.0.1:9" },
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
