"""Shared bot logic for Telegram and Discord."""

from __future__ import annotations

from market_agent.ai.models import ScanReport, TradeOpportunity
from market_agent.ai.opportunity_scanner import OpportunityScanner
from market_agent.config import BotSettings, Settings, load_settings
from market_agent.growth.growth_trader import GrowthTrader
from market_agent.trader.auto_executor import AutoExecutor
from market_agent.trader.auto_trader import AutoTrader
from market_agent.ai.market_predictor import MarketPredictor

HELP_TEXT = """
*Market Agent Bot* — AI trading on Polymarket, Kalshi & Robinhood

*Find the best trades*
/best — scan the market and rank the top trade setups
/scan `AAPL,MSFT,NVDA` — score and rank specific symbols
/movers — biggest gainers and losers today
/trending — tickers people are watching right now
/sector `tech` — best setups in a sector (tech, ai, finance, energy, healthcare, consumer, crypto)
/insider\\_buys — stocks where multiple insiders are buying
/opportunities `kalshi` — best prediction-market contracts
/compare `AAPL MSFT` — head-to-head ranking
/watchlist `add AAPL` — view or edit your watchlist

*Market analysis & predictions*
/quote `AAPL` — live stock price
/news `AAPL` — latest news
/research `AAPL` — full intel (price + news + insider + technicals)
/predict `AAPL` — price forecast, buy/sell zones, direction
/insider `AAPL` — SEC insider trade history (OpenInsider.com)
/analyze `AAPL` — AI buy/sell/hold signal with reasoning
/signals — buy/sell signals for entire watchlist

*Execute trades*
/trade `AAPL` — analyze + execute immediately
/auto_start — start auto buy/sell on watchlist (runs every 15min)
/auto_stop — stop auto-trading
/auto_status — auto-trader status
/portfolio — paper portfolio
/cycle — run one AI cycle on watchlist

*Growth (live multi-platform)*
/growth_setup `1000` — set starting capital (targets 2x/3x)
/growth — growth progress & milestones
/growth_run — live cycle on all platforms
/platforms — broker connection status

*Other*
/status — system health
/help — this message

_Auto-trader buys when AI predicts bullish + executes sells on bearish signals._
""".strip()


def _format_opportunity(rank: int, o: TradeOpportunity) -> list[str]:
    emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(o.action.value, "⚪")
    header = f"*{rank}. `{o.symbol}`* {emoji} {o.action.value.upper()} — score {o.score:.0f}"
    if o.name:
        header += f"\n   _{o.name[:60]}_"
    lines = [header]

    price_bits = []
    if o.price:
        price_bits.append(f"${o.price:.2f}")
    if o.change_pct is not None:
        price_bits.append(f"{o.change_pct:+.2f}%")
    if o.upside_pct is not None:
        price_bits.append(f"target {o.upside_pct:+.1f}%")
    if price_bits:
        lines.append(f"   {' | '.join(price_bits)}")

    if o.entry_price and o.stop_loss and o.take_profit:
        rr = f" (R:R {o.risk_reward:.1f})" if o.risk_reward else ""
        lines.append(
            f"   Entry ${o.entry_price:.2f} | Stop ${o.stop_loss:.2f} | "
            f"Target ${o.take_profit:.2f}{rr}"
        )

    lines.append(f"   Setup: {o.setup} ({o.confidence:.0%} confidence)")
    for reason in o.reasons[:2]:
        lines.append(f"   • {reason}")
    for catalyst in o.catalysts[:2]:
        lines.append(f"   ⚡ {catalyst}")
    for warning in o.warnings[:1]:
        lines.append(f"   ⚠️ {warning}")
    return lines


def _format_scan(report: ScanReport, title: str) -> str:
    if not report.opportunities:
        return f"{title}\n\n{report.summary}"
    lines = [f"{title}\n", f"_{report.summary}_\n"]
    for i, opp in enumerate(report.opportunities, 1):
        lines.extend(_format_opportunity(i, opp))
        lines.append("")
    lines.append("_Trade it with_ `/trade SYMBOL` _or dig in with_ `/analyze SYMBOL`")
    return "\n".join(lines)


class BotService:
    """Backend service shared by Telegram and Discord bots."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self.trader = AutoTrader(self.settings)
        self.growth = GrowthTrader(self.settings)
        self.predictor = MarketPredictor()
        self.auto_executor = AutoExecutor(self.trader, self.settings)
        self.bot_settings = self.settings.bot
        self.scanner = OpportunityScanner(
            researcher=self.trader.researcher,
            predictor=self.predictor,
            kalshi=self.trader.kalshi,
            polymarket=self.trader.polymarket,
        )
        self._watchlist = self.settings.ai.symbols()

    async def close(self) -> None:
        if self.auto_executor.is_running:
            await self.auto_executor.stop()
        await self.scanner.close()
        await self.trader.close()
        await self.growth.close()

    def is_authorized(self, user_id: str) -> bool:
        allowed = self.bot_settings.allowed_user_ids()
        if not allowed:
            return True
        return str(user_id) in allowed

    def auth_denied_message(self) -> str:
        return "⛔ Unauthorized. Ask the bot owner to add your user ID to BOT_ALLOWED_USERS."

    async def cmd_help(self) -> str:
        return HELP_TEXT

    async def cmd_status(self) -> str:
        pm = await self.trader.polymarket.health()
        ka = await self.trader.kalshi.health()
        rh = await self.trader.robinhood.health()
        live, live_msg = self.growth._live_enabled()
        engine = "LLM" if self.trader.llm and self.trader.llm.is_configured else "Rules"
        return (
            f"🟢 *Market Agent Status*\n\n"
            f"AI engine: {engine}\n"
            f"Dry run: {self.settings.ai.dry_run}\n"
            f"Live trading: {'✅' if live else '❌'} {live_msg}\n\n"
            f"Polymarket: {pm.get('status', '?')}\n"
            f"Kalshi: {ka.get('status', '?')} ({ka.get('environment', '')})\n"
            f"Robinhood: {rh.get('status', '?')}"
        )

    async def cmd_quote(self, symbol: str) -> str:
        symbol = symbol.upper().strip()
        research = await self.trader.research(symbol)
        m = research.market
        if not m or not m.price:
            return f"❌ No data for `{symbol}`"
        lines = [
            f"📈 *{symbol}* — {m.extra.get('name', symbol)}",
            f"Price: ${m.price:.2f}",
            f"Change: {m.change_pct:+.2f}%",
        ]
        if m.volume:
            lines.append(f"Volume: {m.volume:,}")
        lines.append(f"Sector: {m.sector or 'N/A'}")
        lines.append(f"P/E: {m.pe_ratio or 'N/A'}")
        return "\n".join(lines)

    async def cmd_news(self, symbol: str, limit: int = 5) -> str:
        symbol = symbol.upper().strip()
        news = await self.trader.researcher.news.get_stock_news(symbol, limit)
        if not news:
            return f"No news found for `{symbol}`"
        lines = [f"📰 *News for {symbol}*\n"]
        for i, n in enumerate(news[:limit], 1):
            lines.append(f"{i}. {n.title}\n   _{n.source}_")
        return "\n".join(lines)

    async def cmd_research(self, symbol: str) -> str:
        symbol = symbol.upper().strip()
        research = await self.trader.research(symbol)
        m = research.market
        tech = research.technical_signals
        lines = [f"🔍 *Research: {symbol}*\n"]
        if m:
            lines.append(f"Price: ${m.price:.2f} ({m.change_pct:+.2f}%)")
        if tech:
            lines.append(
                f"RSI: {tech.get('rsi_14', 'N/A')} | Trend: {tech.get('trend', 'N/A')}\n"
                f"SMA20: {tech.get('sma_20', 'N/A')} | SMA50: {tech.get('sma_50', 'N/A')}"
            )
        if research.news:
            lines.append(f"\n*Top news:*")
            for n in research.news[:3]:
                lines.append(f"• {n.title[:80]}")
        if research.insider_summary:
            s = research.insider_summary
            lines.append(
                f"\n*Insider ({s.period_days}d):* {s.net_sentiment.upper()} — "
                f"{s.purchases} buys (${s.buy_value_usd:,.0f}) / "
                f"{s.sales} sells (${s.sell_value_usd:,.0f})"
            )
        if research.web_snippets:
            lines.append(f"\n*Web:* {research.web_snippets[0][:150]}...")
        return "\n".join(lines)

    async def cmd_analyze(self, symbol: str, platform: str = "paper") -> str:
        symbol = symbol.upper().strip()
        research, signal = await self.trader.analyze(symbol, platform=platform)
        emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(signal.action.value, "⚪")
        price = research.market.price if research.market else signal.limit_price
        lines = [
            f"{emoji} *{signal.action.value.upper()}* `{symbol}`",
            f"Confidence: {signal.confidence:.0%}",
            f"Quantity: {signal.quantity}",
            f"Platform: {platform}",
        ]
        if price:
            lines.append(f"Price: ${price:.2f}")
        lines.append(f"\n*Reasoning:*\n{signal.reasoning[:500]}")
        if signal.risk_factors:
            lines.append(f"\n*Risks:* {', '.join(signal.risk_factors[:3])}")
        if signal.news_catalysts:
            lines.append(f"*Catalysts:* {', '.join(signal.news_catalysts[:3])}")
        return "\n".join(lines)

    async def cmd_trade(self, symbol: str, platform: str = "paper", force: bool = False) -> str:
        symbol = symbol.upper().strip()
        _, signal = await self.trader.analyze(symbol, platform=platform)
        if signal.action.value == "hold":
            return f"🟡 HOLD `{symbol}` — no trade executed.\n{signal.reasoning[:300]}"
        result = await self.trader.execute_signal(signal, force=force, platform=platform)
        emoji = "✅" if result.executed else "⚠️"
        return (
            f"{emoji} *Trade Result*\n"
            f"Action: {signal.action.value.upper()} {signal.quantity} {symbol}\n"
            f"Platform: {platform}\n"
            f"Executed: {result.executed}\n"
            f"{result.message}"
        )

    async def cmd_portfolio(self) -> str:
        pf = await self.trader.get_paper_portfolio()
        lines = [
            f"💼 *Paper Portfolio*\n",
            f"Cash: ${pf['cash']:,.2f}",
            f"Total value: ${pf['total_value']:,.2f}",
            f"Orders: {pf.get('order_count', 0)}\n",
        ]
        positions = pf.get("positions", {})
        if positions:
            lines.append("*Positions:*")
            for sym, pos in positions.items():
                pnl = pos.get("pnl", 0)
                lines.append(
                    f"• {sym}: {pos['quantity']} @ ${pos.get('current_price', pos['avg_cost']):.2f} "
                    f"(P&L: ${pnl:+,.2f})"
                )
        else:
            lines.append("_No open positions_")
        return "\n".join(lines)

    async def cmd_cycle(self, platform: str = "paper", force: bool = False) -> str:
        report = await self.trader.run_cycle(platform=platform, force=force)
        executed = sum(1 for e in report.executions if e.executed)
        lines = [f"🔄 *Trading Cycle* ({platform})\n", report.summary, "\n*Signals:*"]
        for s in report.signals:
            if s.action.value != "hold":
                lines.append(f"• {s.action.value.upper()} {s.symbol} ({s.confidence:.0%})")
        lines.append(f"\nExecuted: {executed}/{len(report.executions)}")
        return "\n".join(lines)

    async def cmd_growth_setup(self, capital: float) -> str:
        result = await self.growth.setup(starting_capital=capital)
        g = result["growth_status"]
        return (
            f"🎯 *Growth Trading Initialized*\n\n"
            f"Starting capital: ${g['starting_capital']:,.2f}\n"
            f"Targets: {g['targets']}\n\n"
            f"_{result['disclaimer']}_"
        )

    async def cmd_growth_status(self) -> str:
        status = await self.growth.status()
        g = status["growth"]
        lines = [
            f"📊 *Growth Progress*\n",
            f"Value: ${g['current_value']:,.2f} ({g['multiplier']:.2f}x)",
            f"P&L: ${g['total_pnl']:+,.2f} ({g['total_pnl_pct']:+.1f}%)",
            f"Milestones: {', '.join(g['milestones_hit']) or 'none yet'}\n",
        ]
        for label, prog in g.get("progress", {}).items():
            bar = "█" * int(prog["progress_pct"] / 10) + "░" * (10 - int(prog["progress_pct"] / 10))
            hit = "✅" if prog["hit"] else ""
            lines.append(f"{label} ${prog['target_usd']:,.0f} [{bar}] {prog['progress_pct']}% {hit}")

        platforms = status.get("platforms", {})
        lines.append(f"\n*Platform balances:*")
        for name, data in platforms.items():
            if name == "total_usd":
                continue
            usd = data.get("total_usd", 0) if isinstance(data, dict) else 0
            st = data.get("status", "") if isinstance(data, dict) else ""
            lines.append(f"• {name}: ${usd:,.2f} ({st})")
        lines.append(f"\n*Total:* ${platforms.get('total_usd', 0):,.2f}")
        return "\n".join(lines)

    async def cmd_growth_run(self, force: bool = False) -> str:
        result = await self.growth.run_live_cycle(force=force)
        if result.get("halted"):
            return f"🛑 *HALTED*\n{result['reason']}"
        if result.get("error"):
            return f"❌ {result['error']}\n_{result.get('hint', '')}_"
        return f"🚀 *Live Cycle Complete*\n\n{result.get('summary', '')}"

    async def cmd_platforms(self) -> str:
        readiness = self.growth.balances.platform_readiness()
        live = await self.growth._check_live_ready()
        lines = ["🔌 *Platform Readiness*\n"]
        for name, info in readiness.items():
            icon = "✅" if info["ready"] else "❌"
            needs = ", ".join(info["needs"]) if info["needs"] else "ready"
            lines.append(f"{icon} *{name}*: {needs}")
        lines.append(f"\nLive trading: {'✅' if live['live_enabled'] else '❌'}")
        lines.append(f"_{live['message']}_")
        return "\n".join(lines)

    async def cmd_predict(self, symbol: str) -> str:
        symbol = symbol.upper().strip()
        research = await self.trader.research(symbol)
        prediction = await self.predictor.predict(research)
        emoji = {"bullish": "📈", "bearish": "📉", "neutral": "➡️"}.get(prediction.direction, "➡️")
        action_emoji = {"buy": "🟢 BUY", "sell": "🔴 SELL", "hold": "🟡 HOLD"}.get(
            prediction.recommended_action.value, "🟡 HOLD"
        )
        upside = 0.0
        if prediction.price_target_1d and prediction.current_price:
            upside = (prediction.price_target_1d - prediction.current_price) / prediction.current_price * 100

        lines = [
            f"{emoji} *Prediction: {symbol}*\n",
            f"Direction: *{prediction.direction.upper()}* ({prediction.confidence:.0%})",
            f"Action: {action_emoji}",
            f"\nCurrent: ${prediction.current_price:.2f}",
            f"1-day target: ${prediction.price_target_1d:.2f} ({upside:+.1f}%)" if prediction.price_target_1d else "",
            f"1-week target: ${prediction.price_target_1w:.2f}" if prediction.price_target_1w else "",
            f"\nBuy zone: ${prediction.buy_zone:.2f} | Sell zone: ${prediction.sell_zone:.2f}",
            f"Support: ${prediction.support:.2f} | Resistance: ${prediction.resistance:.2f}",
            f"\n*Factors:*",
        ]
        for f in prediction.factors:
            lines.append(f"• {f}")
        return "\n".join(l for l in lines if l)

    async def cmd_insider(self, symbol: str, days: int = 180) -> str:
        symbol = symbol.upper().strip()
        summary = await self.trader.researcher.insider.get_summary(symbol, days=min(days, 365))
        trades = await self.trader.researcher.insider.get_trades(symbol, limit=15, days=days)

        emoji = {"bullish": "🟢", "bearish": "🔴", "neutral": "🟡"}.get(summary.net_sentiment, "➡️")
        lines = [
            f"🏛️ *Insider Trades: {symbol}* (OpenInsider / SEC Form 4)\n",
            f"Period: last {summary.period_days} days",
            f"Sentiment: {emoji} *{summary.net_sentiment.upper()}*",
            f"Purchases: {summary.purchases} (${summary.buy_value_usd:,.0f})",
            f"Sales: {summary.sales} (${summary.sell_value_usd:,.0f})",
            f"\n*Recent transactions:*",
        ]
        if not trades:
            lines.append("_No insider trades found for this period._")
        for t in trades[:12]:
            icon = "🟢" if t.is_purchase else "🔴" if t.is_sale else "⚪"
            val = f"${t.value:,.0f}" if t.value else "N/A"
            lines.append(
                f"{icon} `{t.trade_date}` **{t.insider_name}** ({t.title})\n"
                f"   {t.trade_type} — {t.quantity:,} shares @ ${t.price or 0:.2f} = {val}"
            )
        lines.append(f"\n_Source: openinsider.com (SEC Form 4 filings)_")
        return "\n".join(lines)

    async def cmd_signals(self) -> str:
        signals = await self.auto_executor.get_signals()
        lines = ["📡 *Watchlist Signals*\n"]
        for sig in signals:
            if sig.get("error"):
                lines.append(f"❌ `{sig['symbol']}`: {sig['error']}")
                continue
            emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(sig["action"], "⚪")
            pred = sig.get("prediction", {})
            target = pred.get("price_target_1d", "?")
            direction = pred.get("direction", "?")
            lines.append(
                f"{emoji} `{sig['symbol']}` {sig['action'].upper()} ({sig['confidence']:.0%}) "
                f"| {direction} → ${target}"
            )
        return "\n".join(lines)

    # ── Opportunity discovery ───────────────────────────────────────────────

    async def cmd_best_trades(self, limit: int = 8, deep: bool = False) -> str:
        report = await self.scanner.find_best_trades(limit=limit, deep=deep)
        return _format_scan(report, title="🏆 Best Trades Right Now")

    async def cmd_scan(self, symbols: list[str] | None = None, limit: int = 10) -> str:
        report = await self.scanner.scan_stocks(
            symbols=symbols or self._watchlist, limit=limit
        )
        return _format_scan(report, title="🔎 Scan Results")

    async def cmd_sector_scan(self, sector: str, limit: int = 8) -> str:
        report = await self.scanner.scan_sector(sector, limit=limit)
        return _format_scan(report, title=f"🏭 Best in {sector.title()}")

    async def cmd_movers(self, limit: int = 8) -> str:
        gainers = await self.scanner.screener.top_gainers(limit=limit)
        losers = await self.scanner.screener.top_losers(limit=limit)
        lines = ["📊 *Market Movers*\n", "*Top gainers:*"]
        for g in gainers:
            lines.append(
                f"🟢 `{g.symbol}` ${g.price or 0:.2f} {g.change_pct:+.2f}%"
                if g.change_pct is not None
                else f"🟢 `{g.symbol}`"
            )
        lines.append("\n*Top losers (dip candidates):*")
        for l in losers:
            lines.append(
                f"🔴 `{l.symbol}` ${l.price or 0:.2f} {l.change_pct:+.2f}%"
                if l.change_pct is not None
                else f"🔴 `{l.symbol}`"
            )
        lines.append("\n_Use /scan SYM to score any of these._")
        return "\n".join(lines)

    async def cmd_trending(self, limit: int = 15) -> str:
        symbols = await self.scanner.screener.trending(limit)
        quotes = await self.scanner.screener.get_universe_quotes(symbols)
        lines = ["🔥 *Trending Tickers*\n"]
        for q in quotes:
            change = f"{q.change_pct:+.2f}%" if q.change_pct is not None else "—"
            lines.append(f"• `{q.symbol}` ${q.price or 0:.2f} ({change})")
        lines.append("\n_Run /best to rank these into actionable setups._")
        return "\n".join(lines)

    async def cmd_insider_buys(self, days: int = 14, min_insiders: int = 2, limit: int = 10) -> str:
        report = await self.scanner.scan_insider_buys(
            days=days, min_insiders=min_insiders, limit=limit
        )
        if not report.opportunities:
            return f"🏛️ No insider cluster buys found in the last {days} days."
        lines = [
            f"🏛️ *Insider Cluster Buys* (last {days}d, {min_insiders}+ insiders)\n",
        ]
        for i, o in enumerate(report.opportunities, 1):
            cluster = o.metadata.get("cluster", {})
            lines.append(
                f"*{i}. `{o.symbol}`* — {cluster.get('insider_count', 0)} insiders, "
                f"${cluster.get('total_value_usd', 0):,.0f}"
            )
            if o.price:
                lines.append(
                    f"   ${o.price:.2f} | stop ${o.stop_loss:.2f} | target ${o.take_profit:.2f}"
                )
            lines.append(f"   {o.reasons[0] if o.reasons else ''}")
        lines.append("\n_Source: openinsider.com (SEC Form 4)_")
        return "\n".join(lines)

    async def cmd_opportunities(self, platform: str = "kalshi", limit: int = 8) -> str:
        report = await self.scanner.find_prediction_opportunities(
            platform=platform, limit=limit
        )
        if not report.opportunities:
            return f"🎲 {report.summary}"
        lines = [f"🎲 *Prediction Market Opportunities* ({platform})\n"]
        for i, o in enumerate(report.opportunities, 1):
            lines.append(f"*{i}. {o.name[:90]}*")
            lines.append(f"   `{o.symbol}` — {o.setup} (score {o.score:.0f})")
            for r in o.reasons[:2]:
                lines.append(f"   • {r}")
            if o.warnings:
                lines.append(f"   ⚠️ {o.warnings[0]}")
        lines.append("\n_Prices are implied probabilities; size positions accordingly._")
        return "\n".join(lines)

    async def cmd_compare(self, symbols: list[str]) -> str:
        symbols = [s.upper().strip() for s in symbols if s.strip()][:8]
        if len(symbols) < 2:
            return "Give me at least two symbols, e.g. `/compare AAPL MSFT NVDA`"
        ranked = await self.scanner.compare(symbols)
        if not ranked:
            return "❌ Couldn't fetch data for those symbols."
        lines = [f"⚖️ *Head-to-head: {', '.join(symbols)}*\n"]
        for i, o in enumerate(ranked, 1):
            emoji = {"buy": "🟢", "sell": "🔴", "hold": "🟡"}.get(o.action.value, "⚪")
            change = f"{o.change_pct:+.2f}%" if o.change_pct is not None else "—"
            lines.append(
                f"*{i}. `{o.symbol}`* {emoji} {o.action.value.upper()} — score {o.score:.0f}\n"
                f"   ${o.price or 0:.2f} ({change}) | {o.setup} | {o.confidence:.0%} confidence"
            )
        lines.append(f"\n🏆 Strongest: *{ranked[0].symbol}* ({ranked[0].action.value.upper()})")
        return "\n".join(lines)

    async def cmd_watchlist(self, action: str = "list", symbols: list[str] | None = None) -> str:
        action = (action or "list").lower()
        symbols = [s.upper().strip() for s in (symbols or []) if s.strip()]

        if action == "add" and symbols:
            for s in symbols:
                if s not in self._watchlist:
                    self._watchlist.append(s)
        elif action in ("remove", "rm", "del") and symbols:
            self._watchlist = [s for s in self._watchlist if s not in symbols]
        elif action == "clear":
            self._watchlist = []
        elif action not in ("list", "show", ""):
            return "Usage: `/watchlist list|add|remove|clear [SYMBOLS]`"

        self.settings.ai.watchlist = ",".join(self._watchlist)
        note = "_Used by /signals, /scan and /cycle._"
        if self.auto_executor.is_running:
            note += (
                "\n_The auto-trader keeps the list it started with — "
                "restart it with /auto\\_stop then /auto\\_start to pick up changes._"
            )
        return (
            f"👁️ *Watchlist* ({len(self._watchlist)})\n"
            f"{', '.join(self._watchlist) if self._watchlist else '_empty_'}\n\n"
            f"{note}"
        )

    async def cmd_auto_start(
        self,
        platform: str = "paper",
        interval_min: int = 15,
        force: bool = False,
        notify_callback=None,
    ) -> str:
        if notify_callback:
            self.auto_executor.set_notify_callback(notify_callback)
        result = await self.auto_executor.start(platform=platform, interval_min=interval_min, force=force)
        return (
            f"🤖 *Auto-Trader Started*\n\n"
            f"Platform: {result.get('platform', platform)}\n"
            f"Symbols: {', '.join(result.get('symbols', []))}\n"
            f"Interval: every {interval_min} min\n\n"
            f"The bot will automatically:\n"
            f"• *BUY* when prediction is bullish (confidence ≥ 65%)\n"
            f"• *SELL* when prediction is bearish and you hold the stock\n"
            f"• Skip if signal is uncertain\n\n"
            f"Use /auto_stop to halt."
        )

    async def cmd_auto_stop(self) -> str:
        result = await self.auto_executor.stop()
        return f"🛑 *Auto-Trader Stopped*\nTrades executed: {result.get('trades_executed', 0)}"

    async def cmd_auto_status(self) -> str:
        status = self.auto_executor.status()
        running = "🟢 RUNNING" if status.get("running") else "🔴 STOPPED"
        lines = [
            f"🤖 *Auto-Trader* — {running}\n",
            f"Platform: {status.get('platform', 'paper')}",
            f"Symbols: {', '.join(status.get('symbols', []))}",
            f"Interval: {status.get('interval_min', 15)} min",
            f"Trades executed: {status.get('trades_executed', 0)}",
            f"Last run: {status.get('last_run') or 'never'}",
        ]
        history = status.get("history", [])[-5:]
        if history:
            lines.append("\n*Recent trades:*")
            for t in history:
                lines.append(f"• {t['action'].upper()} {t['quantity']} {t['symbol']} ({t['timestamp'][:16]})")
        return "\n".join(lines)
