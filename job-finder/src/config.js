const fs = require("node:fs");
const path = require("node:path");

const ROOT = path.join(__dirname, "..");

const DEFAULT_FILTERS = {
  titleInclude: [],
  titleExclude: [],
  locationInclude: [],
  locationExclude: [],
  remoteOnly: false,
  minScore: 20,
  maxResults: 40,
  postedWithinDays: 30,
};

const DEFAULT_OUTPUT = {
  generateCoverLetterDrafts: true,
  draftsForTopN: 10,
  generateTailoredResumes: true,
  tailoredResumesForTopN: 10,
};

function loadConfig(configPath) {
  const resolved = configPath || process.env.JOB_FINDER_CONFIG || path.join(ROOT, "config.json");
  if (!fs.existsSync(resolved)) {
    throw new Error(`Config not found at ${resolved}. Copy config.example.json to config.json.`);
  }
  const raw = JSON.parse(fs.readFileSync(resolved, "utf8"));
  return {
    sources: raw.sources || {},
    filters: { ...DEFAULT_FILTERS, ...(raw.filters || {}) },
    output: { ...DEFAULT_OUTPUT, ...(raw.output || {}) },
  };
}

/**
 * Resolves the resume text. Preference order:
 *   1. RESUME_TEXT env var (paste the text into a CI variable)
 *   2. RESUME_FILE env var (path — works with GitLab "File" type variables)
 *   3. job-finder/resume.txt (only if you're comfortable committing it)
 *
 * Using a CI variable is recommended so personal contact details stay out of
 * the repository.
 */
function loadResumeText() {
  if (process.env.RESUME_TEXT && process.env.RESUME_TEXT.trim()) {
    return process.env.RESUME_TEXT;
  }
  if (process.env.RESUME_FILE && fs.existsSync(process.env.RESUME_FILE)) {
    return fs.readFileSync(process.env.RESUME_FILE, "utf8");
  }
  const localPath = path.join(ROOT, "resume.txt");
  if (fs.existsSync(localPath)) {
    return fs.readFileSync(localPath, "utf8");
  }
  throw new Error(
    "No resume found. Set the RESUME_TEXT CI variable (recommended), set RESUME_FILE to a file path, or add job-finder/resume.txt."
  );
}

module.exports = { loadConfig, loadResumeText, ROOT, DEFAULT_FILTERS, DEFAULT_OUTPUT };
