#!/usr/bin/env node
/**
 * Multi-user discovery run. Fetches the shared pool of postings once, then
 * scores and prepares tailored drafts for every uploaded resume, writing each
 * user's results into their own directory.
 *
 * Same boundary as the single-user runner: it discovers and prepares. It does
 * not submit applications, create accounts, or drive a browser on anyone's
 * behalf. Each user opens their own links and applies themselves.
 */
const path = require("node:path");

const { loadConfig } = require("./config");
const { fetchAllJobs } = require("./fetchJobs");
const { scoreJobs } = require("./score");
const { writeOutputs } = require("./report");
const { listUsers } = require("./users");

/**
 * Runs one discovery cycle for all users. Returns a per-user summary.
 * Safe to call repeatedly (used by the web server's internal scheduler).
 */
async function runOnce(logger = console) {
  const config = loadConfig();
  const users = listUsers();

  if (users.length === 0) {
    logger.log("No users have uploaded a resume yet — nothing to do this cycle.");
    return { users: 0, results: [] };
  }

  logger.log(`Running discovery for ${users.length} user(s).`);
  const { allJobs, sourcesSucceeded, sourcesFailed, attributions } = await fetchAllJobs(config, logger);
  logger.log(`Fetched ${allJobs.length} posting(s); scoring per user.`);

  const results = [];
  for (const user of users) {
    try {
      // Per-user filters override the shared defaults from config.json.
      const filters = { ...config.filters, ...(user.filters || {}) };
      const { profile, matches } = scoreJobs(allJobs, user.resumeText, filters);

      const meta = {
        generatedAt: new Date().toISOString(),
        totalFetched: allJobs.length,
        sourcesSucceeded,
        sourcesFailed,
        attributions,
        filters,
        profile,
      };

      const outputDir = path.join(user.dir, "output");
      const { draftCount, tailoredCount } = writeOutputs(outputDir, matches, meta, config);

      logger.log(`  [${user.label}] ${matches.length} match(es), ${tailoredCount} tailored, ${draftCount} drafts`);
      results.push({ id: user.id, label: user.label, matchCount: matches.length });
    } catch (err) {
      logger.warn(`  [${user.label}] failed: ${err.message}`);
      results.push({ id: user.id, label: user.label, error: err.message });
    }
  }

  return { users: users.length, results };
}

async function main() {
  const summary = await runOnce();
  console.log("");
  console.log(`Done. Processed ${summary.users} user(s).`);
  console.log("Each user reviews their own shortlist and applies themselves.");
}

if (require.main === module) {
  main().catch((err) => {
    console.error(`\nMulti-user discovery failed: ${err.message}`);
    process.exit(1);
  });
}

module.exports = { runOnce, main };
