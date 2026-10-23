"""Webhook alerts when a ticker's news tone breaks sharply from its normal level on unusual volume."""
from __future__ import annotations

import logging
from datetime import datetime

import requests

from .config import AlertConfig
from .db.repo import Repo

log = logging.getLogger(__name__)


def triggered(cfg: AlertConfig, row: dict) -> str | None:
    if row["confidence"] < cfg.min_confidence or row["volume_z"] < cfg.min_volume_z:
        return None
    if row["delta"] >= cfg.min_abs_delta:
        return "bullish"
    if row["delta"] <= -cfg.min_abs_delta:
        return "bearish"
    return None


def format_alert(row: dict, direction: str) -> str:
    lines = [f"**{row['ticker']}** news turned {direction}: score {row['score']:+.2f} "
             f"(normal {row['baseline']:+.2f}), {row['n_articles']} articles, volume z={row['volume_z']:.1f}"]
    lines += [f"• {h['title']} ({h['publisher']}, {h['compound']:+.2f})" for h in row["top_headlines"]]
    lines.append("_Research signal, not trading advice._")
    return "\n".join(lines)


def send_alerts(repo: Repo, cfg: AlertConfig, rows: list[dict], as_of: datetime) -> int:
    if not cfg.webhook_url:
        log.warning("alerts enabled but alerts.webhook_url is empty")
        return 0
    day = as_of.date().isoformat()
    sent = 0
    for row in rows:
        direction = triggered(cfg, row)
        if not direction or repo.alert_already_sent(row["ticker"], day, direction):
            continue
        text = format_alert(row, direction)
        payload = {"content": text} if cfg.kind == "discord" else {"text": text}
        try:
            requests.post(cfg.webhook_url, json=payload, timeout=10).raise_for_status()
        except requests.RequestException as e:
            log.warning("alert for %s failed: %s", row["ticker"], e)
            continue
        repo.mark_alert_sent(row["ticker"], day, direction)
        sent += 1
    return sent
