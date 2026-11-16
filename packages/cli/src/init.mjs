// `relay init`: point the project's coding agents (Claude Code, Cursor, Codex, …) at the Relay SDK docs.
//
// The docs ship inside the installed SDK package, so they always match the installed version. Agents
// skip `node_modules` unless told, so this writes short pointers into the files each agent reads:
// a marked block in AGENTS.md and CLAUDE.md (replaced on every run, never duplicated) and a Cursor rule.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";

export const SDK_PACKAGE = "@sumukhj1219-wkt-org/relay-web-sdk";
const START = "<!-- relay:start (managed by `relay init`; edits inside this block are replaced) -->";
const START_PREFIX = "<!-- relay:start";
const END = "<!-- relay:end -->";

/** The installed SDK nearest to `dir` (walks up, for hoisted monorepo installs), or null. */
export function findSdk(dir) {
  let current = resolve(dir);
  for (;;) {
    const candidate = join(current, "node_modules", ...SDK_PACKAGE.split("/"));
    if (existsSync(join(candidate, "AGENTS.md"))) {
      let version = null;
      try {
        version = JSON.parse(readFileSync(join(candidate, "package.json"), "utf8")).version ?? null;
      } catch {
        // unreadable package.json: the docs are still there
      }
      return { path: candidate, version };
    }
    const parent = dirname(current);
    if (parent === current) return null;
    current = parent;
  }
}

/** Path of the SDK folder as written in the project's files: relative, with forward slashes. */
function sdkRef(dir, sdk) {
  const rel = sdk ? relative(dir, sdk.path) : join("node_modules", ...SDK_PACKAGE.split("/"));
  return rel.split(sep).join("/");
}

function instruction(ref) {
  return [
    "This app has a Relay assistant (voice + text AI that answers from the app's data and drives its UI).",
    `Before adding to or changing anything Relay-related (the assistant, its tools service, its agent manifest, \`${SDK_PACKAGE}\` code),`,
    "read these files from the installed SDK in full, and follow the required workflow in its AGENTS.md:",
    "",
    `- \`${ref}/AGENTS.md\` (the workflow and rules; it is only the index)`,
    `- \`${ref}/docs/02-backend.md\` (inventory, tools service, agent manifest)`,
    `- \`${ref}/docs/01-frontend.md\` (session, surfaces, forms, approvals, navigation and screen actions)`,
    `- \`${ref}/docs/03-reference.md\` (look-ups: events, surface specs, errors, endpoints)`,
    "",
    "Do not guess Relay APIs from memory; they are in those files and the package's type definitions.",
  ].join("\n");
}

/** Insert or replace the managed block in `text`. */
export function upsertBlock(text, body) {
  const block = `${START}\n${body}\n${END}`;
  const start = text.indexOf(START_PREFIX);
  const end = start === -1 ? -1 : text.indexOf(END, start);
  if (start !== -1 && end !== -1) {
    return text.slice(0, start) + block + text.slice(end + END.length);
  }
  if (!text.trim()) return `${block}\n`;
  return `${text.replace(/\s*$/, "")}\n\n${block}\n`;
}

function writeBlock(file, body) {
  const before = existsSync(file) ? readFileSync(file, "utf8") : null;
  const after = upsertBlock(before ?? "", body);
  if (after === before) return "unchanged";
  writeFileSync(file, after);
  return before === null ? "created" : before.includes(START_PREFIX) ? "updated" : "added to";
}

function writeOwned(file, content) {
  const before = existsSync(file) ? readFileSync(file, "utf8") : null;
  if (before === content) return "unchanged";
  mkdirSync(dirname(file), { recursive: true });
  writeFileSync(file, content);
  return before === null ? "created" : "updated";
}

export function init(flags, out, cwd = process.cwd()) {
  const dir = resolve(cwd, flags.dir ?? ".");
  if (!existsSync(dir)) throw new Error(`no such folder: ${dir}`);
  const sdk = findSdk(dir);
  const ref = sdkRef(dir, sdk);
  const text = instruction(ref);

  const results = [
    ["AGENTS.md", writeBlock(join(dir, "AGENTS.md"), text)],
    // Claude Code reads CLAUDE.md, not AGENTS.md; the @-import loads the SDK's index into its context.
    ["CLAUDE.md", writeBlock(join(dir, "CLAUDE.md"), `@${ref}/AGENTS.md\n\n${text}`)],
    [
      ".cursor/rules/relay.mdc",
      writeOwned(
        join(dir, ".cursor", "rules", "relay.mdc"),
        `---\ndescription: Relay assistant: read the SDK docs before working on it\nalwaysApply: true\n---\n\n${text}\n`,
      ),
    ],
  ];

  out.log(`Pointed this project's coding agents at the Relay SDK docs (${dir}):\n`);
  for (const [name, result] of results) out.log(`  ${result.padEnd(9)} ${name}`);
  if (sdk) {
    out.log(`\nDocs: ${ref}${sdk.version ? ` (SDK ${sdk.version})` : ""}. They follow SDK upgrades; no need to run this again.`);
  } else {
    out.log(`\nThe SDK is not installed here yet; the pointers assume ${ref}. Install it:`);
    out.log(`  npm install ${SDK_PACKAGE}`);
  }
  out.log("\nNext: commit these files, then ask your coding agent to \"integrate Relay\".");
  return 0;
}
