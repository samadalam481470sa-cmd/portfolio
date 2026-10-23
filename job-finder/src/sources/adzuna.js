/**
 * Adzuna Job Search API (optional — requires free API credentials).
 * Docs: https://developer.adzuna.com/overview
 *
 * Set ADZUNA_APP_ID and ADZUNA_APP_KEY as CI variables to enable.
 */
const { fetchJson, sleep } = require("../http");
const { stripHtml } = require("../html");

const ID = "adzuna";

async function fetchJobs(config) {
  const appId = process.env.ADZUNA_APP_ID;
  const appKey = process.env.ADZUNA_APP_KEY;
  if (!appId || !appKey) {
    throw new Error("Adzuna enabled but ADZUNA_APP_ID / ADZUNA_APP_KEY are not set");
  }

  const country = config.country || "us";
  const pages = Math.max(1, Math.min(config.pages || 1, 5));
  const resultsPerPage = Math.max(1, Math.min(config.resultsPerPage || 50, 50));
  const jobs = [];

  for (let page = 1; page <= pages; page++) {
    const params = new URLSearchParams({
      app_id: appId,
      app_key: appKey,
      results_per_page: String(resultsPerPage),
      "content-type": "application/json",
    });
    if (config.what) params.set("what", config.what);
    if (config.where) params.set("where", config.where);
    if (config.maxDaysOld) params.set("max_days_old", String(config.maxDaysOld));

    const url = `https://api.adzuna.com/v1/api/jobs/${encodeURIComponent(country)}/search/${page}?${params.toString()}`;
    const data = await fetchJson(url);
    for (const job of data.results || []) {
      jobs.push({
        id: `${ID}:${job.id}`,
        source: ID,
        title: job.title || "",
        company: (job.company && job.company.display_name) || "",
        location: (job.location && job.location.display_name) || "",
        url: job.redirect_url || "",
        description: stripHtml(job.description),
        postedAt: job.created || null,
      });
    }
    await sleep(400);
  }

  return jobs;
}

module.exports = { id: ID, label: "Adzuna", fetchJobs };
