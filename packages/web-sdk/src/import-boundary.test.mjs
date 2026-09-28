import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import assert from "node:assert/strict";

const root = join(dirname(fileURLToPath(import.meta.url)));
const forbidden = ["pipecat", "langgraph", "@pipecat"];

function walkTsFiles(dir) {
  const out = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walkTsFiles(path));
    else if (entry.name.endsWith(".ts")) out.push(path);
  }
  return out;
}

test("web-sdk sources avoid adapter framework tokens", () => {
  for (const file of walkTsFiles(root)) {
    const text = readFileSync(file, "utf8").toLowerCase();
    for (const token of forbidden) {
      assert.equal(text.includes(token), false, `${file} must not mention ${token}`);
    }
  }
});
