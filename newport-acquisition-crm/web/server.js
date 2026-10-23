#!/usr/bin/env node
/**
 * Self-hostable, dependency-free web service for the job finder.
 *
 * One process does two things:
 *   1. Serves an upload page where ANY user can submit their resume and get a
 *      private results URL.
 *   2. Runs a built-in scheduler that re-scans public job boards every few
 *      hours and refreshes every user's ranked matches + drafts — i.e. it
 *      "runs 24/7" as long as the process is up (host it with systemd, pm2,
 *      Docker, a small VM, etc.).
 *
 * What it does NOT do: submit applications, create accounts, or interact with
 * any job site on a user's behalf, and it makes no attempt to hide automated
 * activity from anyone. It fetches from documented public job APIs and leaves
 * the applying to each human.
 *
 * This is a personal/self-host tool: a user's results URL contains an
 * unguessable id that acts as their capability token. There is no account
 * system. If you expose it publicly, put it behind your own auth/HTTPS and
 * remember you are then storing other people's resumes — handle that data
 * responsibly.
 */
const http = require("node:http");
const { URL } = require("node:url");

const { createUser, loadUser, readUserMatches, listUsers } = require("../../job-finder/src/users");
const { runOnce } = require("../../job-finder/src/multiuser");
const views = require("./views");

const PORT = Number(process.env.PORT || 3000);
const RUN_INTERVAL_HOURS = Number(process.env.RUN_INTERVAL_HOURS || 6);
const RUN_ON_START = process.env.RUN_ON_START !== "false";
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || "";
const MAX_BODY_BYTES = 256 * 1024;

let running = false;

async function runCycle(reason) {
  if (running) {
    console.log(`[scheduler] skip (${reason}) — a run is already in progress`);
    return { skipped: true };
  }
  running = true;
  const started = Date.now();
  console.log(`[scheduler] start (${reason})`);
  try {
    const summary = await runOnce();
    console.log(`[scheduler] done in ${((Date.now() - started) / 1000).toFixed(1)}s`);
    return summary;
  } catch (err) {
    console.error(`[scheduler] failed: ${err.message}`);
    return { error: err.message };
  } finally {
    running = false;
  }
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(new Error("Request body too large"));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

function parseForm(body) {
  const params = new URLSearchParams(body);
  const obj = {};
  for (const [key, value] of params.entries()) obj[key] = value;
  return obj;
}

function send(res, status, contentType, body) {
  res.writeHead(status, { "Content-Type": contentType, "X-Content-Type-Options": "nosniff" });
  res.end(body);
}

function sendHtml(res, status, html) {
  send(res, status, "text/html; charset=utf-8", html);
}

async function handle(req, res) {
  const url = new URL(req.url, `http://${req.headers.host || "localhost"}`);
  const { pathname } = url;

  if (req.method === "GET" && pathname === "/") {
    return sendHtml(res, 200, views.uploadPage());
  }

  if (req.method === "GET" && pathname === "/healthz") {
    return send(res, 200, "application/json", JSON.stringify({ ok: true, users: listUsers().length, running }));
  }

  if (req.method === "POST" && pathname === "/upload") {
    let form;
    try {
      form = parseForm(await readBody(req));
    } catch (err) {
      return sendHtml(res, 413, views.uploadPage({ error: err.message }));
    }
    try {
      const user = createUser({
        resumeText: form.resumeText,
        label: form.label,
        filters: {
          titleInclude: form.titleInclude,
          titleExclude: form.titleExclude,
          locationExclude: form.locationExclude,
          minScore: form.minScore,
          remoteOnly: form.remoteOnly === "1",
        },
      });
      res.writeHead(303, { Location: `/u/${user.id}` });
      return res.end();
    } catch (err) {
      return sendHtml(res, 400, views.uploadPage({ error: err.message }));
    }
  }

  const userMatch = pathname.match(/^\/u\/([A-Za-z0-9_-]+)$/);
  if (req.method === "GET" && userMatch) {
    const id = userMatch[1];
    const user = loadUser(id);
    if (!user) return sendHtml(res, 404, views.layout("Not found", "<h1>Not found</h1><p><a href='/'>Upload a resume</a></p>"));
    const data = readUserMatches(id);
    return sendHtml(res, 200, views.resultsPage(user, data));
  }

  // Operator-triggered run (useful for testing without waiting for the timer).
  if (req.method === "POST" && pathname === "/admin/run") {
    if (ADMIN_TOKEN && url.searchParams.get("token") !== ADMIN_TOKEN) {
      return send(res, 403, "application/json", JSON.stringify({ error: "forbidden" }));
    }
    runCycle("manual trigger");
    return send(res, 202, "application/json", JSON.stringify({ accepted: true }));
  }

  return sendHtml(res, 404, views.layout("Not found", "<h1>Not found</h1><p><a href='/'>Upload a resume</a></p>"));
}

function createServer() {
  return http.createServer((req, res) => {
    handle(req, res).catch((err) => {
      console.error(`Request error: ${err.message}`);
      if (!res.headersSent) send(res, 500, "text/plain", "Internal server error");
    });
  });
}

function startScheduler() {
  if (RUN_ON_START) {
    runCycle("startup");
  }
  const intervalMs = Math.max(1, RUN_INTERVAL_HOURS) * 60 * 60 * 1000;
  const timer = setInterval(() => runCycle("scheduled"), intervalMs);
  timer.unref?.();
  console.log(`[scheduler] will re-scan every ${RUN_INTERVAL_HOURS}h`);
  return timer;
}

if (require.main === module) {
  const server = createServer();
  server.listen(PORT, () => {
    console.log(`Job Finder web service listening on http://localhost:${PORT}`);
    console.log("Any user can upload a resume at that URL and get a private results link.");
    startScheduler();
  });
}

module.exports = { createServer, runCycle, startScheduler };
