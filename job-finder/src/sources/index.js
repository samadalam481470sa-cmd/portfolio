/**
 * Registry of job sources. Every source here is an officially documented,
 * public API intended for programmatic consumption (some optionally
 * key-gated) — no scraping of pages that prohibit it, no logging into
 * anyone's account.
 *
 * To add a source: create a module exporting { id, label, fetchJobs(config) }
 * that returns normalized postings:
 *   { id, source, title, company, location, url, description, postedAt }
 */
const greenhouse = require("./greenhouse");
const lever = require("./lever");
const ashby = require("./ashby");
const remoteok = require("./remoteok");
const adzuna = require("./adzuna");
const usajobs = require("./usajobs");

const SOURCES = [greenhouse, lever, ashby, remoteok, adzuna, usajobs];

const SOURCES_BY_ID = SOURCES.reduce((acc, source) => {
  acc[source.id] = source;
  return acc;
}, {});

module.exports = { SOURCES, SOURCES_BY_ID };
