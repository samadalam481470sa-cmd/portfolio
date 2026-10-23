/**
 * Fetches postings from every enabled source once. Separated from scoring so
 * a multi-user run can fetch the shared pool of jobs a single time and then
 * score it against many different resumes.
 */
const { SOURCES_BY_ID } = require("./sources");

async function fetchAllJobs(config, logger = console) {
  const enabledSourceIds = Object.entries(config.sources)
    .filter(([, sourceConfig]) => sourceConfig && sourceConfig.enabled)
    .map(([id]) => id);

  if (enabledSourceIds.length === 0) {
    throw new Error("No sources enabled in config.json — enable at least one under `sources`.");
  }

  logger.log(`Fetching from ${enabledSourceIds.length} source(s): ${enabledSourceIds.join(", ")}`);

  const allJobs = [];
  const sourcesSucceeded = [];
  const sourcesFailed = [];
  const attributions = [];

  // Sources run sequentially: it's a background job, and being gentle with
  // third-party APIs matters more than shaving seconds off the runtime.
  for (const id of enabledSourceIds) {
    const source = SOURCES_BY_ID[id];
    if (!source) {
      sourcesFailed.push({ id, error: "unknown source id" });
      logger.warn(`Skipping unknown source "${id}"`);
      continue;
    }
    try {
      const jobs = await source.fetchJobs(config.sources[id] || {});
      allJobs.push(...jobs);
      sourcesSucceeded.push(id);
      if (source.attribution) attributions.push(source.attribution);
      logger.log(`  ${source.label}: ${jobs.length} posting(s)`);
    } catch (err) {
      sourcesFailed.push({ id, error: err.message });
      logger.warn(`  ${source.label}: FAILED — ${err.message}`);
    }
  }

  if (sourcesSucceeded.length === 0) {
    throw new Error("Every enabled source failed — see the warnings above.");
  }

  return { allJobs, sourcesSucceeded, sourcesFailed, attributions };
}

module.exports = { fetchAllJobs };
