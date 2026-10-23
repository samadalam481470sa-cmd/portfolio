/**
 * USAJOBS Search API (optional — requires a free API key).
 * Docs: https://developer.usajobs.gov/
 *
 * Set USAJOBS_API_KEY and USAJOBS_EMAIL as CI variables to enable.
 */
const { fetchJson } = require("../http");
const { stripHtml } = require("../html");

const ID = "usajobs";

async function fetchJobs(config) {
  const apiKey = process.env.USAJOBS_API_KEY;
  const email = process.env.USAJOBS_EMAIL;
  if (!apiKey || !email) {
    throw new Error("USAJOBS enabled but USAJOBS_API_KEY / USAJOBS_EMAIL are not set");
  }

  const params = new URLSearchParams({
    ResultsPerPage: String(Math.min(config.resultsPerPage || 50, 500)),
  });
  if (config.keyword) params.set("Keyword", config.keyword);
  if (config.locationName) params.set("LocationName", config.locationName);
  if (config.remoteOnly) params.set("RemoteIndicator", "true");

  const url = `https://data.usajobs.gov/api/search?${params.toString()}`;
  const data = await fetchJson(url, {
    headers: {
      Host: "data.usajobs.gov",
      "User-Agent": email,
      "Authorization-Key": apiKey,
    },
  });

  const items = (data.SearchResult && data.SearchResult.SearchResultItems) || [];
  return items.map((item) => {
    const d = item.MatchedObjectDescriptor || {};
    const details = (d.UserArea && d.UserArea.Details) || {};
    return {
      id: `${ID}:${item.MatchedObjectId || d.PositionID}`,
      source: ID,
      title: d.PositionTitle || "",
      company: d.OrganizationName || "",
      location: d.PositionLocationDisplay || "",
      url: d.PositionURI || "",
      description: stripHtml([d.QualificationSummary, details.JobSummary, details.MajorDuties].filter(Boolean).join("\n")),
      postedAt: d.PublicationStartDate || null,
    };
  });
}

module.exports = { id: ID, label: "USAJOBS", fetchJobs };
