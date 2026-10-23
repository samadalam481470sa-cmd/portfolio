/**
 * Server-rendered HTML for the self-hostable job-finder web service.
 * Dependency-free: plain template strings with escaping.
 */
function esc(str) {
  return String(str == null ? "" : str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const STYLE = `
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    max-width: 760px; margin: 0 auto; padding: 24px; line-height: 1.5; color: #1a1a2e; background: #fafafe; }
  h1 { font-size: 22px; margin-bottom: 4px; }
  .tagline { color: #6b7280; margin-top: 0; font-size: 14px; }
  .card { background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px; margin: 16px 0; }
  label { display: block; font-weight: 600; font-size: 13px; margin: 12px 0 4px; }
  input[type=text], textarea { width: 100%; padding: 9px 10px; border: 1px solid #d1d5db; border-radius: 8px;
    font-size: 14px; font-family: inherit; }
  textarea { resize: vertical; }
  .hint { font-size: 12px; color: #9ca3af; margin: 4px 0 0; }
  .row { display: flex; gap: 12px; flex-wrap: wrap; }
  .row > div { flex: 1; min-width: 180px; }
  button { background: #4338ca; color: #fff; border: none; border-radius: 8px; padding: 11px 18px;
    font-size: 14px; font-weight: 600; cursor: pointer; margin-top: 16px; }
  button:hover { background: #3730a3; }
  .btn-secondary { background: #e5e7eb; color: #1a1a2e; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid #eef0f3; vertical-align: top; }
  th { color: #6b7280; font-weight: 600; }
  .score { font-weight: 700; color: #4338ca; }
  .chip { display: inline-block; font-size: 11px; padding: 2px 7px; border-radius: 10px; margin: 2px; }
  .chip.ok { background: #d1fae5; color: #065f46; }
  .chip.gap { background: #fee2e2; color: #991b1b; }
  a { color: #4338ca; }
  .notice { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 10px 12px;
    font-size: 13px; color: #92400e; }
  .error { background: #fef2f2; border-color: #fecaca; color: #991b1b; }
  footer { margin-top: 32px; font-size: 12px; color: #9ca3af; }
`;

function layout(title, body) {
  return `<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title><style>${STYLE}</style></head>
<body>${body}
<footer>This tool finds and ranks jobs and prepares drafts for you to review. It never submits
applications, creates accounts, or acts on a job site on your behalf — you open each link and apply
yourself. Nothing is invented: gaps are shown as gaps.</footer>
</body></html>`;
}

function uploadPage({ error } = {}) {
  return layout(
    "Resume Job Finder",
    `<h1>Resume Job Finder</h1>
<p class="tagline">Upload your resume once. A scheduler keeps scanning public job boards and ranks the best matches for you, with per-role resume tweaks and cover-letter drafts to review.</p>
${error ? `<div class="notice error">${esc(error)}</div>` : ""}
<div class="card">
<form method="POST" action="/upload">
  <label for="label">A name or label for you (optional)</label>
  <input type="text" id="label" name="label" placeholder="e.g. Sam — frontend search" maxlength="80">

  <label for="resumeFile">Upload resume (.txt) — or paste below</label>
  <input type="file" id="resumeFile" accept=".txt,.md,text/plain">
  <p class="hint">PDF/Word? Open it, copy the text, and paste it below.</p>

  <label for="resumeText">Resume text</label>
  <textarea id="resumeText" name="resumeText" rows="12" required
    placeholder="Paste your full resume text here"></textarea>

  <div class="row">
    <div>
      <label for="titleInclude">Job titles to include</label>
      <input type="text" id="titleInclude" name="titleInclude"
        placeholder="software engineer, data analyst">
      <p class="hint">Comma-separated. Leave blank to allow all.</p>
    </div>
    <div>
      <label for="titleExclude">Titles to exclude</label>
      <input type="text" id="titleExclude" name="titleExclude"
        placeholder="senior, manager, director">
    </div>
  </div>
  <div class="row">
    <div>
      <label for="locationExclude">Locations to exclude</label>
      <input type="text" id="locationExclude" name="locationExclude"
        placeholder="India, Dublin, London">
    </div>
    <div>
      <label for="minScore">Minimum match score</label>
      <input type="text" id="minScore" name="minScore" placeholder="18">
    </div>
  </div>
  <label style="font-weight:400;font-size:13px;">
    <input type="checkbox" name="remoteOnly" value="1" style="width:auto;"> Remote roles only
  </label>

  <button type="submit">Save my resume &amp; start matching</button>
</form>
</div>
<script>
  document.getElementById("resumeFile").addEventListener("change", function (e) {
    var file = e.target.files[0];
    if (!file) return;
    var reader = new FileReader();
    reader.onload = function () { document.getElementById("resumeText").value = String(reader.result || ""); };
    reader.readAsText(file);
  });
</script>`
  );
}

function matchesTable(matches) {
  if (!matches || matches.length === 0) {
    return `<p class="hint">No matches yet. The next scheduled scan will fill this in, or ask the operator to trigger a run.</p>`;
  }
  const rows = matches
    .slice(0, 40)
    .map(
      (j, i) => `<tr>
      <td>${i + 1}</td>
      <td class="score">${esc(j.score)}%</td>
      <td><a href="${esc(j.url)}" target="_blank" rel="noopener noreferrer">${esc(j.title)}</a><br>
        <span class="hint">${esc(j.company)}${j.location ? " · " + esc(j.location) : ""} · ${esc(j.source)}</span></td>
    </tr>`
    )
    .join("");
  return `<table><thead><tr><th>#</th><th>Score</th><th>Role</th></tr></thead><tbody>${rows}</tbody></table>`;
}

function resultsPage(user, data) {
  const matches = data && data.matches ? data.matches : [];
  const meta = (data && data.meta) || {};
  const generated = meta.generatedAt ? new Date(meta.generatedAt).toUTCString() : "not yet run";

  return layout(
    `Matches — ${user.label}`,
    `<h1>Your job matches</h1>
<p class="tagline">${esc(user.label)} · last updated: ${esc(generated)}</p>
<div class="notice">Bookmark this page — the link is your private key to your results. The scheduler
refreshes it automatically every cycle.</div>
<div class="card">
  <p><strong>${matches.length}</strong> match(es)${
      meta.totalFetched ? ` from ${esc(meta.totalFetched)} postings scanned` : ""
    }. Open a link, then use the Chrome extension's floating widget to fill the form fast.</p>
  ${matchesTable(matches)}
</div>
<p><a href="/">&larr; Upload a different resume</a></p>`
  );
}

module.exports = { esc, layout, uploadPage, resultsPage };
