import { spawnSync } from "node:child_process";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

// src/api/generated.ts is written from docs/api/openapi.json by `npm run gen:api` and committed.
// This test runs the generator's own `--check` mode, which regenerates in memory with the same
// options as the script and exits non-zero when the committed file differs (or is missing), so a
// backend change that was not followed by `npm run gen:api` fails here.
const frontend = resolve(__dirname, "../..");

describe("generated API types", () => {
  it("src/api/generated.ts matches docs/api/openapi.json", () => {
    const cli = resolve(frontend, "node_modules/openapi-typescript/bin/cli.js");
    const run = spawnSync(
      process.execPath,
      [cli, "../docs/api/openapi.json", "-o", "src/api/generated.ts", "--check"],
      { cwd: frontend, encoding: "utf8" },
    );
    const output = `${run.stdout ?? ""}${run.stderr ?? ""}`.trim();
    expect(
      run.status,
      `src/api/generated.ts is stale or missing. Run \`npm run gen:api\` in frontend/ and commit it.\n${output}`,
    ).toBe(0);
  });
});
