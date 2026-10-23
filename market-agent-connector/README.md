# Market Agent Connector

An AI agent connector that bridges **Polymarket**, **Kalshi**, and **Robinhood** through their official open APIs — plus an **advanced AI trading engine** that fetches live market data, real-time news, and web research to make intelligent buy/sell/hold decisions.

## What's New: AI Trading Engine

The built-in AI trader:

1. **Finds the trades for you** — scans market movers, trending tickers, sector baskets and insider-buy clusters, then ranks the best setups with entry, stop-loss and target levels
2. **Gathers real-world intelligence** — live stock quotes (Yahoo Finance), news (Google News RSS + Finnhub), web research (DuckDuckGo), insider filings (OpenInsider / SEC Form 4), and technical indicators (RSI, SMA, trend)
3. **Makes AI decisions** — GPT/LLM analysis when `AI_API_KEY` is set, or smart rule-based engine as fallback
4. **Executes trades safely** — risk limits, dry-run mode, paper trading sandbox ($10k virtual portfolio)
5. **Supports all platforms** — paper (default), Robinhood, Kalshi, Polymarket

```
Discover → Research → Analyze → Risk Check → Execute
   ↓          ↓          ↓          ↓           ↓
 Movers     News      AI/LLM    Confidence   Paper/Live
 Trending   Prices    Signal    Max $ limit  Broker
 Insiders   Web       BUY/SELL  Dry-run
```

> **Note on price data:** Yahoo Finance requires a cookie/crumb handshake for its
> quote API and rate-limits datacenter IPs aggressively. The client handles the
> handshake, retries with backoff, and falls back to the unauthenticated chart
> endpoint. If a scan reports that market data could not be retrieved, the feed is
> throttling — wait and retry rather than assuming there are no setups.

## Live Growth Trading (2x / 3x Targets)

> **Important:** You deposit money into **your own** Robinhood, Kalshi, and Polymarket accounts. This software connects via API keys — it never holds your funds. Doubling or tripling your capital is a **goal**, not a guarantee. You can lose everything.

The growth trader runs AI analysis across all platforms and executes live trades toward your targets:

```
$1,000 start → target $2,000 (2x) → target $3,000 (3x)
        ↓              ↓                    ↓
   50% Robinhood   milestone hit       milestone hit
   30% Kalshi
   20% Polymarket
```

### Setup for live trading

1. **Fund your accounts** — deposit capital on Robinhood, Kalshi, Polymarket
2. **Add API credentials** to `.env` (see `.env.example`)
3. **Enable live mode:**

```env
GROWTH_STARTING_CAPITAL=1000
GROWTH_TARGETS=2,3
GROWTH_LIVE_ENABLED=true
GROWTH_LIVE_ACK=I_ACCEPT_FINANCIAL_RISK
AI_DRY_RUN=false
AI_REQUIRE_CONFIRMATION=false
KALSHI_USE_DEMO=false
```

4. **Initialize and run:**

```bash
# One-shot cycle via MCP tools:
# growth_setup(1000, "2,3")
# growth_run_live_cycle()

# Or continuous daemon (every 30 min):
market-agent-growth
```

### Growth MCP tools

| Tool | Description |
|------|-------------|
| `growth_setup(1000, "2,3")` | Set starting capital and 2x/3x targets |
| `growth_status()` | Portfolio value, multiplier, milestone progress |
| `growth_platform_check()` | Which platforms are ready for live |
| `growth_run_live_cycle()` | Analyze + trade on all platforms |

### Safety limits (auto-halt)

- **Max drawdown** — stops if portfolio drops 20% from peak (configurable)
- **Daily loss limit** — stops if down 10% in one day
- **Per-trade risk** — only 3% of capital per trade
- **Confidence gate** — won't trade below 65% AI confidence

## Telegram & Discord Bot

Chat with your trading AI directly from your phone or Discord.

```
You:  /analyze AAPL
Bot:  🟢 BUY AAPL — 72% confidence, RSI oversold, positive earnings news...

You:  /growth
Bot:  📊 $1,470 (1.47x) — [███████░░░] 73% toward 2x

You:  /growth_run
Bot:  🚀 Live cycle: 3 trades executed across Robinhood, Kalshi, Polymarket
```

### Setup

1. **Create a bot:**
   - Telegram: message [@BotFather](https://t.me/BotFather) → `/newbot` → copy token
   - Discord: [Discord Developer Portal](https://discord.com/developers/applications) → New App → Bot → copy token → enable Message Content Intent

2. **Add to `.env`:**
```env
TELEGRAM_BOT_TOKEN=123456:ABC...
DISCORD_BOT_TOKEN=your-discord-token
BOT_ALLOWED_USERS=your_telegram_or_discord_user_id
```

3. **Run:**
```bash
market-agent-bot                  # both Telegram + Discord
market-agent-bot --platform telegram
market-agent-bot --platform discord
```

### Commands (same on both platforms)

**Finding trades** (you don't need to know what to look at):

| Command | What it does |
|---------|-------------|
| `/best` | Scans the market and ranks the best trades to make right now |
| `/scan AAPL,MSFT,NVDA` | Scores and ranks specific symbols (blank = your watchlist) |
| `/movers` | Biggest gainers and losers today |
| `/trending` | Tickers the market is watching right now |
| `/sector tech` | Best setups in a sector (tech, ai, finance, healthcare, energy, consumer, crypto) |
| `/insider_buys` | Stocks where multiple insiders are buying |
| `/opportunities kalshi` | Best prediction-market contracts (kalshi, polymarket, both) |
| `/compare AAPL MSFT NVDA` | Head-to-head ranking |
| `/watchlist add AAPL` | View or edit the watchlist (list, add, remove, clear) |

**Analysis and trading:**

| Command | What it does |
|---------|-------------|
| `/quote AAPL` | Live stock price |
| `/news AAPL` | Latest news |
| `/research AAPL` | Full intel report |
| `/insider AAPL` | SEC insider trade history (OpenInsider) |
| `/analyze AAPL` | AI buy/sell/hold |
| `/predict AAPL` | Price forecast + buy/sell zones |
| `/signals` | All watchlist buy/sell signals |
| `/auto_start` | Start automatic trading (every 15min) |
| `/auto_stop` | Stop auto-trading |
| `/trade AAPL` | Analyze + execute immediately |
| `/portfolio` | Paper portfolio |
| `/cycle` | Run watchlist cycle |
| `/growth_setup 1000` | Set $1k target 2x/3x |
| `/growth` | Progress toward milestones |
| `/growth_run` | Live multi-platform cycle |
| `/platforms` | Broker connection status |
| `/status` | System health |

### How trade discovery works

`/best` is the "just tell me what to trade" command. It pulls candidates from
four sources, scores each one, and returns the strongest setups with levels you
can act on:

```
Top gainers ─┐
Top losers  ─┤
Most active ─┼─→ score each candidate ─→ rank ─→ top N with entry/stop/target
Trending    ─┤    (momentum, RSI, trend,
Insider     ─┘     risk/reward, insider conviction)
clusters
```

Each result includes the direction, a conviction score, entry price, stop-loss,
take-profit, risk/reward ratio, the reason it surfaced, and any warnings (thin
volume, already-extended move). A multi-insider cluster buy can carry a name
that the technicals alone would have rated HOLD, because several insiders buying
the same stock is a thesis on its own.

Example flow:

```
/best              →  ranked list of setups across the whole market
/insider_buys      →  stocks with 2+ insiders buying (strongest single signal)
/compare AAPL MSFT →  which of these two is the better trade
/analyze NVDA      →  full reasoning for one name
/trade NVDA        →  execute it
```

### How auto buy/sell works

```
Every 15 min → Scan watchlist → Predict direction → Execute if confident

/predict AAPL  →  "BULLISH 74%, target $185, buy zone $176"
/signals       →  Shows BUY/SELL for all watchlist stocks
/auto_start    →  Bot automatically buys bullish + sells bearish
                  and messages you each trade it makes
```

The system decides **when to buy** (RSI oversold + bullish news + upward trend) and **when to sell** (RSI overbought + bearish news + downward trend). It only executes when confidence is ≥ 65%.

## Platforms

| Platform | Public Data | Trading | Auth Method |
|----------|-------------|---------|-------------|
| **Polymarket** | ✅ Gamma + CLOB APIs | ✅ CLOB API keys | Wallet + API key derivation |
| **Kalshi** | ✅ REST API | ✅ RSA API keys | Key ID + RSA private key |
| **Robinhood** | ⚠️ Partner only | ⚠️ Partner only | OAuth 2.0 (requires approval) |

> **Robinhood note:** Robinhood does not offer a public retail API. This connector implements the official [Partner Brokerage API](https://go.robinhood.com/partner). You must apply and be approved before use.

## Quick Start

### 1. Install

```bash
pip install -e ".[dev]"
```

### 2. Configure credentials

```bash
cp .env.example .env
# Edit .env with your API keys
```

### 3. Run as MCP server (for Cursor, Claude Desktop, etc.)

Add to your MCP config (`~/.cursor/mcp.json` or Claude Desktop config):

```json
{
  "mcpServers": {
    "market-agent": {
      "command": "market-agent-mcp",
      "env": {
        "KALSHI_API_KEY_ID": "your-key-id",
        "KALSHI_PRIVATE_KEY_PATH": "/path/to/kalshi-key.pem",
        "POLYMARKET_WALLET_ADDRESS": "0x...",
        "POLYMARKET_CLOB_API_KEY": "...",
        "POLYMARKET_CLOB_SECRET": "...",
        "POLYMARKET_CLOB_PASSPHRASE": "..."
      }
    }
  }
}
```

Or run directly:

```bash
market-agent-mcp
```

### 4. Run as REST API

```bash
market-agent-api
# API docs at http://localhost:8000/docs
```

### 5. Try AI trading (works immediately with paper mode)

```bash
# In Cursor MCP or via REST API:
# ai_research_symbol("AAPL")     — gather live data + news
# ai_analyze_trade("AAPL")       — get buy/sell/hold signal
# ai_execute_trade("AAPL")       — analyze + execute (dry-run by default)
# ai_run_trading_cycle()         — analyze entire watchlist
```

Set `AI_API_KEY` in `.env` for GPT-powered analysis. Without it, the rule-based engine still works using technicals + news sentiment.

## AI Trading Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_API_KEY` | — | OpenAI-compatible API key for LLM decisions |
| `AI_DRY_RUN` | `true` | Simulate trades without executing |
| `AI_REQUIRE_CONFIRMATION` | `true` | Require `force=true` to execute |
| `AI_MIN_CONFIDENCE` | `0.65` | Minimum confidence to trade |
| `AI_MAX_SINGLE_TRADE_USD` | `500` | Max dollars per trade |
| `AI_WATCHLIST` | `AAPL,MSFT,...` | Default symbols for auto cycles |
| `AI_PAPER_STARTING_CASH` | `10000` | Paper trading starting balance |

## Getting API Credentials

### Polymarket

1. **Public data** — no credentials needed (Gamma, Data, CLOB orderbooks)
2. **Trading** — derive CLOB API credentials from your wallet:
   - Install the [Polymarket TypeScript/Python SDK](https://docs.polymarket.com/quickstart)
   - Use `client.deriveApiKey()` to get key, secret, passphrase
   - Set `POLYMARKET_WALLET_ADDRESS`, `POLYMARKET_CLOB_API_KEY`, `POLYMARKET_CLOB_SECRET`, `POLYMARKET_CLOB_PASSPHRASE`

Docs: https://docs.polymarket.com

### Kalshi

1. **Public data** — no credentials needed
2. **Trading** — create API keys at https://kalshi.com/account/profile:
   - Click "Create New API Key"
   - Save the **Key ID** and **RSA private key** (downloaded once)
   - Set `KALSHI_API_KEY_ID` and `KALSHI_PRIVATE_KEY_PATH`
   - Use `KALSHI_USE_DEMO=true` for sandbox (recommended for testing)

Docs: https://docs.kalshi.com

### Robinhood

1. Apply for partner access: https://go.robinhood.com/partner
2. Once approved, create OAuth app and set `ROBINHOOD_CLIENT_ID`, `ROBINHOOD_CLIENT_SECRET`
3. Direct users to the OAuth URL from `robinhood_get_auth_url` tool
4. Exchange the code with `robinhood_exchange_code`

## AI Agent Tools (MCP)

The MCP server exposes these tools:

### Polymarket
- `polymarket_search_markets` — search by keyword
- `polymarket_list_events` — browse events
- `polymarket_get_event` — event details by slug
- `polymarket_get_orderbook` — CLOB orderbook
- `polymarket_get_price` — current price
- `polymarket_get_positions` — wallet positions
- `polymarket_place_order` — limit order (auth required)
- `polymarket_cancel_order` — cancel order (auth required)
- `polymarket_get_open_orders` — list open orders (auth required)

### Kalshi
- `kalshi_list_events` — browse events
- `kalshi_get_event` — event by ticker
- `kalshi_list_markets` — browse markets
- `kalshi_get_market` — market details
- `kalshi_get_orderbook` — orderbook
- `kalshi_get_balance` — account balance (auth required)
- `kalshi_get_positions` — portfolio positions (auth required)
- `kalshi_place_order` — place order (auth required)
- `kalshi_cancel_order` — cancel order (auth required)

### Robinhood
- `robinhood_get_auth_url` — OAuth authorization URL
- `robinhood_exchange_code` — exchange OAuth code for tokens
- `robinhood_get_account` — account info (auth required)
- `robinhood_get_portfolio` — portfolio summary (auth required)
- `robinhood_get_positions` — stock positions (auth required)
- `robinhood_get_quotes` — stock quotes (auth required)

### General
- `connector_status` — health check for all platforms

### AI Trading Engine
- `ai_get_stock_quote` — live price, volume, sector
- `ai_get_stock_news` — real-time news from web
- `ai_get_technicals` — RSI, SMA, trend analysis
- `ai_research_symbol` — full intelligence bundle
- `ai_analyze_trade` — AI buy/sell/hold recommendation
- `ai_execute_trade` — analyze + execute with risk checks
- `ai_run_trading_cycle` — automated watchlist trading
- `ai_get_paper_portfolio` — paper trading account
- `ai_search_web` — web research on any topic

### Finding the best trades
- `find_best_trades` — scan the whole market and rank the strongest setups
- `scan_stocks` — score and rank a list of symbols, filterable by direction
- `scan_sector` — best setups within a sector
- `scan_market_movers` — today's gainers, losers and most active
- `scan_trending_tickers` — what the market is watching, with live quotes
- `scan_insider_buys` — stocks with multiple insiders buying (cluster buys)
- `scan_insider_buys_market_wide` — every notable insider purchase market-wide
- `scan_prediction_markets` — best Kalshi / Polymarket contracts
- `compare_stocks` — rank symbols head-to-head

## Example: AI agent workflow

```
User: "Should I buy Apple stock right now?"

Agent calls: ai_research_symbol("AAPL")
Agent calls: ai_analyze_trade("AAPL")

Agent: "Based on RSI 28 (oversold), positive earnings news, and bullish SMA trend,
        I recommend BUY with 72% confidence. 6 shares at $178.50."

User: "Execute it on paper"

Agent calls: ai_execute_trade("AAPL", platform="paper", force=true)
```

```
User: "Run an automated trading cycle on my watchlist"

Agent calls: ai_run_trading_cycle(symbols="AAPL,NVDA,TSLA,MSFT", platform="paper")
```

```
User: "I don't know what to buy — find me the best trades"

Agent calls: find_best_trades(limit=5)

Agent: "Top setup is OSCR BUY (score 78): 4 insiders bought $1.5M this week and
        RSI is 33. Entry $15.10, stop $13.80, target $18.10 (2.3:1 risk/reward).
        Runner-up is AMD BUY on a momentum breakout above the 20/50-day averages."

User: "Take the first one"

Agent calls: ai_execute_trade("OSCR", platform="paper", force=true)
```

## REST API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Platform status |
| GET | `/polymarket/search?q=` | Search markets |
| GET | `/polymarket/events` | List events |
| GET | `/polymarket/orderbook/{token_id}` | Orderbook |
| GET | `/kalshi/markets` | List markets |
| GET | `/kalshi/markets/{ticker}/orderbook` | Orderbook |
| GET | `/kalshi/balance` | Balance (auth) |
| POST | `/kalshi/orders` | Place order (auth) |
| GET | `/robinhood/auth-url` | OAuth URL |
| GET | `/robinhood/portfolio` | Portfolio (auth) |
| GET | `/ai/research/{symbol}` | Full intelligence gathering |
| GET | `/ai/analyze/{symbol}` | AI trade signal |
| POST | `/ai/execute/{symbol}` | Analyze + execute |
| POST | `/ai/cycle` | Automated watchlist cycle |
| GET | `/ai/paper-portfolio` | Paper trading account |
| GET | `/scan/best` | Rank the best trades across the market |
| GET | `/scan/stocks?symbols=` | Score and rank specific symbols |
| GET | `/scan/sector/{sector}` | Best setups in a sector |
| GET | `/scan/movers` | Gainers, losers, most active |
| GET | `/scan/trending` | Trending tickers with quotes |
| GET | `/scan/insider-buys` | Insider cluster buys |
| GET | `/scan/insider-market-wide` | All notable insider purchases |
| GET | `/scan/predictions?platform=` | Best prediction-market contracts |
| GET | `/scan/compare?symbols=` | Head-to-head ranking |

Full interactive docs at `http://localhost:8000/docs` when the API server is running.

## Security

- Credentials are loaded from environment variables / `.env` — never hardcoded
- Kalshi uses RSA-PSS request signing (private key stays local)
- Polymarket uses HMAC-signed CLOB headers
- Robinhood uses standard OAuth 2.0 bearer tokens
- **Never commit `.env` or private keys to version control**

## Development

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT
