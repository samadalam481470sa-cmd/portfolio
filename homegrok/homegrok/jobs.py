"""Job Scout: finds real, open internships and entry-level jobs from public sources.

Sources (public and free to use):
  * SimplifyJobs' community-maintained lists of internships and new-grad roles on GitHub,
    which link straight to each company's own application page;
  * the companies' own job boards (Greenhouse, Lever, Ashby, SmartRecruiters, Workday), which
    HomeGrok asks directly whether a posting is still open and what it says.

A posting is recommended or used only when it is listed as active, was posted recently, and the
company's own job board confirms it is still open, so closed and bogus listings are dropped.
Finding and checking jobs uses no Claude usage.
"""
import hashlib
import html
import json
import re
import sqlite3
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

LISTINGS = {
    "internship": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
    "new_grad": "https://raw.githubusercontent.com/SimplifyJobs/New-Grad-Positions/dev/.github/scripts/listings.json",
}
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) HomeGrok/1.0 (personal job search)"
REFRESH_HOURS = 3        # how often the listings are re-downloaded
MAX_AGE_DAYS = 14        # older postings are ignored
RECHECK_HOURS = 24       # an "open" check is trusted this long
CLOSED_TEXT = re.compile(r"no longer (?:accepting|available|open|active)|(?:position|job|role) (?:has been |is )?"
                         r"(?:filled|closed|expired)|job not found|this job (?:posting )?has expired|"
                         r"we couldn.t find (?:that|this) job", re.I)

US_PLACE = re.compile(r", (?:A[LKZR]|C[AOT]|D[EC]|FL|GA|HI|I[DLNA]|K[SY]|LA|M[EDAINSOT]|N[EVHJMYCD]|O[HKR]|PA|RI|"
                      r"S[CD]|T[NX]|UT|V[TA]|W[AVIY])\b|\bUSA\b|United States|\bUS\b|Remote|\bNYC\b|\bSF\b")

# What makes a posting a good fit. Weights add up; tune them in workspace/config.json -> "jobs".
DEFAULT_PREFS = {
    "keywords": {
        "systems analyst": 6, "business analyst": 5, "data analyst": 5, "business intelligence": 4,
        "information systems": 5, "information technology": 4, "analyst": 3, "analytics": 3, "data": 2,
        "it ": 2, "product": 2, "technology": 1, "ai": 2, "artificial intelligence": 3, "machine learning": 2,
        "nlp": 3, "ux": 2, "research": 1, "technical writ": 3, "operations": 1, "consult": 2, "cloud": 1,
        "aws": 2, "sql": 2, "tableau": 3, "power bi": 3, "software": 1, "salesforce": 2, "erp": 2,
    },
    "avoid": {
        "phd": 8, "ph.d": 8, "master": 4, "mba": 5, "senior": 6, "sr.": 6, "staff": 6, "principal": 7,
        "director": 8, "manager": 3, "hardware": 3, "mechanical": 4, "electrical": 3, "chemical": 4,
        "civil": 4, "nurse": 8, "physician": 8,
    },
    "kinds": {"new_grad": 6, "internship": -4},   # raise the kind you want; tune this for yourself
    "locations": {
        "YOUR_CITY": 4, "remote": 3,
    },
}


def html_to_text(markup):
    markup = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", markup or "")
    markup = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr|ul|ol)>", "\n", markup)
    text = html.unescape(re.sub(r"<[^>]+>", " ", markup))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def _get(url, timeout=15, as_json=False, max_bytes=8_000_000):
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT, "Accept": "application/json" if as_json else "text/html,*/*"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            body = resp.read(max_bytes).decode("utf-8", "replace")
            return resp.status, (json.loads(body) if as_json else body)
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:   # any failed or truncated response (including http.client errors) is just "unknown"
        return None, None


_ashby_boards = {}


def _ashby_job(org, job_id):
    cached = _ashby_boards.get(org)
    if not cached or time.time() - cached[0] > 3600:
        code, data = _get(f"https://api.ashbyhq.com/posting-api/job-board/{org}?includeCompensation=true", as_json=True)
        if code != 200 or not isinstance(data, dict):
            return "unknown", ""
        cached = (time.time(), {j.get("id"): j for j in data.get("jobs", [])})
        _ashby_boards[org] = cached
    job = cached[1].get(job_id)
    if job is None:
        return "closed", ""
    return "open", job.get("descriptionPlain") or html_to_text(job.get("descriptionHtml", ""))


def check_posting(url):
    """Ask the company's own job board whether a posting is open.

    Returns (status, description) with status "open", "closed" or "unknown". Never raises.
    """
    try:
        return _check_posting(url)
    except Exception:
        return "unknown", ""


def _check_posting(url):
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    parts = [p for p in parsed.path.split("/") if p]
    try:
        if "greenhouse.io" in host and "jobs" in parts and parts.index("jobs") > 0:
            i = parts.index("jobs")
            code, data = _get(f"https://boards-api.greenhouse.io/v1/boards/{parts[i - 1]}/jobs/{parts[i + 1]}",
                              as_json=True)
            if code == 404:
                return "closed", ""
            if code == 200:
                return "open", html_to_text(html.unescape(data.get("content", "")))
        elif host == "jobs.lever.co" and len(parts) >= 2:
            code, data = _get(f"https://api.lever.co/v0/postings/{parts[0]}/{parts[1]}", as_json=True)
            if code == 404:
                return "closed", ""
            if code == 200:
                lists = "\n".join(f"{x.get('text', '')}\n{html_to_text(x.get('content', ''))}" for x in data.get("lists", []))
                return "open", f"{data.get('descriptionPlain', '')}\n{lists}\n{data.get('additionalPlain', '')}".strip()
        elif host == "jobs.ashbyhq.com" and len(parts) >= 2:
            return _ashby_job(parts[0], parts[1])
        elif host == "jobs.smartrecruiters.com" and len(parts) >= 2:
            job_id = parts[1].split("-")[0]
            code, data = _get(f"https://api.smartrecruiters.com/v1/companies/{parts[0]}/postings/{job_id}", as_json=True)
            if code == 404:
                return "closed", ""
            if code == 200:
                sections = (data.get("jobAd") or {}).get("sections") or {}
                text = "\n\n".join(html_to_text(s.get("text", "")) for s in sections.values() if isinstance(s, dict))
                return ("open" if data.get("active", True) else "closed"), text
        elif host.endswith("myworkdayjobs.com") and "job" in parts:
            path = parts[1:] if re.fullmatch(r"[a-z]{2}-[A-Z]{2}", parts[0]) else parts
            i = path.index("job")
            if i > 0:
                code, data = _get(f"https://{host}/wday/cxs/{host.split('.')[0]}/{path[i - 1]}/{'/'.join(path[i:])}",
                                  as_json=True)
                if code in (404, 410):
                    return "closed", ""
                if code == 200:
                    info = data.get("jobPostingInfo") or {}
                    return ("open" if info.get("canApply", True) else "closed"), html_to_text(info.get("jobDescription", ""))
        # Any other site: load the page itself.
        code, page = _get(url)
        if code in (404, 410):
            return "closed", ""
        if code == 200 and page:
            text = html_to_text(page)
            if CLOSED_TEXT.search(text[:8000]):
                return "closed", ""
            if len(text) > 600:
                return "open", text[:20000]
    except (ValueError, KeyError, IndexError, AttributeError):
        pass
    return "unknown", ""


class JobScout:
    def __init__(self, ws):
        self.ws = ws
        self.path = ws.root / "jobs.db"
        with self._db() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY, company TEXT, title TEXT, locations TEXT, url TEXT, kind TEXT,
                    category TEXT, terms TEXT, sponsorship TEXT, degrees TEXT, date_posted REAL,
                    first_seen REAL, last_seen REAL, listed INTEGER DEFAULT 1, status TEXT DEFAULT 'unchecked',
                    checked_at REAL, description TEXT, used INTEGER DEFAULT 0, in_corpus INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
            """)

    @contextmanager
    def _db(self):
        """A connection that is committed and always closed (sqlite3's own `with` doesn't close it)."""
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def _meta(self, key, value=None):
        with self._db() as db:
            if value is None:
                row = db.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
                return json.loads(row["value"]) if row else None
            db.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (key, json.dumps(value)))

    @property
    def prefs(self):
        user = self.ws.load_config().get("jobs", {})
        return {k: {**DEFAULT_PREFS[k], **user.get(k, {})} for k in DEFAULT_PREFS}

    # -- listings -------------------------------------------------------------
    def refresh_due(self):
        return time.time() - (self._meta("refreshed_at") or 0) > REFRESH_HOURS * 3600

    def refresh(self, log=print):
        """Download the public listings and record which postings are active."""
        now, seen, rows = time.time(), set(), []
        for kind, url in LISTINGS.items():
            code, data = _get(url, timeout=120, as_json=True, max_bytes=200_000_000)
            if code != 200 or not isinstance(data, list):
                log(f"Job Scout: couldn't download the {kind.replace('_', '-')} list, keeping the last one")
                return 0
            for item in data:
                posted = item.get("date_posted") or 0
                if not (item.get("active") and item.get("is_visible", True) and item.get("url")):
                    continue
                if now - posted > MAX_AGE_DAYS * 86400:
                    continue
                job_id = str(item.get("id") or hashlib.sha1(item["url"].encode()).hexdigest())
                seen.add(job_id)
                rows.append((job_id, item.get("company_name", ""), item.get("title", ""),
                             json.dumps(item.get("locations") or []), item["url"], kind, item.get("category") or "",
                             json.dumps(item.get("terms") or []), item.get("sponsorship") or "",
                             json.dumps(item.get("degrees") or []), posted, now, now))
        with self._db() as db:
            db.executemany("""
                INSERT INTO jobs (id, company, title, locations, url, kind, category, terms, sponsorship, degrees,
                                  date_posted, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET listed=1, last_seen=excluded.last_seen, url=excluded.url,
                                              title=excluded.title, locations=excluded.locations""", rows)
            db.execute(f"UPDATE jobs SET listed=0 WHERE id NOT IN ({','.join('?' * len(seen))})", tuple(seen))
        self._meta("refreshed_at", now)
        log(f"Job Scout: {len(rows):,} active postings from the last {MAX_AGE_DAYS} days")
        return len(rows)

    # -- ranking ----------------------------------------------------------------
    def score(self, row, extra_terms=()):
        prefs = self.prefs
        title = f" {row['title'].lower()} "
        text = f"{title} {row['category'].lower()} {row['company'].lower()}"
        score = sum(w for k, w in prefs["keywords"].items() if k in text)
        score += sum(3 for t in extra_terms if t in text)
        score -= sum(w for k, w in prefs["avoid"].items() if k in title)
        raw_places = " | ".join(json.loads(row["locations"] or "[]"))
        if raw_places and not US_PLACE.search(raw_places):
            score -= 20   # outside the US
        places = raw_places.lower()
        score += max([w for k, w in prefs["locations"].items() if k in places] or [0])
        score += prefs["kinds"].get(row["kind"], 0)
        age_days = (time.time() - (row["date_posted"] or 0)) / 86400
        score += 8 if age_days <= 5 else 3 if age_days <= 10 else 0   # 5 days or newer first
        return score

    def ranked(self, extra_terms=(), unused_only=False, limit=40, url_filter=None):
        sql = "SELECT * FROM jobs WHERE listed=1 AND status != 'closed' AND date_posted > ?"
        if unused_only:
            sql += " AND used=0"
        with self._db() as db:
            rows = db.execute(sql, (time.time() - MAX_AGE_DAYS * 86400,)).fetchall()
        if url_filter is not None:
            rows = [r for r in rows if url_filter.search(r["url"])]
        rows = sorted(rows, key=lambda r: self.score(r, extra_terms), reverse=True)
        return [dict(r) for r in rows[:limit]]

    # -- verification -------------------------------------------------------------
    def verify(self, jobs, workers=8):
        """Check postings with the companies' own job boards (re-checks older than a day)."""
        stale = [j for j in jobs if j["status"] == "unchecked" or time.time() - (j["checked_at"] or 0) > RECHECK_HOURS * 3600]
        if stale:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                results = list(pool.map(lambda j: check_posting(j["url"]), stale))
            now = time.time()
            with self._db() as db:
                for job, (status, description) in zip(stale, results):
                    job.update(status=status, checked_at=now, description=description or job.get("description"))
                    db.execute("UPDATE jobs SET status=?, checked_at=?, description=COALESCE(NULLIF(?, ''), description) "
                               "WHERE id=?", (status, now, description, job["id"]))
        return [j for j in jobs if j["status"] == "open"]

    def open_jobs(self, extra_terms=(), unused_only=False, limit=12, url_filter=None):
        """The best-fitting postings that the company's own board confirms are open right now."""
        found = []
        for batch_start in range(0, 120, 30):
            candidates = self.ranked(extra_terms, unused_only, limit=batch_start + 30, url_filter=url_filter)[batch_start:]
            if not candidates:
                break
            found += self.verify(candidates)
            if len(found) >= limit:
                break
        return sorted(found, key=lambda j: self.score(j, extra_terms), reverse=True)[:limit]

    def confirmed_open(self, limit=8):
        """Best-fitting postings confirmed open within the last day (database only, no network)."""
        with self._db() as db:
            rows = db.execute("SELECT * FROM jobs WHERE listed=1 AND status='open' AND checked_at > ?",
                              (time.time() - RECHECK_HOURS * 3600,)).fetchall()
        rows = sorted(rows, key=self.score, reverse=True)[:limit]
        return [{k: r[k] for k in ("id", "company", "title", "url", "date_posted", "kind", "used")}
                | {"locations": json.loads(r["locations"] or "[]")} for r in rows]

    def mark_used(self, job_ids):
        with self._db() as db:
            db.executemany("UPDATE jobs SET used=1 WHERE id=?", [(i,) for i in job_ids])

    def new_corpus_text(self, limit=200):
        """Descriptions of open postings not yet given to the local model (public text only)."""
        with self._db() as db:
            rows = db.execute("SELECT id, company, title, locations, description FROM jobs WHERE status='open' "
                              "AND in_corpus=0 AND length(description) > 400 LIMIT ?", (limit,)).fetchall()
            db.executemany("UPDATE jobs SET in_corpus=1 WHERE id=?", [(r["id"],) for r in rows])
        return [f"{r['title']} at {r['company']} ({', '.join(json.loads(r['locations'] or '[]'))})\n\n{r['description']}"
                for r in rows]

    def stats(self):
        with self._db() as db:
            row = db.execute("""SELECT
                SUM(listed=1) AS listed, SUM(listed=1 AND status='open') AS verified_open,
                SUM(status='closed') AS closed, SUM(used=1) AS used,
                SUM(listed=1 AND first_seen > ?) AS new_today FROM jobs""", (time.time() - 86400,)).fetchone()
        return {**{k: row[k] or 0 for k in row.keys()}, "refreshed_at": self._meta("refreshed_at")}


def format_jobs(jobs, with_description=0):
    lines = []
    for j in jobs:
        places = ", ".join(json.loads(j["locations"] or "[]")[:3]) or "location not listed"
        posted = time.strftime("%b %d", time.localtime(j["date_posted"] or 0))
        line = f"- {j['title']} at {j['company']} ({places}), posted {posted}, confirmed open: {j['url']}"
        if j.get("sponsorship") and j["sponsorship"] != "Other":
            line += f" [{j['sponsorship']}]"
        if with_description and j.get("description"):
            line += "\n  Description: " + re.sub(r"\s+", " ", j["description"])[:with_description]
        lines.append(line)
    return "\n".join(lines)
