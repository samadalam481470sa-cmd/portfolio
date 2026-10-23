"""Long-running scheduler. Each job catches its own errors so one failure doesn't stop collection."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from apscheduler.schedulers.blocking import BlockingScheduler

from . import pipeline
from .evaluation.prices import update_prices

log = logging.getLogger(__name__)


def _safe(fn, name):
    def wrapper():
        try:
            log.warning("%s: %s", name, fn())
        except Exception:
            log.exception("%s failed", name)
    return wrapper


def run_scheduler(ctx: pipeline.Context) -> None:
    s = ctx.settings.schedule
    sched = BlockingScheduler(timezone="America/New_York")

    def collect():
        return {"fetch": pipeline.run_fetch(ctx), "linked": pipeline.run_link(ctx), "scored": pipeline.run_score(ctx)}

    def signals():
        return f"{len(pipeline.run_signals(ctx))} signals"

    def daily():
        return f"{update_prices(ctx.repo, ctx.tickers + [ctx.settings.benchmark], date.today() - timedelta(days=365))} price rows"

    hour, minute = map(int, s.daily_eval_time.split(":"))
    sched.add_job(_safe(collect, "collect"), "interval", minutes=s.fetch_minutes, next_run_time=_now(),
                  max_instances=1, coalesce=True)
    sched.add_job(_safe(signals, "signals"), "interval", minutes=s.signals_minutes, max_instances=1, coalesce=True)
    sched.add_job(_safe(daily, "prices"), "cron", day_of_week="mon-fri", hour=hour, minute=minute)
    logging.getLogger().setLevel(logging.WARNING)
    print(f"Scheduler running: collect every {s.fetch_minutes}m, signals every {s.signals_minutes}m, "
          f"prices at {s.daily_eval_time} ET on weekdays. Ctrl+C to stop.")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        pass


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
