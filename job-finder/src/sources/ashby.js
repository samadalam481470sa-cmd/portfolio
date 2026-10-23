/**
 * Ashby public job board API.
 * Docs: https://developers.ashbyhq.com/docs/public-job-posting-api
 * Endpoint: https://api.ashbyhq.com/posting-api/job-board/{jobBoardName}
 *
 * Public, key-free endpoint for a company's own published postings.
 */
const { fetchJson, sleep } = require("../http");
const { stripHtml } = require("../html");

const ID = "ashby";

async function fetchJobs(config) {
  const boards = config.boards || [];
  const jobs = [];

  for (const board of boards) {
    const url = `https://api.ashbyhq.com/posting-api/job-board/${encodeURIComponent(board)}`;
    try {
      const data = await fetchJson(url);
      for (const job of data.jobs || []) {
        jobs.push({
          id: `${ID}:${board}:${job.id}`,
          source: ID,
          title: job.title || "",
          company: data.name || board,
          location: job.location || (job.address && job.address.postalAddress && job.address.postalAddress.addressLocality) || "",
          url: job.jobUrl || job.applyUrl || "",
          description: job.descriptionPlain || stripHtml(job.descriptionHtml),
          postedAt: job.publishedAt || job.updatedAt || null,
        });
      }
    } catch (err) {
      console.warn(`    ashby/${board}: skipped — ${err.message}`);
    }
    await sleep(250);
  }

  return jobs;
}

module.exports = { id: ID, label: "Ashby", fetchJobs };
