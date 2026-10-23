/**
 * Scores and filters postings against the resume, reusing the *exact* same
 * keyword-overlap logic the Chrome extension uses on-page, so a score in the
 * CI digest means the same thing as a score in the browser.
 */
const path = require("node:path");

const JobMatcher = require(path.join(__dirname, "../../job-application-chrome-extension/lib/matcher.js"));
const ResumeParser = require(path.join(__dirname, "../../job-application-chrome-extension/lib/resumeParser.js"));

function matchesAny(text, needles) {
  if (!needles || needles.length === 0) return true;
  const lower = (text || "").toLowerCase();
  return needles.some((n) => lower.includes(String(n).toLowerCase()));
}

function matchesNone(text, needles) {
  if (!needles || needles.length === 0) return true;
  const lower = (text || "").toLowerCase();
  return !needles.some((n) => lower.includes(String(n).toLowerCase()));
}

function isRemote(job) {
  const haystack = `${job.location || ""} ${job.title || ""}`.toLowerCase();
  if (/remote|anywhere|distributed/.test(haystack)) return true;
  // Fall back to the description, but only its opening chunk to avoid
  // matching boilerplate like "we have remote offices" deep in the text.
  return /remote/.test((job.description || "").slice(0, 400).toLowerCase());
}

function withinDays(job, days) {
  if (!days || !job.postedAt) return true;
  const posted = new Date(job.postedAt);
  if (Number.isNaN(posted.getTime())) return true;
  const ageDays = (Date.now() - posted.getTime()) / (1000 * 60 * 60 * 24);
  return ageDays <= days;
}

function passesFilters(job, filters) {
  if (!matchesAny(job.title, filters.titleInclude)) return false;
  if (!matchesNone(job.title, filters.titleExclude)) return false;
  if (filters.locationInclude && filters.locationInclude.length > 0 && !matchesAny(job.location, filters.locationInclude)) {
    return false;
  }
  // Location strings are often blank or "N/A"; only exclude when the posting
  // actually names a place you've ruled out.
  if (job.location && !matchesNone(job.location, filters.locationExclude)) return false;
  if (filters.remoteOnly && !isRemote(job)) return false;
  if (!withinDays(job, filters.postedWithinDays)) return false;
  return true;
}

function dedupeJobs(jobs) {
  const seen = new Set();
  const unique = [];
  for (const job of jobs) {
    // Same role cross-posted to multiple sources: key on company+title+url.
    const key = `${(job.company || "").toLowerCase()}|${(job.title || "").toLowerCase()}|${job.url || ""}`;
    if (seen.has(key)) continue;
    seen.add(key);
    unique.push(job);
  }
  return unique;
}

/**
 * Returns { profile, matches } where matches is a ranked array of
 * { ...job, score, matched, missing }.
 */
function scoreJobs(jobs, resumeText, filters) {
  const profile = ResumeParser.parseResume(resumeText);
  const scored = [];

  for (const job of dedupeJobs(jobs)) {
    if (!passesFilters(job, filters)) continue;
    const jobText = `${job.title}\n${job.description || ""}`;
    const result = JobMatcher.computeMatchScore(resumeText, profile.skills, jobText);
    if (result.score < filters.minScore) continue;
    scored.push({ ...job, score: result.score, matched: result.matched, missing: result.missing });
  }

  scored.sort((a, b) => b.score - a.score);
  return { profile, matches: scored.slice(0, filters.maxResults) };
}

module.exports = { scoreJobs, passesFilters, dedupeJobs, isRemote, withinDays };
