/**
 * Small polite HTTP helper: identifies itself with a real User-Agent,
 * times out, and backs off on 429/5xx instead of hammering an API.
 */
const DEFAULT_USER_AGENT =
  process.env.JOB_FINDER_USER_AGENT ||
  "resume-fit-job-finder/1.0 (personal job search; https://gitlab.com/)";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function fetchJson(url, options = {}) {
  const { headers = {}, timeoutMs = 20000, retries = 2, retryDelayMs = 1000 } = options;
  let lastError;

  for (let attempt = 0; attempt <= retries; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(url, {
        headers: {
          "User-Agent": DEFAULT_USER_AGENT,
          Accept: "application/json",
          ...headers,
        },
        signal: controller.signal,
      });

      if (res.status === 429 || res.status >= 500) {
        throw new Error(`HTTP ${res.status} (retryable) for ${url}`);
      }
      if (!res.ok) {
        const body = await res.text().catch(() => "");
        const err = new Error(`HTTP ${res.status} for ${url}: ${body.slice(0, 200)}`);
        err.fatal = true;
        throw err;
      }
      return await res.json();
    } catch (err) {
      lastError = err;
      if (err.fatal) break;
      if (attempt < retries) await sleep(retryDelayMs * Math.pow(2, attempt));
    } finally {
      clearTimeout(timer);
    }
  }

  throw lastError;
}

module.exports = { fetchJson, sleep, DEFAULT_USER_AGENT };
