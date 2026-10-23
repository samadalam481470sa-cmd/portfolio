/**
 * Greenhouse public Job Board API.
 * Docs: https://developers.greenhouse.io/job-board.html
 * Endpoint: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
 *
 * This is the same public endpoint companies use to embed their own job
 * boards — it's intended for programmatic consumption and needs no key.
 */
const { fetchJson, sleep } = require("../http");
const { stripHtml } = require("../html");

const ID = "greenhouse";

async function fetchJobs(config) {
  const boards = config.boards || [];
  const jobs = [];

  for (const board of boards) {
    const url = `https://boards-api.greenhouse.io/v1/boards/${encodeURIComponent(board)}/jobs?content=true`;
    try {
      const data = await fetchJson(url);
      for (const job of data.jobs || []) {
        jobs.push({
          id: `${ID}:${board}:${job.id}`,
          source: ID,
          title: job.title || "",
          company: board,
          location: (job.location && job.location.name) || "",
          url: job.absolute_url || "",
          description: stripHtml(job.content),
          postedAt: job.updated_at || job.first_published || null,
        });
      }
    } catch (err) {
      // A company that moved off Greenhouse (or a typo'd slug) shouldn't
      // take down the whole source.
      console.warn(`    greenhouse/${board}: skipped — ${err.message}`);
    }
    // Be polite between boards.
    await sleep(250);
  }

  return jobs;
}

module.exports = { id: ID, label: "Greenhouse", fetchJobs };
