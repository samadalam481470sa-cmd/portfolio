"""Online learning: reads only open sources, checks robots.txt, caps each day, logs every item.

Sources: Wikipedia, arXiv, Hacker News, and RSS feeds. Each fetch is identified and paced.
A site that disallows the path in robots.txt is skipped. Everything learned is listed on the dashboard.
"""
import json
import time
import urllib.robotparser
from urllib.parse import urlparse

DAILY_CAP = 40
UA = "HomeGrok/1.0 (personal learning assistant; identified client)"
_robots = {}


def _allowed(url):
    host = urlparse(url).scheme + "://" + urlparse(url).netloc
    if host not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(host + "/robots.txt")
        try:
            rp.read()
        except Exception:
            rp = None   # cannot read robots.txt: treat as not allowed
        _robots[host] = rp
    rp = _robots[host]
    return rp is not None and rp.can_fetch(UA, url)


def learn_online(ws, log=print):
    from .cortex_bot import PublicCortex
    from .relearn import CortexConfig, HttpClient, SourceRouter
    from .relearn import RNG
    log_path = ws.root / "online_learned.jsonl"
    today = time.strftime("%Y-%m-%d")
    meta_path = ws.root / "online_meta.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    if meta.get("day") != today:
        meta = {"day": today, "count": 0}
    room = DAILY_CAP - meta["count"]
    if room <= 0:
        return 0
    cfg = CortexConfig(online=True, user_agent=UA, rate_limit_seconds=2.0, timeout_seconds=12.0)
    router = SourceRouter(cfg, RNG(int(time.time()) % 100000))
    cortex = PublicCortex(ws)
    learned = 0
    for source in cfg.sources:
        if learned >= room:
            break
        try:
            doc = router.fetch(source)
        except Exception as e:
            log(f"Online: {source} unavailable ({e!r})")
            continue
        if not doc.url or doc.url.startswith("offline") or not doc.text.strip():
            continue
        if not _allowed(doc.url):
            log(f"Online: skipped {doc.url} (robots.txt does not allow it)")
            continue
        cortex.learn_one(doc.text, title=doc.title)
        with open(log_path, "a") as f:
            f.write(json.dumps({"time": time.time(), "source": doc.source, "title": doc.title, "url": doc.url}) + "\n")
        learned += 1
    meta["count"] += learned
    meta_path.write_text(json.dumps(meta))
    if learned:
        log(f"Online: learned {learned} items (today {meta['count']}/{DAILY_CAP})")
    return learned


def recent(ws, n=10):
    path = ws.root / "online_learned.jsonl"
    if not path.exists():
        return []
    lines = path.read_text().splitlines()[-n:]
    return [json.loads(x) for x in lines][::-1]
