# Stock news sentiment

News sentiment signals for stocks. Research tool, not trading advice.

The pipeline is fetch, then normalize and dedupe, then link articles to tickers, score sentiment, build signals, and optionally send alerts. Storage is SQLite (`data/sentiment.db` by default).

## What it reads

Sources and weights are in `config.yaml`.

- Enabled: Nasdaq RSS, Finviz news, MarketWatch, and SEC EDGAR.
- Google News and Yahoo are present in the code and turned off. Their robots.txt disallows automated access to these feeds.
- EDGAR is skipped unless `http.sec_user_agent` is set to a descriptive User-Agent with a contact email.

Sentiment defaults to FinBERT (`ProsusAI/finbert`) and falls back to VADER if FinBERT is not available. A VADER score is also stored as the baseline. The ticker universe in `config.yaml` is a fixed list (Apple, Microsoft, Nvidia, and the other names in that file), with optional loading of S&P 500 constituents from Wikipedia.

## Commands

From this folder, after installing `requirements.txt`:

```bash
python -m stock_sentiment --help
python -m stock_sentiment run          # fetch, link, score, signals
python -m stock_sentiment signals
python -m stock_sentiment prices
python -m stock_sentiment backtest
python -m stock_sentiment health
python -m stock_sentiment universe --show
python -m stock_sentiment schedule     # fetch on an interval, signals hourly, prices daily
python -m stock_sentiment dashboard    # Streamlit UI
```

`pytest` runs the parser, linker, signal, and pipeline tests. They use local fixtures and do not call the network.

FinBERT, Streamlit, and the price download (`yfinance`) are only needed for those commands. The unit tests score with VADER.
