# Job Finder — scheduled discovery & resume matching

A dependency-free Node script that runs on a GitLab CI schedule (every few
hours, on GitLab's runners, so it keeps working with your laptop closed). Each
run it:

1. Pulls postings from public job APIs (Greenhouse, Lever, Ashby, Remote OK,
   plus optional Adzuna and USAJOBS with free API keys).
2. Scores every posting against your resume using the **same** keyword-overlap
   logic the Chrome extension uses on-page, so a score means the same thing in
   both places.
3. Filters by your title/location/recency/score rules.
4. Publishes downloadable artifacts:
   - `output/matches.md` — ranked shortlist with apply links, matched keywords,
     and what's new since the last run.
   - `output/matches.json` — the same data, machine-readable.
   - `output/tailored-resumes/` — per-role "tweak your resume" plans: which of
     **your existing** skills and bullets to lead with, plus an honest gap list.
   - `output/cover-letter-drafts/` — per-role cover letter drafts built only
     from your real resume content, with `[BRACKETED]` prompts you must fill in.
5. Optionally posts a summary to a Slack/Discord webhook.

## What it does not do

It stops at discovery and preparation. It does not submit applications, create
accounts, log into job boards, or drive a browser. Two reasons:

- Automated/scripted application submission violates the Terms of Service of
  effectively every job board and ATS, and is a good way to get your accounts
  banned mid-search.
- Auto-submitting means submitting answers nobody verified. Every generated
  artifact here is a *draft for you to review* precisely so nothing inaccurate
  goes out under your name.

You open the links it produces and apply yourself. The Chrome extension in
`../job-application-chrome-extension/` makes each of those applications take seconds instead of
minutes.

## Setup

### 1. Provide your resume

Pick one (in priority order):

| Method | How | Notes |
|---|---|---|
| `RESUME_TEXT` CI variable | CI/CD → Variables → add `RESUME_TEXT`, paste resume text | **Recommended.** Keeps contact details out of a public repo. |
| `RESUME_FILE` CI variable | Add a "File" type variable; the script reads the path | Also keeps it out of git. |
| `job-finder/resume.txt` | Commit it | The committed copy is placeholders only. Put your real resume in `resume.local.txt` or `RESUME_TEXT`. |

A git-ignored `job-finder/resume.local.txt` is also available for keeping a
full local copy with real contact details.

### 2. Tune `config.json`

```jsonc
{
  "sources": {
    "greenhouse": { "enabled": true, "boards": ["stripe", "figma"] },  // board slug from boards.greenhouse.io/<slug>
    "lever":      { "enabled": true, "companies": ["plaid"] },          // slug from jobs.lever.co/<slug>
    "ashby":      { "enabled": true, "boards": ["linear"] },            // slug from jobs.ashbyhq.com/<slug>
    "remoteok":   { "enabled": true, "tags": [] },
    "adzuna":     { "enabled": false, "country": "us", "what": "software engineer", "where": "YOUR_CITY" },
    "usajobs":    { "enabled": false, "keyword": "information technology" }
  },
  "filters": {
    "titleInclude": ["software engineer", "data analyst"],  // empty = allow all
    "titleExclude": ["senior", "staff", "manager"],
    "locationInclude": [],                                   // empty = allow all
    "locationExclude": ["India", "Dublin"],                  // skip places you can't take
    "remoteOnly": false,
    "minScore": 18,          // scores are relative rankings, not absolute quality
    "maxResults": 40,
    "postedWithinDays": 30
  }
}
```

Finding company slugs: open a company's careers page and look at the URL —
`boards.greenhouse.io/stripe` → `stripe`, `jobs.lever.co/plaid` → `plaid`,
`jobs.ashbyhq.com/linear` → `linear`. Invalid or migrated slugs are skipped
with a warning rather than failing the run.

### 3. Schedule it

GitLab → **CI/CD → Schedules → New schedule**. Cron `0 */6 * * *` runs it every
6 hours. Then grab the artifacts from the pipeline page (or wire up
`JOB_ALERT_WEBHOOK` to get pinged).

To run it on your own Mac instead, register a self-hosted GitLab Runner, or
just run it locally:

```bash
cd job-finder
RESUME_FILE=./resume.local.txt node src/index.js
```

### Optional CI variables

| Variable | Purpose |
|---|---|
| `JOB_ALERT_WEBHOOK` | Slack/Discord incoming webhook for a per-run summary |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Enables the Adzuna source |
| `USAJOBS_API_KEY` / `USAJOBS_EMAIL` | Enables the USAJOBS source |
| `JOB_FINDER_USER_AGENT` | Override the User-Agent sent to APIs |

## Multi-user mode

For a self-hostable web service where any user can upload a resume and get
continuously-updated matches, see [`../newport-acquisition-crm/web/README.md`](../newport-acquisition-crm/web/README.md). The
CLI entry point for that path is:

```bash
node src/multiuser.js   # fetch once, score every uploaded resume
```

## Development

```bash
cd job-finder
npm test              # parser, scoring, filters, tailoring, report rendering
node src/index.js     # a real single-user run (hits live APIs)
node src/multiuser.js # a real multi-user run (hits live APIs)
```

## Adding a source

Create `src/sources/<name>.js` exporting `{ id, label, fetchJobs(config) }`
that returns normalized postings:

```js
{ id, source, title, company, location, url, description, postedAt }
```

Register it in `src/sources/index.js`. Only add sources with an official
public API — don't add scrapers for sites that prohibit automated access.

## File structure

```
job-finder/
├── config.json           # sources + filters (edit this)
├── resume.txt            # placeholder resume used for matching (put yours in resume.local.txt)
├── package.json
├── src/
│   ├── index.js          # orchestrates a run
│   ├── config.js         # config + resume resolution
│   ├── score.js          # scoring + filtering (reuses the extension's matcher)
│   ├── coverLetter.js    # cover-letter drafts
│   ├── report.js         # markdown/json/webhook output + tailored resumes
│   ├── http.js           # polite fetch (UA, timeout, backoff)
│   ├── html.js           # HTML -> text
│   └── sources/          # one module per job API
└── test/pipeline.test.js
```
