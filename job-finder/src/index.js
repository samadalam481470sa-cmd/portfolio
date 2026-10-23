#!/usr/bin/env node
/**
 * Scheduled job-discovery run.
 *
 * Fetches postings from officially public job APIs, scores each against the
 * resume with the same logic the Chrome extension uses, writes a ranked
 * shortlist plus per-job cover-letter drafts, and (optionally) pings a
 * webhook.
 *
 * It deliberately stops at discovery + preparation. It does not submit
 * applications, create accounts, or log into any job board — you open the
 * links it produces and apply yourself (the browser extension makes that
 * fast).
 */
const fs = require("node:fs");
const path = require("node:path");

const { loadConfig, loadResumeText, ROOT } = require("./config");
const { fetchAllJobs } = require("./fetchJobs");
const { scoreJobs } = require("./score");
const { writeOutputs, sendWebhook } = require("./report");

const CACHE_DIR = path.join(ROOT, ".cache");
const SEEN_PATH = path.join(CACHE_DIR, "seen.json");
const OUTPUT_DIR = path.join(ROOT, "output");

function loadSeenIds() {
  try {
    if (fs.existsSync(SEEN_PATH)) {
      const parsed = JSON.parse(fs.readFileSync(SEEN_PATH, "utf8"));
      return new Set(parsed.ids || []);
    }
  } catch (err) {
    console.warn(`Could not read seen-cache (${err.message}); treating everything as new.`);
  }
  return new Set();
}

function saveSeenIds(ids) {
  fs.mkdirSync(CACHE_DIR, { recursive: true });
  // Keep the cache bounded so it doesn't grow forever across scheduled runs.
  const bounded = Array.from(ids).slice(-5000);
  fs.writeFileSync(SEEN_PATH, JSON.stringify({ updatedAt: new Date().toISOString(), ids: bounded }, null, 2));
}

async function main() {
  const config = loadConfig();
  const resumeText = loadResumeText();

  const { allJobs, sourcesSucceeded, sourcesFailed, attributions } = await fetchAllJobs(config);

  const { profile, matches } = scoreJobs(allJobs, resumeText, config.filters);

  const seenIds = loadSeenIds();
  let newCount = 0;
  for (const job of matches) {
    job.isNew = !seenIds.has(job.id);
    if (job.isNew) newCount++;
  }

  const meta = {
    generatedAt: new Date().toISOString(),
    totalFetched: allJobs.length,
    sourcesSucceeded,
    sourcesFailed,
    attributions,
    filters: config.filters,
    newCount,
    profile,
  };

  const { draftCount, tailoredCount } = writeOutputs(OUTPUT_DIR, matches, meta, config);

  matches.forEach((job) => seenIds.add(job.id));
  saveSeenIds(seenIds);

  const webhookSent = await sendWebhook(matches, meta);

  console.log("");
  console.log(`Scanned ${allJobs.length} posting(s); ${matches.length} cleared your filters (${newCount} new).`);
  console.log(
    `Wrote ${path.relative(process.cwd(), OUTPUT_DIR)}/: matches.md, matches.json, ` +
      `${draftCount} cover-letter draft(s), ${tailoredCount} tailored-resume plan(s).`
  );
  if (webhookSent) console.log("Posted summary to JOB_ALERT_WEBHOOK.");
  console.log("");
  console.log("Next step is yours: open the links, review each posting, and submit the applications you actually want.");
}

if (require.main === module) {
  main().catch((err) => {
    console.error(`\nJob discovery failed: ${err.message}`);
    process.exit(1);
  });
}

module.exports = { main };
