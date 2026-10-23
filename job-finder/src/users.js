/**
 * Multi-user store for the self-hostable web service.
 *
 * Each uploaded resume becomes a user directory under `job-finder/users/`:
 *   users/<id>/profile.json   — id, createdAt, display label, per-user filters
 *   users/<id>/resume.txt     — the uploaded resume text
 *   users/<id>/output/        — that user's latest matches + drafts (written by the runner)
 *
 * IMPORTANT: this directory holds other people's resumes (names, contact
 * details). It is git-ignored and must never be committed. On a real
 * deployment keep it on a private disk, not in a public repo.
 */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");

const { ROOT } = require("./config");

const USERS_DIR = process.env.JOB_FINDER_USERS_DIR || path.join(ROOT, "users");

const MAX_RESUME_CHARS = 60000; // generous for a resume; blocks accidental huge pastes
const MIN_RESUME_CHARS = 40;

function ensureUsersDir() {
  fs.mkdirSync(USERS_DIR, { recursive: true });
}

function newUserId() {
  // Unguessable id doubles as a capability token for the user's results URL.
  return crypto.randomBytes(9).toString("base64url");
}

function userDir(id) {
  // Guard against path traversal from a user-supplied id.
  const safe = String(id).replace(/[^a-zA-Z0-9_-]/g, "");
  if (!safe || safe !== String(id)) throw new Error("Invalid user id");
  return path.join(USERS_DIR, safe);
}

function sanitizeFilters(input = {}) {
  const toArray = (v) =>
    Array.isArray(v)
      ? v.map((s) => String(s).trim()).filter(Boolean).slice(0, 100)
      : String(v || "")
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
          .slice(0, 100);

  const filters = {};
  if (input.titleInclude !== undefined) filters.titleInclude = toArray(input.titleInclude);
  if (input.titleExclude !== undefined) filters.titleExclude = toArray(input.titleExclude);
  if (input.locationInclude !== undefined) filters.locationInclude = toArray(input.locationInclude);
  if (input.locationExclude !== undefined) filters.locationExclude = toArray(input.locationExclude);
  if (input.remoteOnly !== undefined) filters.remoteOnly = Boolean(input.remoteOnly);
  if (input.minScore !== undefined && input.minScore !== "") {
    const n = Number(input.minScore);
    if (!Number.isNaN(n)) filters.minScore = Math.max(0, Math.min(100, n));
  }
  return filters;
}

function createUser({ resumeText, label, filters }) {
  ensureUsersDir();

  const text = String(resumeText || "").trim();
  if (text.length < MIN_RESUME_CHARS) {
    throw new Error(`Resume text is too short (need at least ${MIN_RESUME_CHARS} characters).`);
  }
  if (text.length > MAX_RESUME_CHARS) {
    throw new Error(`Resume text is too long (max ${MAX_RESUME_CHARS} characters).`);
  }

  const id = newUserId();
  const dir = userDir(id);
  fs.mkdirSync(dir, { recursive: true });

  const profile = {
    id,
    label: String(label || "").trim().slice(0, 80) || "Anonymous",
    createdAt: new Date().toISOString(),
    filters: sanitizeFilters(filters),
  };

  fs.writeFileSync(path.join(dir, "profile.json"), JSON.stringify(profile, null, 2));
  fs.writeFileSync(path.join(dir, "resume.txt"), text);
  return profile;
}

function loadUser(id) {
  const dir = userDir(id);
  const profilePath = path.join(dir, "profile.json");
  if (!fs.existsSync(profilePath)) return null;
  const profile = JSON.parse(fs.readFileSync(profilePath, "utf8"));
  const resumePath = path.join(dir, "resume.txt");
  const resumeText = fs.existsSync(resumePath) ? fs.readFileSync(resumePath, "utf8") : "";
  return { ...profile, resumeText, dir };
}

function listUsers() {
  ensureUsersDir();
  return fs
    .readdirSync(USERS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => loadUser(entry.name))
    .filter(Boolean);
}

function readUserMatches(id) {
  const dir = userDir(id);
  const matchesPath = path.join(dir, "output", "matches.json");
  if (!fs.existsSync(matchesPath)) return null;
  try {
    return JSON.parse(fs.readFileSync(matchesPath, "utf8"));
  } catch {
    return null;
  }
}

function deleteUser(id) {
  const dir = userDir(id);
  if (fs.existsSync(dir)) fs.rmSync(dir, { recursive: true, force: true });
}

module.exports = {
  USERS_DIR,
  createUser,
  loadUser,
  listUsers,
  readUserMatches,
  deleteUser,
  sanitizeFilters,
  userDir,
  MAX_RESUME_CHARS,
  MIN_RESUME_CHARS,
};
