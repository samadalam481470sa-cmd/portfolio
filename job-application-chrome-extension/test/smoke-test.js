#!/usr/bin/env node
/**
 * End-to-end smoke test: loads the extension in a real Chromium instance,
 * serves a fake application form, and asserts that the floating widget
 * injects and actually fills the form.
 *
 * This exists because the failure modes that matter here (a bad manifest, a
 * renamed injected file, a broken zip layout) don't show up in unit tests —
 * they only appear when a browser tries to load the thing.
 *
 * Requires Playwright's Chromium:
 *   npm install --no-save playwright && npx playwright install chromium
 *
 * Usage:
 *   node job-application-chrome-extension/test/smoke-test.js [path-to-extension-dir]
 *
 * Defaults to this extension's source folder. Pass an unzipped release
 * folder to verify a built package instead.
 */
const http = require("node:http");
const path = require("node:path");
const os = require("node:os");
const fs = require("node:fs");

const EXTENSION_DIR = process.argv[2] || path.join(__dirname, "..");

const FORM_HTML = `<!DOCTYPE html><html><head><title>Apply: Software Engineer</title></head>
<body><h1>Apply: Software Engineer</h1>
<p>We are hiring a software engineer with Python and SQL experience.</p>
<form>
<label for="fn">First Name</label><input id="fn" name="first_name" type="text">
<label for="ln">Last Name</label><input id="ln" name="last_name" type="text">
<label for="em">Email</label><input id="em" name="email" type="email">
<label for="ph">Phone</label><input id="ph" name="phone" type="tel">
<label for="li">LinkedIn Profile</label><input id="li" name="linkedin" type="text">
<label for="cl">Cover Letter</label><textarea id="cl" name="cover_letter"></textarea>
<fieldset><legend>Are you legally authorized to work in the United States?</legend>
<label><input type="radio" name="auth" value="yes"> Yes</label>
<label><input type="radio" name="auth" value="no"> No</label></fieldset>
</form></body></html>`;

const PROFILE = {
  name: "Test Candidate",
  firstName: "Test",
  lastName: "Candidate",
  email: "test@example.com",
  phone: "555-555-0100",
  location: "Dallas, TX",
  linkedin: "linkedin.com/in/testcandidate",
  website: "",
  skills: ["Python", "SQL", "JavaScript"],
  summary: "Software engineering intern with Python and SQL experience.",
  experience: "Software Engineer Intern\n• Built web platform features.",
  projects: "",
  bullets: ["Built web platform features."],
  rawText: "Test Candidate Python SQL JavaScript software engineer intern web platform",
};

const QA = [{ question: "Are you legally authorized to work in the United States?", answer: "Yes" }];

const failures = [];
function check(name, condition, detail) {
  if (condition) {
    console.log(`  PASS  ${name}`);
  } else {
    console.log(`  FAIL  ${name}${detail ? ` — ${detail}` : ""}`);
    failures.push(name);
  }
}

async function main() {
  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch (err) {
    console.error("Playwright is not installed. Run:\n  npm install --no-save playwright && npx playwright install chromium");
    process.exit(2);
  }

  if (!fs.existsSync(path.join(EXTENSION_DIR, "manifest.json"))) {
    console.error(`No manifest.json in ${EXTENSION_DIR} — is that the right folder?`);
    process.exit(2);
  }

  const server = http.createServer((req, res) => {
    res.writeHead(200, { "Content-Type": "text/html" });
    res.end(FORM_HTML);
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const url = `http://127.0.0.1:${server.address().port}/`;

  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "resume-fit-smoke-"));
  const context = await chromium.launchPersistentContext(userDataDir, {
    channel: "chromium",
    headless: true,
    args: [`--disable-extensions-except=${EXTENSION_DIR}`, `--load-extension=${EXTENSION_DIR}`, "--no-sandbox"],
  });

  const pageErrors = [];

  try {
    console.log(`Loading extension from ${EXTENSION_DIR}`);
    let sw = context.serviceWorkers()[0];
    if (!sw) sw = await context.waitForEvent("serviceworker", { timeout: 20000 }).catch(() => null);
    check("extension loads (service worker starts)", !!sw);
    if (!sw) return;

    const extId = new URL(sw.url()).host;

    // Seed storage the same way the popup's Save button would.
    const popup = await context.newPage();
    popup.on("pageerror", (e) => pageErrors.push(`popup: ${e.message}`));
    await popup.goto(`chrome-extension://${extId}/popup.html`);
    await popup.evaluate(
      ([profile, qa]) =>
        new Promise((resolve) => chrome.storage.local.set({ resumeProfile: profile, customAnswers: qa }, resolve)),
      [PROFILE, QA]
    );
    check("popup page loads without script errors", pageErrors.length === 0, pageErrors.join("; "));

    const page = await context.newPage();
    page.on("pageerror", (e) => pageErrors.push(`content: ${e.message}`));
    await page.goto(url, { waitUntil: "networkidle" });
    await page.waitForTimeout(1000);

    const widgetPresent = await page.evaluate(() => !!document.getElementById("resume-fit-widget-root"));
    check("floating widget injects into the page", widgetPresent);
    if (!widgetPresent) return;

    await page.evaluate(() => {
      const shadow = document.getElementById("resume-fit-widget-root").shadowRoot;
      shadow.querySelector(".bubble").click();
    });
    await page.waitForTimeout(200);
    await page.evaluate(() => {
      const shadow = document.getElementById("resume-fit-widget-root").shadowRoot;
      shadow.querySelector("#fullAutofillBtn").click();
    });
    await page.waitForTimeout(1200);

    const v = await page.evaluate(() => ({
      firstName: document.getElementById("fn").value,
      lastName: document.getElementById("ln").value,
      email: document.getElementById("em").value,
      phone: document.getElementById("ph").value,
      linkedin: document.getElementById("li").value,
      coverLetter: document.getElementById("cl").value,
      authYes: document.querySelector('input[name="auth"][value="yes"]').checked,
      authNo: document.querySelector('input[name="auth"][value="no"]').checked,
    }));

    check("fills first name", v.firstName === PROFILE.firstName, v.firstName);
    check("fills last name", v.lastName === PROFILE.lastName, v.lastName);
    check("fills email", v.email === PROFILE.email, v.email);
    check("fills phone", v.phone === PROFILE.phone, v.phone);
    check("fills LinkedIn", v.linkedin === PROFILE.linkedin, v.linkedin);
    check("drafts a cover letter from resume content", v.coverLetter.includes(PROFILE.summary), v.coverLetter.slice(0, 60));
    check("answers the radio question from saved Q&A", v.authYes === true && v.authNo === false);

    const status = await page.evaluate(() => {
      const shadow = document.getElementById("resume-fit-widget-root").shadowRoot;
      return shadow.querySelector("#widgetStatus").textContent;
    });
    check("widget reports a result summary", /Filled:\s*\d+/.test(status), status);
    check("no uncaught page errors", pageErrors.length === 0, pageErrors.join("; "));
  } finally {
    await context.close();
    server.close();
    fs.rmSync(userDataDir, { recursive: true, force: true });
  }
}

main()
  .then(() => {
    console.log("");
    if (failures.length > 0) {
      console.error(`SMOKE TEST FAILED — ${failures.length} check(s) failed.`);
      process.exit(1);
    }
    console.log("SMOKE TEST PASSED");
  })
  .catch((err) => {
    console.error("Harness error:", err.message);
    process.exit(1);
  });
