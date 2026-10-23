"""Polite HTTP client: per-domain rate limiting, robots.txt, retries with backoff, conditional GETs, raw cache."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests

from ..config import HttpConfig
from ..db.repo import Repo

log = logging.getLogger(__name__)

RETRY_STATUSES = {429, 500, 502, 503, 504}
MAX_BACKOFF_SECONDS = 60


class FetchError(Exception):
    pass


class RobotsDisallowed(FetchError):
    pass


@dataclass
class Response:
    url: str
    status: int
    text: str | None  # None when the server says nothing changed (304)

    @property
    def not_modified(self) -> bool:
        return self.status == 304


class HttpClient:
    def __init__(self, cfg: HttpConfig, repo: Repo | None = None, raw_cache_dir: Path | None = None):
        self.cfg = cfg
        self.repo = repo
        self.raw_cache_dir = raw_cache_dir
        self.session = requests.Session()
        self._last_hit: dict[str, float] = {}
        self._robots: dict[str, RobotFileParser | None] = {}
        self._lock = threading.Lock()

    def get(self, url: str, *, user_agent: str | None = None, conditional: bool = True,
            params: dict | None = None) -> Response:
        ua = user_agent or self.cfg.user_agent
        full_url = requests.Request("GET", url, params=params).prepare().url
        if self.cfg.respect_robots and not self._robots_allowed(full_url, ua):
            raise RobotsDisallowed(f"robots.txt disallows {full_url}")

        headers = {"User-Agent": ua, "Accept-Language": "en-US,en;q=0.9"}
        if conditional and self.repo:
            etag, last_modified = self.repo.http_validators(full_url)
            if etag:
                headers["If-None-Match"] = etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified

        last_exc: Exception | None = None
        for attempt in range(self.cfg.max_retries + 1):
            self._throttle(full_url)
            try:
                r = self.session.get(full_url, headers=headers, timeout=self.cfg.timeout)
            except requests.RequestException as e:
                last_exc = e
                self._sleep_backoff(attempt, None)
                continue
            if r.status_code == 304:
                return Response(full_url, 304, None)
            if r.status_code in RETRY_STATUSES and attempt < self.cfg.max_retries:
                log.info("HTTP %s from %s, retrying", r.status_code, full_url)
                self._sleep_backoff(attempt, r.headers.get("Retry-After"))
                continue
            if r.status_code >= 400:
                raise FetchError(f"HTTP {r.status_code} for {full_url}")
            if conditional and self.repo:
                self.repo.save_http_validators(full_url, r.headers.get("ETag"), r.headers.get("Last-Modified"))
            self._write_raw(full_url, r.content)
            return Response(full_url, r.status_code, r.text)
        raise FetchError(f"giving up on {full_url}: {last_exc}")

    # ---- helpers --------------------------------------------------------
    def _throttle(self, url: str) -> None:
        domain = urlparse(url).netloc
        with self._lock:
            wait = self._last_hit.get(domain, 0) + self.cfg.min_interval_seconds - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last_hit[domain] = time.monotonic()

    def _sleep_backoff(self, attempt: int, retry_after: str | None) -> None:
        delay = 2 ** attempt * 2
        if retry_after and retry_after.isdigit():
            delay = int(retry_after)
        time.sleep(min(delay, MAX_BACKOFF_SECONDS))

    def _robots_allowed(self, url: str, ua: str) -> bool:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._robots:
            rp = RobotFileParser()
            try:
                r = self.session.get(root + "/robots.txt", headers={"User-Agent": ua}, timeout=self.cfg.timeout)
                if r.status_code >= 400:
                    rp = None  # no robots.txt: everything allowed
                else:
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp = None
            self._robots[root] = rp
        rp = self._robots[root]
        return True if rp is None else rp.can_fetch(ua, url)

    def _write_raw(self, url: str, content: bytes) -> None:
        if not self.raw_cache_dir:
            return
        self.raw_cache_dir.mkdir(parents=True, exist_ok=True)
        name = hashlib.sha1(url.encode()).hexdigest()[:16]
        (self.raw_cache_dir / f"{name}.raw").write_bytes(content)
