# Resume-Fit Autofill Assistant (Chrome Extension)

A Chrome extension that helps with job applications **without** crossing into
fraud or platform-abuse territory. It:

- Lets you save your **real** resume (paste text or upload a `.txt` file), parsed
  into structured fields you can review and correct.
- Lets you pre-write your **own answers** to recurring questions (work
  authorization, visa sponsorship, salary expectations, notice period, etc.)
  once, in the **Q&A** tab. Whenever a matching question shows up on a page —
  even reworded — it's filled in with your exact wording. This works for text
  fields, dropdowns, checkboxes, and yes/no radio-button questions.
- On any job page, autofills form fields it can confidently match (name, email,
  phone, links, skills, your saved Q&A answers, etc.) using **only** your real
  data — never invented facts.
- For open-ended prompts with no saved Q&A answer (like "Why do you want to
  work here?" or a cover-letter box), **drafts a short suggestion** built only
  from your real resume content (summary/skills/experience). Drafts are
  highlighted in blue and clearly marked "review & personalize before
  submitting" — they're a starting point, not a final answer, and nothing is
  ever submitted automatically.
- Highlights anything it still can't confidently handle — like legally
  sensitive checkboxes/radios you haven't pre-answered — in yellow, so **you**
  answer them yourself.
- Shows a **job-fit score**: keyword overlap between your resume and the
  posting's description, plus which keywords are matched vs. missing.
- Never auto-submits an application and never simulates mouse movement or any
  other bot-detection evasion.
- Includes a small **floating helper bubble** ("RF") that appears in the
  corner of every page (draggable, and can be turned off from the popup).
  Click it for one-click actions: Fill Name, Fill Email, Fill Phone, and Full
  Autofill + Job Score — all using the engine described above.

## What this deliberately does NOT do

This project intentionally does **not** implement:

- Autonomous/continuous submission of applications without a human reviewing
  each one.
- Fabricating answers to questions it doesn't know (work authorization,
  salary expectations, cover letters, etc.) — these are always left blank and
  flagged for you.
- Any mouse-movement simulation or other technique aimed at evading a site's
  bot/anti-fraud detection.

Most job boards and ATS platforms (LinkedIn, Indeed, Greenhouse, Lever,
Workday, etc.) prohibit automated/scripted account activity in their Terms of
Service, and providing false information on an application can constitute
fraud. This tool is designed to stay on the right side of both: it's a
review-and-autofill assistant, not an autonomous applicant.

## Install on macOS

This portfolio does not include a prebuilt `resume-fit-assistant.zip`. Load this folder unpacked.

1. Go to `chrome://extensions`.
2. Toggle on **Developer mode** (top-right switch). Without this, the
   **Load unpacked** button doesn't appear at all.
3. Click **Load unpacked**.
4. Select the **`job-application-chrome-extension` folder itself** — not its parent
   folder, and not a file inside it. If Chrome says *"Manifest file is
   missing or unreadable"*, you selected the wrong level; open the folder and
   confirm you can see `manifest.json` directly inside it.
5. Pin the extension: puzzle-piece icon in the toolbar → pin "Resume-Fit
   Autofill Assistant".

### Set it up

1. Click the extension icon → **Resume** tab → paste or upload your resume →
   **Save Resume Profile**.
2. Optional but worth it: **Q&A** tab → add your answers to recurring
   questions (work authorization, salary expectations…) → **Save Q&A**.
3. On any application page, either use the popup's **Fill & Score** tab, or
   click the floating **"RF"** bubble in the page corner.

### Rebuilding the zip

From the portfolio root:

```bash
node newport-acquisition-crm/scripts/build-extension.js
```

This validates the package before zipping — it checks the manifest, confirms
every file referenced by the manifest, by `popup.html`, and by
`chrome.scripting.executeScript` actually exists, and syntax-checks all JS.
It then produces a zip containing a single top-level `resume-fit-assistant/`
folder, so there's no ambiguity about what to select in Chrome.

### Verifying it actually works

```bash
npm install --no-save playwright && npx playwright install chromium
node job-application-chrome-extension/test/smoke-test.js
```

This loads the extension in a real Chromium, serves a fake application form,
and asserts the widget injects and fills first/last name, email, phone,
LinkedIn, a drafted cover letter, and a saved Q&A radio answer. Pass a path
to test a built package instead of the source folder:

```bash
node job-application-chrome-extension/test/smoke-test.js ~/Downloads/resume-fit-assistant
```

## File structure

```
job-application-chrome-extension/
├── manifest.json          # Manifest V3 config
├── popup.html/.css/.js    # Resume + Q&A input UI, "Analyze & Fill This Page" trigger
├── content.js             # Injected on demand (popup button / context menu)
├── widget.js              # Always-on floating "RF" bubble injected on every page
├── background.js          # Service worker; adds a right-click "Fill this page" shortcut
├── lib/
│   ├── resumeParser.js    # Heuristic resume-text -> structured profile parser
│   ├── matcher.js         # Resume vs. job-description keyword overlap scoring
│   ├── tailor.js          # Per-role skill/bullet prioritization + gap detection
│   └── autofillEngine.js  # Shared field-matching/autofill logic
└── test/smoke-test.js     # Loads the extension in real Chromium and fills a form
```

## The floating widget

A small draggable "RF" bubble appears in the bottom-right corner of every
page (turn it off from the popup's **Fill & Score** tab if you don't want
it). Clicking it opens a panel with:

- **Fill Name / Fill Email / Fill Phone** — fills every matching field on the
  page with that piece of your saved resume data.
- **Full Autofill + Job Score** — runs the same engine as the popup's
  "Analyze & Fill This Page" button.

The widget only fills fields when you click a button — it never runs
automatically in the background, never submits anything, and never moves
your mouse or clicks other page elements.

## Notes & limitations

- PDF/Word resumes aren't parsed directly — open the file, copy the text, and
  paste it into the extension (or export to `.txt` first).
- Field matching is heuristic (label/placeholder/name keyword matching). Always
  review a page after auto-fill before applying.
- The job-fit score is a simple keyword-overlap heuristic, not a semantic or
  ML-based match — treat it as a quick signal, not ground truth.
- Content scripts only run when you explicitly click "Analyze & Fill This
  Page" (or the right-click menu item) — nothing runs in the background or on
  page load.
