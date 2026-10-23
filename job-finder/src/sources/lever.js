/**
 * Lever public Postings API.
 * Docs: https://github.com/lever/postings-api
 * Endpoint: https://api.lever.co/v0/postings/{company}?mode=json
 *
 * Public, key-free endpoint intended for embedding/consuming a company's
 * own job postings.
 */
const { fetchJson, sleep } = require("../http");
const { stripHtml } = require("../html");

const ID = "lever";

async function fetchJobs(config) {
  const companies = config.companies || [];
  const jobs = [];

  for (const company of companies) {
    const url = `https://api.lever.co/v0/postings/${encodeURIComponent(company)}?mode=json`;
    try {
      const data = await fetchJson(url);
      for (const job of Array.isArray(data) ? data : []) {
        const categories = job.categories || {};
        jobs.push({
          id: `${ID}:${company}:${job.id}`,
          source: ID,
          title: job.text || "",
          company,
          location: categories.location || "",
          url: job.hostedUrl || job.applyUrl || "",
          description: job.descriptionPlain || stripHtml(job.description),
          postedAt: job.createdAt ? new Date(job.createdAt).toISOString() : null,
        });
      }
    } catch (err) {
      // Companies migrate between ATS vendors constantly; skip and continue.
      console.warn(`    lever/${company}: skipped — ${err.message}`);
    }
    await sleep(250);
  }

  return jobs;
}

module.exports = { id: ID, label: "Lever", fetchJobs };
