// The published package: what a customer's bundler resolves must exist and load as plain ESM.
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const pkg = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));

test("entry points exist in the build", () => {
  for (const file of [pkg.main, pkg.types, pkg.exports["."].import, pkg.exports["."].types]) {
    assert.ok(existsSync(join(root, file)), `${file} is missing — run the build`);
  }
});

test("built entry loads without a bundler and exposes the public API", async () => {
  const sdk = await import(join(root, pkg.main));
  for (const name of ["createRelaySession", "createSession", "registerPlaygroundSurfaces", "submitForm", "surfaceToCsv"]) {
    assert.equal(typeof sdk[name], "function", name);
  }
  // Built files reference each other with real file names (no extensionless or .ts imports).
  for (const file of [pkg.main, pkg.types]) {
    const text = readFileSync(join(root, file), "utf8");
    assert.match(text, /from "\.\/ui-surfaces\.js"/, file);
    assert.doesNotMatch(text, /from "\.\/[a-z-]+(\.ts)?"/, file);
  }
});

test("shipped docs are customer-facing: no repo paths, operator settings or example domains", async () => {
  const { readdirSync } = await import("node:fs");
  const files = ["README.md", "AGENTS.md", ...readdirSync(join(root, "docs")).map((f) => join("docs", f))];
  const forbidden = /examples\/|sales-crm|mortgage|\bCRM\b|infra\/|services\/gateway|relay_gateway|docker compose|(?<![A-Z_])RELAY_[A-Z_]{3,}/;
  for (const file of files) {
    readFileSync(join(root, file), "utf8").split("\n").forEach((line, index) => {
      assert.doesNotMatch(line, forbidden, `${file}:${index + 1}`);
    });
  }
});
