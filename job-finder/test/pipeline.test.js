const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");

const ResumeParser = require("../../job-application-chrome-extension/lib/resumeParser.js");
require("../../job-application-chrome-extension/lib/matcher.js");
const Tailor = require("../../job-application-chrome-extension/lib/tailor.js");

const { scoreJobs, passesFilters, dedupeJobs, isRemote } = require("../src/score");
const { stripHtml } = require("../src/html");
const { buildCoverLetterDraft } = require("../src/coverLetter");
const { buildMarkdown, slugify } = require("../src/report");
const { DEFAULT_FILTERS } = require("../src/config");

const RESUME = fs.readFileSync(path.join(__dirname, "../resume.txt"), "utf8");

const JOB_STRONG = {
  id: "greenhouse:acme:1",
  source: "greenhouse",
  title: "Software Engineer I",
  company: "Acme",
  location: "Dallas, TX",
  url: "https://example.com/1",
  description:
    "We are hiring a software engineer to work in Python and SQL on our AWS data platform. " +
    "You will build back-end features, integrate data flows, and work with Tableau dashboards. " +
    "JavaScript experience is a plus. Kubernetes and Rust are used by the platform team.",
  postedAt: new Date().toISOString(),
};

const JOB_WEAK = {
  id: "lever:other:2",
  source: "lever",
  title: "Senior Marketing Manager",
  company: "Other",
  location: "New York, NY",
  url: "https://example.com/2",
  description: "Lead brand campaigns, manage agencies, own paid social budgets and creative strategy.",
  postedAt: new Date().toISOString(),
};

test("resume parser handles a real-world resume format", () => {
  const profile = ResumeParser.parseResume(RESUME);

  assert.strictEqual(profile.name, "YOUR_NAME");
  assert.strictEqual(profile.linkedin, "linkedin.com/in/YOUR_LINKEDIN");
  assert.strictEqual(profile.location, "YOUR_CITY, YOUR_STATE");

  // "Category: a, b, c" lines must not leak the category label into skills.
  assert.ok(profile.skills.includes("Python"), "should extract Python");
  assert.ok(profile.skills.includes("SQL"), "should extract SQL");
  assert.ok(
    !profile.skills.some((s) => /programming languages/i.test(s)),
    "category labels should be stripped from skills"
  );

  // PROJECTS must terminate the WORK EXPERIENCE section.
  assert.ok(profile.experience.includes("YOUR_EMPLOYER"));
  assert.ok(!profile.experience.includes("YOUR_PROJECT_ORG"), "projects should not bleed into experience");
  assert.ok(profile.projects.includes("YOUR_CLIENT"));

  // Bullets are pulled from both experience and projects.
  assert.ok(profile.bullets.length >= 5, `expected several bullets, got ${profile.bullets.length}`);
  assert.ok(profile.bullets.some((b) => b.startsWith("YOUR_BULLET")));
});

test("scoring ranks a relevant posting above an irrelevant one", () => {
  const filters = { ...DEFAULT_FILTERS, minScore: 0, titleInclude: [], titleExclude: [] };
  const { matches } = scoreJobs([JOB_WEAK, JOB_STRONG], RESUME, filters);

  assert.strictEqual(matches.length, 2);
  assert.strictEqual(matches[0].id, JOB_STRONG.id, "the software role should rank first");
  assert.ok(matches[0].score > matches[1].score);
  assert.ok(matches[0].matched.length > 0, "should report matched keywords");
});

test("filters exclude by title and enforce minimum score", () => {
  const filters = {
    ...DEFAULT_FILTERS,
    titleInclude: ["engineer"],
    titleExclude: ["senior"],
    minScore: 0,
  };
  assert.ok(passesFilters(JOB_STRONG, filters));
  assert.ok(!passesFilters(JOB_WEAK, filters), "non-engineer title should be filtered out");
  assert.ok(!passesFilters({ ...JOB_STRONG, title: "Senior Engineer" }, filters), "excluded word should win");

  const highBar = { ...DEFAULT_FILTERS, minScore: 99, titleInclude: [], titleExclude: [] };
  assert.strictEqual(scoreJobs([JOB_STRONG], RESUME, highBar).matches.length, 0);
});

test("postedWithinDays drops stale postings", () => {
  const old = { ...JOB_STRONG, postedAt: new Date(Date.now() - 90 * 86400000).toISOString() };
  const filters = { ...DEFAULT_FILTERS, postedWithinDays: 30, titleInclude: [], titleExclude: [] };
  assert.ok(!passesFilters(old, filters));
  // Missing dates should not be silently discarded.
  assert.ok(passesFilters({ ...JOB_STRONG, postedAt: null }, filters));
});

test("remote detection and dedupe behave sanely", () => {
  assert.ok(isRemote({ location: "Remote - US", title: "Engineer", description: "" }));
  assert.ok(!isRemote({ location: "Dallas, TX", title: "Engineer", description: "we have offices" }));

  const dupes = [JOB_STRONG, { ...JOB_STRONG, id: "other:id" }, JOB_WEAK];
  assert.strictEqual(dedupeJobs(dupes).length, 2, "same company+title+url should collapse");
});

test("stripHtml decodes entities and removes markup", () => {
  const html = "&lt;p&gt;Build with Python &amp;amp; SQL&lt;/p&gt;&lt;script&gt;bad()&lt;/script&gt;";
  const text = stripHtml(html);
  assert.ok(text.includes("Python & SQL"), `got: ${text}`);
  assert.ok(!/script|bad\(\)/.test(text), "script contents must be removed");
});

test("tailoring only reorders real content and reports gaps honestly", () => {
  const profile = ResumeParser.parseResume(RESUME);
  const jobText = `${JOB_STRONG.title}\n${JOB_STRONG.description}`;
  const plan = Tailor.tailorForRole(profile, jobText);

  // Lead skills must be a subset of the candidate's own skills.
  plan.leadSkills.forEach((skill) => {
    assert.ok(profile.skills.includes(skill), `${skill} must come from the resume`);
  });
  assert.ok(plan.leadSkills.includes("Python"), "Python is in both resume and posting");

  // Lead bullets must be verbatim resume bullets.
  plan.leadBullets.forEach((bullet) => {
    assert.ok(profile.bullets.includes(bullet), "bullets must be verbatim from the resume");
  });

  // Gaps are surfaced, not silently added to the resume.
  const rendered = Tailor.renderTailoredResume(profile, { ...JOB_STRONG, score: plan.score }, plan);
  assert.ok(/do not fabricate/i.test(rendered));
  assert.ok(!/\bRust\b/.test(plan.leadSkills.join(" ")), "a skill absent from the resume must never be promoted");
});

test("cover letter draft uses real content and keeps placeholders", () => {
  const profile = ResumeParser.parseResume(RESUME);
  const job = { ...JOB_STRONG, score: 42, matched: ["python", "sql"], missing: ["kubernetes"] };
  const draft = buildCoverLetterDraft(profile, job);

  assert.ok(draft.includes("YOUR_NAME"), "should sign with the name on the resume");
  assert.ok(draft.includes("DRAFT"), "must be labelled a draft");
  assert.ok(/\[ADD 1-2 SENTENCES/.test(draft), "must leave an explicit placeholder for the human");
  assert.ok(/Don't claim skills you don't have/.test(draft));
});

test("markdown report renders rows and handles the empty case", () => {
  const meta = {
    generatedAt: new Date().toISOString(),
    totalFetched: 2,
    sourcesSucceeded: ["greenhouse"],
    sourcesFailed: [{ id: "lever", error: "HTTP 500" }],
    filters: DEFAULT_FILTERS,
    newCount: 1,
    attributions: ["Job data from Remote OK (https://remoteok.com)"],
  };
  const md = buildMarkdown([{ ...JOB_STRONG, score: 55, matched: ["python"], missing: [], isNew: true }], meta);
  assert.ok(md.includes("Software Engineer I"));
  assert.ok(md.includes("55%"));
  assert.ok(md.includes("lever"), "failed sources should be reported");
  assert.ok(md.includes("Remote OK"), "attribution should be preserved");

  const empty = buildMarkdown([], meta);
  assert.ok(/No matches cleared the filters/.test(empty));
});

test("slugify produces safe filenames", () => {
  assert.strictEqual(slugify("Acme Corp — Software Engineer I"), "acme-corp-software-engineer-i");
});
