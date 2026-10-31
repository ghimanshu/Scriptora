import { spawnSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
const url = process.env.OPENAPI_SCHEMA_URL;
if (!url)
  throw new Error(
    "Set OPENAPI_SCHEMA_URL to the backend's OpenAPI schema; no fabricated contract is generated.",
  );
const checking = process.argv.includes("--check");
const temporary = checking
  ? mkdtempSync(join(tmpdir(), "scriptora-contract-"))
  : null;
try {
  const destination = temporary
    ? join(temporary, "api.ts")
    : "src/types/api.generated.ts";
  const result = spawnSync(
    process.execPath,
    ["node_modules/openapi-typescript/bin/cli.js", url, "-o", destination],
    { stdio: "inherit" },
  );
  if (result.status !== 0) process.exitCode = result.status ?? 1;
  else if (
    checking &&
    readFileSync(destination, "utf8").replaceAll("\r\n", "\n") !==
      readFileSync("src/types/api.generated.ts", "utf8").replaceAll(
        "\r\n",
        "\n",
      )
  ) {
    console.error("API contract drift. Regenerate and reconcile UI contracts.");
    process.exitCode = 1;
  }
} finally {
  if (temporary) rmSync(temporary, { recursive: true });
}
