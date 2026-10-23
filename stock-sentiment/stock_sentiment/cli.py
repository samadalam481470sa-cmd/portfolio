"""Command-line interface.  Run `python -m stock_sentiment --help`."""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import typer
import yaml

from . import pipeline
from .config import load_settings

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="News sentiment signals for stocks. Research tool, not trading advice.")
state: dict = {}

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 20)
pd.set_option("display.max_colwidth", 70)


def ctx() -> pipeline.Context:
    if "ctx" not in state:
        state["ctx"] = pipeline.Context.build(load_settings(state.get("config")))
    return state["ctx"]


@app.callback()
def main(config: Path = typer.Option(None, help="Path to config.yaml"),
         verbose: bool = typer.Option(False, "-v", "--verbose")):
    state["config"] = config
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@app.command()
def fetch(source: list[str] = typer.Option(None, "--source", "-s", help="Only these sources"),
          ticker: list[str] = typer.Option(None, "--ticker", "-t", help="Only these tickers")):
    """Fetch news from all enabled sources and store new articles."""
    for name, r in pipeline.run_fetch(ctx(), source or None, [t.upper() for t in ticker] if ticker else None).items():
        typer.echo(f"{name:12s} {r}")


@app.command()
def link(all_: bool = typer.Option(False, "--all", help="Re-link every article (after changing the universe "
                                                      "or matching rules); affected pairs get re-scored")):
    """Match stored articles to tickers."""
    if all_:
        ctx().repo.reset_links()
    typer.echo(f"linked {pipeline.run_link(ctx())} articles")


@app.command()
def score():
    """Score sentiment for every linked (article, ticker) pair that isn't scored yet."""
    typer.echo(f"scored {pipeline.run_score(ctx())}")


@app.command()
def signals(top: int = typer.Option(10, help="How many bullish and bearish names to show"),
            model: str = typer.Option(None, help="Sentiment model (default from config)"),
            headlines: bool = typer.Option(True, help="Show the headlines driving each signal")):
    """Compute current signals and print the most bullish and bearish tickers."""
    c = ctx()
    rows = pipeline.run_signals(c, model=model)
    df = pd.DataFrame(rows)
    df = df[df["n_articles"] > 0].sort_values("composite", ascending=False)
    if df.empty:
        typer.echo("No scored news in the lookback window yet. Run `run` (fetch+link+score) first.")
        return
    cols = ["ticker", "composite", "score", "baseline", "delta", "volume_z", "confidence", "n_articles"]
    typer.echo(f"model: {pipeline.effective_model(c, model)}\n\nMost bullish news:")
    typer.echo(df.head(top)[cols].to_string(index=False))
    typer.echo("\nMost bearish news:")
    typer.echo(df.tail(top).iloc[::-1][cols].to_string(index=False))
    if headlines:
        typer.echo("\nDrivers:")
        for _, r in pd.concat([df.head(3), df.tail(3)]).drop_duplicates("ticker").iterrows():
            typer.echo(f"  {r['ticker']}:")
            for h in r["top_headlines"]:
                typer.echo(f"    {h['compound']:+.2f}  {h['title']}  [{h['publisher']}]")
    typer.echo("\nResearch signal only, not trading advice.")


@app.command()
def run():
    """One full cycle: fetch, link, score, signals."""
    typer.echo(json.dumps(pipeline.run_all(ctx()), indent=2, default=str))


@app.command()
def prices(days: int = typer.Option(365, help="History to download on first run")):
    """Download/update daily prices (universe + benchmark) from yfinance."""
    from datetime import timedelta
    from .evaluation.prices import update_prices
    c = ctx()
    n = update_prices(c.repo, c.tickers + [c.settings.benchmark], date.today() - timedelta(days=days))
    typer.echo(f"stored {n} price rows")


@app.command()
def backtest(start: str = typer.Option(None, help="YYYY-MM-DD"), end: str = typer.Option(None, help="YYYY-MM-DD"),
             model: str = typer.Option(None), save: Path = typer.Option(None, help="Write the panel to CSV")):
    """Measure whether past signals predicted next-day / 5-day returns (IC, hit rate, long-short)."""
    from .evaluation.backtest import build_panel, evaluate
    c = ctx()
    model = pipeline.effective_model(c, model)
    items = c.repo.scored_items(model, c.tickers)
    px = c.repo.prices(c.tickers + [c.settings.benchmark])
    if items.empty or px.empty:
        typer.echo("Need scored news and prices. Run `run` and `prices` first.")
        raise typer.Exit(1)
    panel = build_panel(items, px, c.tickers, c.settings,
                        date.fromisoformat(start) if start else None, date.fromisoformat(end) if end else None)
    if save:
        panel.to_csv(save, index=False)
    if panel.empty:
        typer.echo("No overlapping news and price dates yet.")
        raise typer.Exit(1)
    res = evaluate(panel)
    days = panel.loc[panel["n_articles"] > 0, "date"].nunique()
    typer.echo(f"model={model}  ticker-days={len(panel)}  trading days with news={days}  "
               f"with news={int((panel['n_articles'] > 0).sum())}\n")
    typer.echo(res.round(4).to_string(index=False))
    typer.echo("\nHow to read this: ic_mean is the average daily rank correlation between signal and forward return."
               "\n|IC| > 0.03 with |ic_t| > 2 over 60+ days is worth paying attention to; 'random' shows the noise floor.")
    typer.echo("Abnormal (abn_) returns subtract the benchmark: same ranks, so same IC, but different hit rates.")
    if days < 60:
        typer.echo(f"\nWARNING: only {days} trading days with news — too few to conclude anything. "
                   "Keep the scheduler running to collect more.")


@app.command()
def health():
    """Per-source status for the last few runs (catches scrapers that silently broke)."""
    c = ctx()
    h = c.repo.source_health()
    enabled = {n for n, cfg in c.settings.sources.items() if cfg.enabled}
    h = h[h["source"].isin(enabled)]
    typer.echo(h.to_string(index=False) if not h.empty else "no runs yet")
    typer.echo(f"\ncounts: {c.repo.counts()}")
    for _, r in h.iterrows():
        if r["ok_runs"] == 0:
            typer.echo(f"!! {r['source']} failed on every recent run: {r['last_error']}")
        elif r["items"] == 0:
            typer.echo(f"!! {r['source']} returned no items recently (layout change or block?)")


@app.command()
def universe(sp500: bool = typer.Option(False, help="Scrape S&P 500 constituents from Wikipedia"),
             show: bool = typer.Option(False, help="Print the current universe")):
    """Show or extend the stock universe."""
    from .entities.universe import load_sp500
    c = ctx()
    if sp500:
        entries = load_sp500(c.http)
        path = c.settings.universe_file
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump([e.model_dump() for e in entries], sort_keys=False))
        typer.echo(f"wrote {len(entries)} tickers to {path}")
    if show or not sp500:
        for e in c.settings.full_universe():
            typer.echo(f"{e.ticker:6s} {e.name}  aliases={e.aliases}{'  (context required)' if e.context_required else ''}")


@app.command()
def schedule():
    """Run continuously: fetch+score every N minutes, signals hourly, prices daily."""
    from .scheduler import run_scheduler
    run_scheduler(ctx())


@app.command()
def dashboard():
    """Launch the Streamlit dashboard."""
    import subprocess
    import sys
    script = Path(__file__).with_name("dashboard.py")
    args = [sys.executable, "-m", "streamlit", "run", str(script)]
    if state.get("config"):
        args += ["--", "--config", str(state["config"])]
    subprocess.run(args, check=False)
