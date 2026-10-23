const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

// Isolate all user data into a temp dir BEFORE requiring modules that read it.
const TMP_USERS = fs.mkdtempSync(path.join(os.tmpdir(), "jf-users-"));
process.env.JOB_FINDER_USERS_DIR = TMP_USERS;

const users = require("../../../job-finder/src/users");
const { createServer } = require("../server");

const RESUME = `Jane Dev
jane@example.com | 555-555-0100 | Dallas, TX

SKILLS
Python, SQL, JavaScript, React

EXPERIENCE
Software Engineer - Example Co
• Built web platform features in Python and React.`;

test.after(() => {
  fs.rmSync(TMP_USERS, { recursive: true, force: true });
});

// --- user store --------------------------------------------------------

test("createUser stores resume + profile and rejects junk", () => {
  const user = users.createUser({
    resumeText: RESUME,
    label: "Jane",
    filters: { titleInclude: "engineer, developer", minScore: "25", remoteOnly: true },
  });
  assert.ok(user.id, "returns an id");
  assert.strictEqual(user.label, "Jane");
  assert.deepStrictEqual(user.filters.titleInclude, ["engineer", "developer"]);
  assert.strictEqual(user.filters.minScore, 25);
  assert.strictEqual(user.filters.remoteOnly, true);

  const loaded = users.loadUser(user.id);
  assert.strictEqual(loaded.resumeText, RESUME);

  assert.throws(() => users.createUser({ resumeText: "too short" }), /too short/);
});

test("userDir rejects path traversal", () => {
  assert.throws(() => users.userDir("../../etc"), /Invalid user id/);
  assert.throws(() => users.userDir("a/b"), /Invalid user id/);
});

test("listUsers returns every uploaded resume", () => {
  const before = users.listUsers().length;
  users.createUser({ resumeText: RESUME, label: "Second" });
  assert.strictEqual(users.listUsers().length, before + 1);
});

// --- web server --------------------------------------------------------

function listen(server) {
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve(server.address().port)));
}

async function request(port, method, p, body) {
  const res = await fetch(`http://127.0.0.1:${port}${p}`, {
    method,
    redirect: "manual",
    headers: body ? { "Content-Type": "application/x-www-form-urlencoded" } : {},
    body,
  });
  const text = await res.text();
  return { status: res.status, headers: res.headers, text };
}

test("web server: upload flow and results page", async () => {
  const server = createServer();
  const port = await listen(server);
  try {
    const home = await request(port, "GET", "/");
    assert.strictEqual(home.status, 200);
    assert.ok(home.text.includes("Resume Job Finder"));
    assert.ok(home.text.includes("never submits"), "scope boundary is stated on the page");

    const form = new URLSearchParams({
      label: "Harness User",
      resumeText: RESUME,
      titleInclude: "engineer",
      minScore: "10",
    }).toString();
    const upload = await request(port, "POST", "/upload", form);
    assert.strictEqual(upload.status, 303, "successful upload redirects");
    const location = upload.headers.get("location");
    assert.match(location, /^\/u\/[A-Za-z0-9_-]+$/);

    const results = await request(port, "GET", location);
    assert.strictEqual(results.status, 200);
    assert.ok(results.text.includes("Harness User"));
    assert.ok(results.text.includes("Your job matches"));

    // A too-short resume is rejected with the form re-rendered, not a crash.
    const bad = await request(port, "POST", "/upload", new URLSearchParams({ resumeText: "nope" }).toString());
    assert.strictEqual(bad.status, 400);
    assert.ok(bad.text.includes("too short"));

    const missing = await request(port, "GET", "/u/doesnotexist");
    assert.strictEqual(missing.status, 404);

    const health = await request(port, "GET", "/healthz");
    assert.strictEqual(health.status, 200);
    assert.ok(JSON.parse(health.text).ok === true);
  } finally {
    server.close();
  }
});

test("web server: escapes HTML in user-supplied label (no injection)", async () => {
  const server = createServer();
  const port = await listen(server);
  try {
    const form = new URLSearchParams({
      label: "<script>alert(1)</script>",
      resumeText: RESUME,
    }).toString();
    const upload = await request(port, "POST", "/upload", form);
    const results = await request(port, "GET", upload.headers.get("location"));
    assert.ok(!results.text.includes("<script>alert(1)</script>"), "raw script tag must not appear");
    assert.ok(results.text.includes("&lt;script&gt;"), "label should be escaped");
  } finally {
    server.close();
  }
});
