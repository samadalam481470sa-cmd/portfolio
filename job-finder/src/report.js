const fs = require("node:fs");
const path = require("node:path");

const { buildCoverLetterDraft } = require("./coverLetter");
// Loading matcher first populates the global that tailor.js reads lazily.
require(path.join(__dirname, "../../job-application-chrome-extension/lib/matcher.js"));
const Tailor = require(path.join(__dirname, "../../job-application-chrome-extension/lib/tailor.js"));

function slugify(text) {
  return (text || "job")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 60);
}

function buildMarkdown(matches, meta) {
  const lines = [];
  lines.push(`# Job matches — ${new Date(meta.generatedAt).toUTCString()}`);
  lines.push("");
  lines.push(
    `Scanned **${meta.totalFetched}** postings from ${meta.sourcesSucceeded.length} source(s); **${matches.length}** cleared your filters (min score ${meta.filters.minScore}%).`
  );
  if (meta.newCount !== undefined) {
    lines.push("");
    lines.push(`**${meta.newCount}** of these are new since the last run.`);
  }
  if (meta.sourcesFailed.length > 0) {
    lines.push("");
    lines.push(`> Sources that failed this run: ${meta.sourcesFailed.map((s) => `\`${s.id}\` (${s.error})`).join(", ")}`);
  }
  lines.push("");
  lines.push("You apply to these yourself — open the link and use the Chrome extension's floating widget to fill the form in a few seconds.");
  lines.push("");

  if (matches.length === 0) {
    lines.push("_No matches cleared the filters this run. Try lowering `filters.minScore` or widening `filters.titleInclude` in `job-finder/config.json`._");
    return lines.join("\n");
  }

  lines.push("| # | Score | Role | Company | Location | Source | New? | Link |");
  lines.push("|---|-------|------|---------|----------|--------|------|------|");
  matches.forEach((job, idx) => {
    const cell = (v) => String(v || "").replace(/\|/g, "\\|").replace(/\n/g, " ");
    lines.push(
      `| ${idx + 1} | ${job.score}% | ${cell(job.title)} | ${cell(job.company)} | ${cell(job.location)} | ${job.source} | ${
        job.isNew ? "yes" : ""
      } | [apply](${job.url}) |`
    );
  });

  lines.push("");
  lines.push("## Details");
  lines.push("");
  matches.forEach((job, idx) => {
    lines.push(`### ${idx + 1}. ${job.title} — ${job.company} (${job.score}%)`);
    lines.push("");
    lines.push(`- Location: ${job.location || "n/a"}`);
    lines.push(`- Posted: ${job.postedAt ? new Date(job.postedAt).toISOString().slice(0, 10) : "unknown"}`);
    lines.push(`- Source: ${job.source}`);
    lines.push(`- Apply: ${job.url}`);
    lines.push(`- Matches your resume: ${(job.matched || []).join(", ") || "n/a"}`);
    lines.push(`- In posting, not in your resume: ${(job.missing || []).join(", ") || "n/a"}`);
    lines.push("");
  });

  if (meta.attributions && meta.attributions.length > 0) {
    lines.push("---");
    lines.push("");
    meta.attributions.forEach((a) => lines.push(`_${a}_`));
  }

  return lines.join("\n");
}

function writeOutputs(outputDir, matches, meta, config) {
  fs.mkdirSync(outputDir, { recursive: true });

  fs.writeFileSync(path.join(outputDir, "matches.json"), JSON.stringify({ meta, matches }, null, 2));
  fs.writeFileSync(path.join(outputDir, "matches.md"), buildMarkdown(matches, meta));

  let draftCount = 0;
  if (config.output.generateCoverLetterDrafts && matches.length > 0) {
    const draftsDir = path.join(outputDir, "cover-letter-drafts");
    fs.mkdirSync(draftsDir, { recursive: true });
    matches.slice(0, config.output.draftsForTopN).forEach((job, idx) => {
      const filename = `${String(idx + 1).padStart(2, "0")}-${slugify(`${job.company}-${job.title}`)}.md`;
      fs.writeFileSync(path.join(draftsDir, filename), buildCoverLetterDraft(meta.profile, job));
      draftCount++;
    });
  }

  let tailoredCount = 0;
  if (config.output.generateTailoredResumes && matches.length > 0) {
    const tailoredDir = path.join(outputDir, "tailored-resumes");
    fs.mkdirSync(tailoredDir, { recursive: true });
    matches.slice(0, config.output.tailoredResumesForTopN).forEach((job, idx) => {
      const jobText = `${job.title}\n${job.description || ""}`;
      const plan = Tailor.tailorForRole(meta.profile, jobText, { companyName: job.company });
      const filename = `${String(idx + 1).padStart(2, "0")}-${slugify(`${job.company}-${job.title}`)}.md`;
      fs.writeFileSync(path.join(tailoredDir, filename), Tailor.renderTailoredResume(meta.profile, job, plan));
      tailoredCount++;
    });
  }

  return { draftCount, tailoredCount };
}

async function sendWebhook(matches, meta) {
  const url = process.env.JOB_ALERT_WEBHOOK;
  if (!url) return false;

  const top = matches.slice(0, 10);
  const summary = [
    `*${matches.length} job match(es)* from ${meta.totalFetched} postings scanned` +
      (meta.newCount !== undefined ? ` — ${meta.newCount} new` : ""),
    ...top.map((j) => `• ${j.score}% — ${j.title} @ ${j.company} — ${j.url}`),
    matches.length > top.length ? `…and ${matches.length - top.length} more in the pipeline artifacts.` : "",
  ]
    .filter(Boolean)
    .join("\n");

  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: summary, content: summary }),
    });
    return res.ok;
  } catch (err) {
    console.warn(`Webhook post failed: ${err.message}`);
    return false;
  }
}

module.exports = { buildMarkdown, writeOutputs, sendWebhook, slugify };
