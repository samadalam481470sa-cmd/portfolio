/**
 * Remote OK public API.
 * Docs: https://remoteok.com/api
 *
 * Free public JSON feed. Their terms ask that you link back to the original
 * posting URL and attribute the source, which the generated report does.
 */
const { fetchJson } = require("../http");
const { stripHtml } = require("../html");

const ID = "remoteok";

async function fetchJobs(config) {
  const data = await fetchJson("https://remoteok.com/api");
  const entries = Array.isArray(data) ? data : [];
  const tagFilter = (config.tags || []).map((t) => t.toLowerCase());

  const jobs = [];
  for (const entry of entries) {
    // The first element of the feed is Remote OK's legal/attribution notice.
    if (!entry || !entry.id || entry.legal) continue;

    const tags = (entry.tags || []).map((t) => String(t).toLowerCase());
    if (tagFilter.length > 0 && !tagFilter.some((t) => tags.includes(t))) continue;

    jobs.push({
      id: `${ID}:${entry.id}`,
      source: ID,
      title: entry.position || "",
      company: entry.company || "",
      location: entry.location || "Remote",
      url: entry.url || entry.apply_url || "",
      description: stripHtml(entry.description) || (entry.tags || []).join(", "),
      postedAt: entry.date || null,
    });
  }

  return jobs;
}

module.exports = {
  id: ID,
  label: "Remote OK",
  attribution: "Job data from Remote OK (https://remoteok.com)",
  fetchJobs,
};
