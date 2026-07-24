#!/usr/bin/env node
/**
 * docs-aggregate.mjs — aggregate every composed block's `docs/fragment.md`
 * into the project root README's marker regions (Setup / Deployment /
 * Maintenance / Secrets).
 *
 * Canonical spec: references/authoring/documentation-standard.md,
 * "Aggregation markers (canonical spec)" and "Doc fragment format
 * (canonical spec)" in eblouin-plugins. This script implements exactly that
 * spec — it is not a second source of truth. Read the canon before editing
 * this file's matching/parsing logic.
 *
 * Plain Node, no dependencies beyond node:fs / node:path / node:url /
 * node:util. Runs under Node 24 (see the project's .nvmrc / engines).
 *
 * Usage:
 *   node scripts/docs-aggregate.mjs             # regenerate README.md in place
 *   node scripts/docs-aggregate.mjs --check      # exit 1 on drift, 0 if clean
 *   node scripts/docs-aggregate.mjs --root <dir> --readme <path>
 *     --root defaults to this script's parent directory (the project root
 *     when materialized at <project>/scripts/docs-aggregate.mjs); it is the
 *     directory expected to contain apps/, packages/, and infra/.
 *     --readme defaults to <root>/README.md.
 *
 * Exit codes: 0 clean/success, 1 drift detected (--check only), 2 malformed
 * input (bad fragment, bad README marker structure, usage error).
 */

import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseArgs } from "node:util";

const SECTION_NAMES = ["Setup", "Deployment", "Maintenance", "Secrets"];
const VALID_FRAGMENT_SECTIONS = new Set(SECTION_NAMES);

// Exact sentinel bodies, byte-for-byte matching templates/monorepo/README.md.tmpl
// (and references/authoring/documentation-standard.md's copy of the same body).
// These are re-emitted verbatim whenever a section has zero contributing
// fragments, so the zero-fragment skeleton round-trips as a no-op.
// NOT auto-verified: kept in sync by hand for now — a real id<->directory
// cross-check (tracked deferral N2) and a three-way sentinel byte-sync test
// against README.md.tmpl + canon (tracked deferral N3) are both deferred
// until the stack stages settle layer naming; until then, edit all three by hand.
const SENTINEL_INNER = {
  Setup: [
    "<!-- No blocks composed yet. `just docs-generate` fills this region with",
    "     one BEGIN/END block:<layer>/<name> pair per composed block, each",
    "     wrapping that block's Setup fragment content. -->",
  ],
  Deployment: [
    "<!-- No blocks composed yet. `just docs-generate` fills this region with",
    "     one BEGIN/END block:<layer>/<name> pair per composed block, each",
    "     wrapping that block's Deployment fragment content. -->",
  ],
  Maintenance: [
    "<!-- No blocks composed yet. `just docs-generate` fills this region with",
    "     one BEGIN/END block:<layer>/<name> pair per composed block, each",
    "     wrapping that block's Maintenance fragment content. -->",
  ],
  Secrets: [
    "<!-- No blocks composed yet. `just docs-generate` fills this region with",
    "     one BEGIN/END block:<layer>/<name> pair per composed block, each",
    "     wrapping that block's secrets table rows. -->",
  ],
};

const BEGIN_RE = /^<!--\s+BEGIN\s+block:(\S+)\s+-->$/;
const END_RE = /^<!--\s+END\s+block:(\S+)\s+-->$/;
const FRAGMENT_HEADER_RE = /^<!--\s+fragment:\s+block:(\S+)\s+-->$/;
const FRAGMENT_SECTION_RE = /^##\s+(.+?)\s*$/;
const RESERVED_SENTINEL_ID = "<layer>/<name>";
const SECRETS_SEPARATOR_RE = /^\s*\|(?:\s*:?-{1,}:?\s*\|)+\s*$/;
const SECRETS_HEADER_ROW_RE = /^\s*\|\s*Secret\s*\|/i;

// CommonMark-ish fenced-code-block marker: up to 3 leading spaces, then a run
// of 3+ backticks or 3+ tildes, then the rest of the line (an info string on
// open, must be blank on close).
const FENCE_MARKER_RE = /^ {0,3}(`{3,}|~{3,})(.*)$/;

/**
 * Returns a per-line classifier that tracks fenced-code-block state across
 * calls (one tracker instance per document/scan). Call it once per line, in
 * order; it returns true for the fence's opening marker line, every line of
 * fence content, and the fence's closing marker line — i.e. every line that
 * must be excluded from heading/marker matching because it is "inside a
 * fence" in the CommonMark sense. A fence only closes with the same
 * character and a marker at least as long as the one that opened it.
 */
function createFenceTracker() {
  let fenceChar = null;
  let fenceLen = 0;
  return function isFenceLine(line) {
    const m = FENCE_MARKER_RE.exec(line);
    if (fenceChar === null) {
      if (!m) return false;
      const char = m[1][0];
      const info = m[2];
      // A backtick fence's info string may not itself contain a backtick.
      if (char === "`" && info.includes("`")) return false;
      fenceChar = char;
      fenceLen = m[1].length;
      return true;
    }
    if (m && m[1][0] === fenceChar && m[1].length >= fenceLen && m[2].trim() === "") {
      fenceChar = null;
      fenceLen = 0;
      return true;
    }
    return true;
  };
}

class DocsAggregateError extends Error {}

function malformed(message) {
  return new DocsAggregateError(message);
}

function sentinelBlockLines(sectionName) {
  return [
    "<!-- BEGIN block:<layer>/<name> -->",
    ...SENTINEL_INNER[sectionName],
    "<!-- END block:<layer>/<name> -->",
  ];
}

function trimBlankEdges(lines) {
  const out = lines.slice();
  while (out.length && out[0].trim() === "") out.shift();
  while (out.length && out[out.length - 1].trim() === "") out.pop();
  return out;
}

/** Parse one docs/fragment.md file into { id, file, sections }. */
function parseFragment(filePath, raw) {
  const lines = raw.split(/\r?\n/);
  let idx = 0;
  while (idx < lines.length && lines[idx].trim() === "") idx++;
  if (idx >= lines.length) {
    throw malformed(`empty fragment file: ${filePath}`);
  }
  const headerMatch = FRAGMENT_HEADER_RE.exec(lines[idx].trim());
  if (!headerMatch) {
    throw malformed(
      `fragment header missing or malformed in ${filePath} — the first ` +
        `non-blank line must be exactly "<!-- fragment: block:<layer>/<name> -->"`,
    );
  }
  const id = headerMatch[1];
  if (id === RESERVED_SENTINEL_ID) {
    throw malformed(
      `fragment header in ${filePath} declares "block:${RESERVED_SENTINEL_ID}" — that id is ` +
        `permanently reserved for the empty-state sentinel (see documentation-standard.md, ` +
        `"Sentinel lifecycle") and must never be used by a real fragment`,
    );
  }

  const sections = {};
  let current = null;
  let buf = [];
  const finishCurrent = () => {
    if (current === null) return;
    if (Object.prototype.hasOwnProperty.call(sections, current)) {
      throw malformed(`duplicate "## ${current}" section in fragment ${filePath}`);
    }
    if (current === "Secrets") {
      for (const line of buf) {
        if (SECRETS_SEPARATOR_RE.test(line)) {
          throw malformed(
            `"## Secrets" in ${filePath} contains a table separator row ("${line.trim()}") — ` +
              `fragments contribute rows only; the header and separator are written once by ` +
              `the root README template (see documentation-standard.md, "Secrets section specifics")`,
          );
        }
        if (SECRETS_HEADER_ROW_RE.test(line)) {
          throw malformed(
            `"## Secrets" in ${filePath} contains a header row ("${line.trim()}") — ` +
              `fragments contribute rows only; the header and separator are written once by ` +
              `the root README template (see documentation-standard.md, "Secrets section specifics")`,
          );
        }
      }
    }
    sections[current] = buf.join("\n");
  };

  const fenceTracker = createFenceTracker();
  for (const line of lines.slice(idx + 1)) {
    const inFence = fenceTracker(line);
    const headingMatch = inFence ? null : FRAGMENT_SECTION_RE.exec(line);
    if (headingMatch) {
      finishCurrent();
      const name = headingMatch[1];
      if (!VALID_FRAGMENT_SECTIONS.has(name)) {
        throw malformed(
          `unknown fragment section "## ${name}" in ${filePath} — expected ` +
            `one of: ${SECTION_NAMES.join(", ")}`,
        );
      }
      current = name;
      buf = [];
    } else if (current !== null) {
      buf.push(line);
    } else if (line.trim() !== "") {
      throw malformed(
        `unexpected content before the first "##" section in fragment ${filePath}: "${line}"`,
      );
    }
  }
  finishCurrent();

  return { id, file: filePath, sections };
}

/** Discover docs/fragment.md under apps/*\/docs/, packages/*\/docs/, and infra/*\/docs/, sorted by block id. */
function discoverFragments(root) {
  const found = [];
  for (const group of ["apps", "packages", "infra"]) {
    const groupDir = path.join(root, group);
    let entries;
    try {
      entries = fs.readdirSync(groupDir, { withFileTypes: true });
    } catch {
      continue; // no apps/ or packages/ dir yet — nothing to discover there
    }
    entries.sort((a, b) => a.name.localeCompare(b.name));
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const fragPath = path.join(groupDir, entry.name, "docs", "fragment.md");
      if (fs.existsSync(fragPath)) {
        const raw = fs.readFileSync(fragPath, "utf8");
        found.push(parseFragment(fragPath, raw));
      }
    }
  }

  found.sort((a, b) => a.id.localeCompare(b.id));

  const seenBy = new Map();
  for (const fragment of found) {
    if (seenBy.has(fragment.id)) {
      throw malformed(
        `duplicate block id "${fragment.id}" declared by both ${seenBy.get(fragment.id)} and ${fragment.file}`,
      );
    }
    seenBy.set(fragment.id, fragment.file);
  }

  return found;
}

/**
 * Scan a section's body lines for BEGIN/END marker regions. Full-line
 * anchored matching only — never a substring search for "block:". Returns
 * the index of the first BEGIN line and the last END line (the contiguous
 * span the generator owns and replaces wholesale), after validating there
 * is no nesting, no unclosed region, no mismatched pair, and no duplicate
 * block id within the section.
 */
function locateRegionSpan(bodyLines, sectionName) {
  const stack = [];
  const seenIds = new Map();
  let firstBegin = -1;
  let lastEnd = -1;
  const fenceTracker = createFenceTracker();

  for (let i = 0; i < bodyLines.length; i++) {
    const line = bodyLines[i];
    if (fenceTracker(line)) continue; // inside (or delimiting) a fenced code block — never a marker
    const beginMatch = BEGIN_RE.exec(line);
    const endMatch = END_RE.exec(line);

    if (beginMatch) {
      if (stack.length > 0) {
        throw malformed(
          `nested aggregation markers in "## ${sectionName}": BEGIN block:${beginMatch[1]} ` +
            `opened while block:${stack[stack.length - 1].id} is still open`,
        );
      }
      stack.push({ id: beginMatch[1], start: i });
      if (firstBegin === -1) firstBegin = i;
    } else if (endMatch) {
      if (stack.length === 0) {
        throw malformed(
          `END marker without a matching BEGIN in "## ${sectionName}" (block:${endMatch[1]})`,
        );
      }
      const open = stack.pop();
      if (open.id !== endMatch[1]) {
        throw malformed(
          `mismatched aggregation markers in "## ${sectionName}": BEGIN block:${open.id} ` +
            `closed by END block:${endMatch[1]}`,
        );
      }
      if (seenIds.has(open.id)) {
        throw malformed(
          `duplicate block id "${open.id}" in "## ${sectionName}" (regions starting at ` +
            `lines ${seenIds.get(open.id) + 1} and ${open.start + 1} of that section)`,
        );
      }
      seenIds.set(open.id, open.start);
      lastEnd = i;
    }
  }

  if (stack.length > 0) {
    throw malformed(
      `unclosed aggregation region in "## ${sectionName}": BEGIN block:${stack[stack.length - 1].id} ` +
        `has no matching END`,
    );
  }
  if (firstBegin === -1) {
    throw malformed(
      `"## ${sectionName}" has no aggregation region markers — expected at least the ` +
        `block:<layer>/<name> sentinel pair (see references/authoring/documentation-standard.md)`,
    );
  }

  return { firstBegin, lastEnd };
}

/** Build the replacement region lines for one aggregating section from the fragment set. */
function buildRegionLines(sectionName, fragments) {
  const contributing = fragments
    .filter((f) => Object.prototype.hasOwnProperty.call(f.sections, sectionName))
    .sort((a, b) => a.id.localeCompare(b.id));

  if (contributing.length === 0) {
    return sentinelBlockLines(sectionName);
  }

  const out = [];
  contributing.forEach((fragment, i) => {
    if (i > 0) out.push("");
    const content = trimBlankEdges(fragment.sections[sectionName].split("\n"));
    out.push(`<!-- BEGIN block:${fragment.id} -->`, ...content, `<!-- END block:${fragment.id} -->`);
  });
  return out;
}

/** Replace one "## <name>" section's region span in-place within the full README lines. */
function regenerateSection(lines, sectionName, fragments) {
  // Trailing-whitespace tolerant, symmetric with FRAGMENT_SECTION_RE's
  // `\s*$` — still an exact match on the heading text itself. Fence-aware,
  // like every other heading/marker scan in this file: a fenced example line
  // reading "## <name>" (e.g. inside an earlier section's region content)
  // never anchors the section.
  let startIdx = -1;
  const startFenceTracker = createFenceTracker();
  for (let i = 0; i < lines.length; i++) {
    if (startFenceTracker(lines[i])) continue;
    if (lines[i].replace(/\s+$/, "") === `## ${sectionName}`) {
      startIdx = i;
      break;
    }
  }
  if (startIdx === -1) {
    throw malformed(`README is missing the required "## ${sectionName}" heading`);
  }
  let endIdx = lines.length;
  const boundaryFenceTracker = createFenceTracker();
  for (let i = startIdx + 1; i < lines.length; i++) {
    if (boundaryFenceTracker(lines[i])) continue; // a "##"-shaped line inside a fence never ends the section
    if (/^##\s/.test(lines[i])) {
      endIdx = i;
      break;
    }
  }

  const body = lines.slice(startIdx + 1, endIdx);
  const { firstBegin, lastEnd } = locateRegionSpan(body, sectionName);

  const prefix = body.slice(0, firstBegin);
  const suffix = body.slice(lastEnd + 1);
  const newRegionLines = buildRegionLines(sectionName, fragments);
  const newBody = [...prefix, ...newRegionLines, ...suffix];

  return [...lines.slice(0, startIdx + 1), ...newBody, ...lines.slice(endIdx)];
}

/**
 * The file's dominant line ending, used only to choose what we write back —
 * all reading/matching is EOL-agnostic (/\r?\n/) so a CRLF checkout never
 * misparses. CRLF wins only if strictly more line endings are CRLF than
 * lone-LF; otherwise (including no newlines at all) LF is used.
 */
function detectDominantEol(text) {
  const crlfCount = (text.match(/\r\n/g) || []).length;
  const lfCount = (text.match(/(?<!\r)\n/g) || []).length;
  return crlfCount > lfCount ? "\r\n" : "\n";
}

function regenerateReadme(originalText, fragments) {
  const eol = detectDominantEol(originalText);
  let lines = originalText.split(/\r?\n/);
  for (const sectionName of SECTION_NAMES) {
    lines = regenerateSection(lines, sectionName, fragments);
  }
  return lines.join(eol);
}

function summarizeDiff(oldText, newText) {
  const oldLines = oldText.split(/\r?\n/);
  const newLines = newText.split(/\r?\n/);

  let start = 0;
  const maxStart = Math.min(oldLines.length, newLines.length);
  while (start < maxStart && oldLines[start] === newLines[start]) start++;

  let oldEnd = oldLines.length - 1;
  let newEnd = newLines.length - 1;
  while (oldEnd >= start && newEnd >= start && oldLines[oldEnd] === newLines[newEnd]) {
    oldEnd--;
    newEnd--;
  }

  const removed = oldLines.slice(start, oldEnd + 1);
  const added = newLines.slice(start, newEnd + 1);

  const out = [`README.md has drifted from its doc fragments (first difference at line ${start + 1}):`];
  for (const line of removed) out.push(`- ${line}`);
  for (const line of added) out.push(`+ ${line}`);
  return out.join("\n");
}

function parseCliArgs(argv) {
  const { values } = parseArgs({
    args: argv,
    options: {
      check: { type: "boolean", default: false },
      root: { type: "string" },
      readme: { type: "string" },
      help: { type: "boolean", default: false },
    },
  });
  return values;
}

function main() {
  const values = parseCliArgs(process.argv.slice(2));

  if (values.help) {
    console.log(
      "Usage: node scripts/docs-aggregate.mjs [--check] [--root <dir>] [--readme <path>]",
    );
    process.exit(0);
  }

  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const defaultRoot = path.resolve(scriptDir, "..");
  const root = values.root ? path.resolve(values.root) : defaultRoot;
  const readmePath = values.readme ? path.resolve(values.readme) : path.join(root, "README.md");

  if (!fs.existsSync(readmePath)) {
    throw malformed(`README not found at ${readmePath}`);
  }

  const original = fs.readFileSync(readmePath, "utf8");
  const fragments = discoverFragments(root);
  const updated = regenerateReadme(original, fragments);

  if (values.check) {
    if (updated === original) {
      console.log(
        `docs-check: ${readmePath} is up to date with ${fragments.length} fragment(s).`,
      );
      process.exit(0);
    }
    console.error(summarizeDiff(original, updated));
    process.exit(1);
  }

  if (updated !== original) {
    fs.writeFileSync(readmePath, updated, "utf8");
    console.log(`docs-generate: wrote ${readmePath} (${fragments.length} fragment(s)).`);
  } else {
    console.log(
      `docs-generate: ${readmePath} already up to date (${fragments.length} fragment(s)) — no changes.`,
    );
  }
  process.exit(0);
}

try {
  main();
} catch (err) {
  if (err instanceof DocsAggregateError) {
    console.error(`docs-aggregate: ${err.message}`);
    process.exit(2);
  }
  console.error(`docs-aggregate: unexpected error: ${err.stack || err.message}`);
  process.exit(2);
}
