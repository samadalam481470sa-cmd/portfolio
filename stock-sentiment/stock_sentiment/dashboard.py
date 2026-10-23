"""Streamlit dashboard: ranked signals, per-ticker sentiment vs price, and the headlines behind them.
Launch with `python -m stock_sentiment dashboard`."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402
import streamlit as st  # noqa: E402

from stock_sentiment import pipeline  # noqa: E402
from stock_sentiment.config import load_settings  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("--config", default=None)
args, _ = parser.parse_known_args()

st.set_page_config(page_title="News Sentiment", layout="wide")


@st.cache_resource
def get_ctx(config):
    return pipeline.Context.build(load_settings(config))


ctx = get_ctx(args.config)
model = pipeline.effective_model(ctx)

st.title("Stock news sentiment")
st.caption(f"Model: {model}. Research signal only, not trading advice.")

col_a, col_b = st.columns([1, 3])
with col_a:
    if st.button("Recompute signals now"):
        pipeline.run_signals(ctx, alert=False)
        st.rerun()

latest = ctx.repo.latest_signals(model)
if latest.empty:
    st.info("No signals yet. Run `python -m stock_sentiment run` first.")
    st.stop()

st.subheader(f"Signals as of {pd.Timestamp(latest['as_of'].iloc[0]).tz_convert('America/New_York'):%Y-%m-%d %H:%M} ET")
table = latest[latest["n_articles"] > 0][["ticker", "composite", "score", "baseline", "delta", "volume_z",
                                          "confidence", "n_articles"]]
signed = st.column_config.NumberColumn(format="%+.3f")
st.dataframe(table, width="stretch", hide_index=True,
             column_config={c: signed for c in ("composite", "score", "baseline", "delta")})

st.subheader("Ticker detail")
ticker = st.selectbox("Ticker", table["ticker"].tolist() or ctx.tickers)
hist = ctx.repo.signal_history(ticker, model)
px = ctx.repo.prices([ticker])
c1, c2 = st.columns(2)
with c1:
    st.markdown("**Sentiment (composite) over time**")
    if not hist.empty:
        st.line_chart(hist.set_index("as_of")[["composite", "score", "baseline"]])
    else:
        st.write("No history yet.")
with c2:
    st.markdown("**Close price**")
    if not px.empty:
        st.line_chart(px.set_index("date")["close"])
    else:
        st.write("No prices yet. Run `python -m stock_sentiment prices`.")

row = latest[latest["ticker"] == ticker]
if not row.empty:
    st.markdown("**Headlines driving the current signal**")
    for h in json.loads(row["top_headlines"].iloc[0] or "[]"):
        st.markdown(f"`{h['compound']:+.2f}` [{h['title']}]({h['url']}) — {h['publisher']}")

items = ctx.repo.scored_items(model, [ticker]).sort_values("published_at", ascending=False).head(50)
st.markdown("**Recent scored articles**")
st.dataframe(items[["published_at", "title", "publisher", "source", "relevance", "novelty", "compound"]],
             width="stretch", hide_index=True)

with st.expander("Source health"):
    st.dataframe(ctx.repo.source_health(), width="stretch", hide_index=True)
