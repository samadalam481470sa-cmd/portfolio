#!/usr/bin/env node
/**
 * Validates and packages the Chrome extension.
 *
 * The zip is built with a single top-level folder ("resume-fit-assistant/")
 * so that double-clicking it on macOS produces exactly one clearly-named
 * folder containing manifest.json — which is the folder you point Chrome's
 * "Load unpacked" at. A zip with files loose at the root is the classic
 * cause of Chrome's "Manifest file is missing or unreadable" error, because
 * it's ambiguous which directory to select.
 *
 * Usage (from the portfolio root): node newport-acquisition-crm/scripts/build-extension.js
 */
const fs = require("node:fs");
const path = require("node:path");
const { execFileSync } = require("node:child_process");

const ROOT = path.join(__dirname, "..", "..");
const SRC = path.join(ROOT, "job-application-chrome-extension");
const PKG_NAME = "resume-fit-assistant";
const OUT_ZIP = path.join(ROOT, `${PKG_NAME}.zip`);
const STAGE = path.join(ROOT, ".build");

const problems = [];

function fail(msg) {
  problems.push(msg);
}

function mustExist(relPath, why) {
  const abs = path.join(SRC, relPath);
  if (!fs.existsSync(abs)) fail(`${why}: missing file "${relPath}"`);
  return fs.existsSync(abs);
}

// --- 1. Manifest validation -------------------------------------------
const manifestPath = path.join(SRC, "manifest.json");
if (!fs.existsSync(manifestPath)) {
  console.error("FATAL: job-application-chrome-extension/manifest.json not found");
  process.exit(1);
}

let manifest;
try {
  manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
} catch (err) {
  console.error(`FATAL: manifest.json is not valid JSON — ${err.message}`);
  process.exit(1);
}

if (manifest.manifest_version !== 3) fail("manifest_version must be 3");
["name", "version", "description"].forEach((key) => {
  if (!manifest[key]) fail(`manifest is missing required key "${key}"`);
});
if (!/^\d+(\.\d+){0,3}$/.test(manifest.version || "")) {
  fail(`manifest version "${manifest.version}" must be 1-4 dot-separated integers`);
}

// --- 2. Every file the manifest references must exist ------------------
if (manifest.action && manifest.action.default_popup) {
  mustExist(manifest.action.default_popup, "action.default_popup");
}
if (manifest.background && manifest.background.service_worker) {
  mustExist(manifest.background.service_worker, "background.service_worker");
}
(manifest.content_scripts || []).forEach((cs, i) => {
  (cs.js || []).forEach((js) => mustExist(js, `content_scripts[${i}].js`));
  (cs.css || []).forEach((css) => mustExist(css, `content_scripts[${i}].css`));
  if (!cs.matches || cs.matches.length === 0) fail(`content_scripts[${i}] has no "matches"`);
});
Object.values(manifest.icons || {}).forEach((icon) => mustExist(icon, "icons"));

// --- 3. Files referenced from popup.html must exist --------------------
const popupRel = (manifest.action && manifest.action.default_popup) || "popup.html";
const popupPath = path.join(SRC, popupRel);
if (fs.existsSync(popupPath)) {
  const html = fs.readFileSync(popupPath, "utf8");
  const refs = [
    ...[...html.matchAll(/<script[^>]+src=["']([^"']+)["']/g)].map((m) => m[1]),
    ...[...html.matchAll(/<link[^>]+href=["']([^"']+)["']/g)].map((m) => m[1]),
  ].filter((ref) => !/^https?:/.test(ref));
  refs.forEach((ref) => mustExist(ref, `${popupRel} reference`));
}

// --- 4. Files injected at runtime via chrome.scripting.executeScript ---
// These are string literals in the source, so a rename silently breaks them
// at click time rather than at load time. Check them here instead.
const injectedLists = [];
for (const file of ["popup.js", "background.js"]) {
  const abs = path.join(SRC, file);
  if (!fs.existsSync(abs)) continue;
  const src = fs.readFileSync(abs, "utf8");
  for (const m of src.matchAll(/files:\s*\[([^\]]+)\]/g)) {
    const files = [...m[1].matchAll(/["']([^"']+)["']/g)].map((x) => x[1]);
    injectedLists.push({ file, files });
  }
}
injectedLists.forEach(({ file, files }) => {
  files.forEach((f) => mustExist(f, `${file} executeScript`));
});

// --- 5. Syntax-check every JS file ------------------------------------
function walk(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    return entry.isDirectory() ? walk(full) : [full];
  });
}
const jsFiles = walk(SRC).filter((f) => f.endsWith(".js"));
jsFiles.forEach((f) => {
  try {
    execFileSync(process.execPath, ["--check", f], { stdio: "pipe" });
  } catch (err) {
    fail(`syntax error in ${path.relative(SRC, f)}: ${String(err.stderr).split("\n")[0]}`);
  }
});

// --- 6. Report ---------------------------------------------------------
if (problems.length > 0) {
  console.error("Extension package validation FAILED:\n");
  problems.forEach((p) => console.error(`  - ${p}`));
  process.exit(1);
}
console.log(`Validated ${jsFiles.length} JS file(s) and all manifest references.`);

// --- 7. Package --------------------------------------------------------
fs.rmSync(STAGE, { recursive: true, force: true });
const stagedRoot = path.join(STAGE, PKG_NAME);
fs.mkdirSync(stagedRoot, { recursive: true });
fs.cpSync(SRC, stagedRoot, { recursive: true });

// Strip anything that shouldn't ship.
walk(stagedRoot)
  .filter((f) => path.basename(f) === ".DS_Store" || path.basename(f) === "package.json")
  .forEach((f) => fs.rmSync(f));

fs.rmSync(OUT_ZIP, { force: true });
execFileSync("zip", ["-r", "-q", OUT_ZIP, PKG_NAME, "-x", "*.DS_Store"], { cwd: STAGE });
fs.rmSync(STAGE, { recursive: true, force: true });

const sizeKb = (fs.statSync(OUT_ZIP).size / 1024).toFixed(1);
console.log(`Built ${path.relative(ROOT, OUT_ZIP)} (${sizeKb} KB)`);
console.log(`Unzips to a single folder: ${PKG_NAME}/  <- select this in Chrome's "Load unpacked"`);
