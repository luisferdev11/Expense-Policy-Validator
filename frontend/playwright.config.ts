import { tmpdir } from "node:os";
import { join } from "node:path";
import { defineConfig } from "@playwright/test";

// Smoke tests run against a throwaway backend: a fresh SQLite file (its answer table is seeded from
// the committed classifications), offline, untraced, no keys.
const stamp = Date.now();
const db = join(tmpdir(), `epv-e2e-${stamp}.sqlite3`);
const API_PORT = 8777;
const WEB_PORT = 5177;

export default defineConfig({
  testDir: "e2e",
  timeout: 45_000,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${WEB_PORT}`, trace: "retain-on-failure" },
  webServer: [
    {
      command: `uv run --directory .. epv serve --port ${API_PORT} --with-worker --offline --no-trace --db ${db}`,
      url: `http://localhost:${API_PORT}/health`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { EPV_API: `http://localhost:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
