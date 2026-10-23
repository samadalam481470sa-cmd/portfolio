"""Opportunity scanner — finds and ranks the best trades across the market.

Rather than analysing a symbol you already picked, this scans a universe of
candidates (movers, trending names, insider-buy clusters, sector baskets or a
custom list), scores each one, and returns the highest-conviction setups with
concrete entry, stop and target levels.
"""

from __future__ import annotations

import asyncio
from typing import Any

from market_agent.ai.market_predictor import MarketPredictor
from market_agent.ai.models import (
    AssetType,
    MarketPrediction,
    ResearchBundle,
    ScanReport,
    TradeAction,
    TradeOpportunity,
)
from market_agent.intelligence.researcher import IntelligenceResearcher
from market_agent.intelligence.screener import MarketScreener

MAX_CONCURRENT_SCANS = 8


class OpportunityScanner:
    """Scans and ranks trade opportunities across stocks and prediction markets."""

    def __init__(
        self,
        researcher: IntelligenceResearcher,
        predictor: MarketPredictor | None = None,
        screener: MarketScreener | None = None,
        kalshi: Any = None,
        polymarket: Any = None,
    ) -> None:
        self.researcher = researcher
        self.predictor = predictor or MarketPredictor()
        # Share the researcher's Yahoo session so the crumb handshake and rate
        # limiting are coordinated across both callers.
        self.screener = screener or MarketScreener(
            session=getattr(getattr(researcher, "market_data", None), "session", None)
        )
        self.kalshi = kalshi
        self.polymarket = polymarket
        self._sem = asyncio.Semaphore(MAX_CONCURRENT_SCANS)

    async def close(self) -> None:
        await self.screener.close()

    # ── Stock scanning ──────────────────────────────────────────────────────

    async def scan_stocks(
        self,
        symbols: list[str] | None = None,
        limit: int = 10,
        min_score: float = 0.0,
        action: str = "any",
        include_news: bool = False,
    ) -> ScanReport:
        """Score every symbol in the universe and return the top-ranked setups.

        ``action`` accepts a specific direction ("buy"/"sell"), "any" to drop
        HOLD ratings, or "all" to keep everything for further processing.
        """
        universe = [s.upper().strip() for s in (symbols or await self.screener.trending(25))]
        universe = list(dict.fromkeys(universe))  # de-dupe, keep order

        results = await asyncio.gather(
            *(self._score_symbol(sym, include_news) for sym in universe),
            return_exceptions=True,
        )
        opportunities = [r for r in results if isinstance(r, TradeOpportunity)]

        action = action.lower()
        if action in ("buy", "sell", "hold"):
            wanted = TradeAction(action)
            opportunities = [o for o in opportunities if o.action == wanted]
        elif action != "all":
            opportunities = [o for o in opportunities if o.action != TradeAction.HOLD]

        opportunities = [o for o in opportunities if o.score >= min_score]
        opportunities.sort(key=lambda o: o.score, reverse=True)
        top = opportunities[:limit]
        scanned = len([r for r in results if not isinstance(r, Exception)])

        return ScanReport(
            scan_type="stocks",
            universe_size=len(universe),
            scanned=scanned,
            opportunities=top,
            summary=_summarize(top, len(universe), scanned),
        )

    async def find_best_trades(self, limit: int = 10, deep: bool = False) -> ScanReport:
        """Broadest search: combines movers, trending names and insider clusters."""
        gainers, losers, active, trending, clusters = await asyncio.gather(
            self.screener.top_gainers(limit=12),
            self.screener.top_losers(limit=12),
            self.screener.most_active(limit=12),
            self.screener.trending(15),
            self._safe_clusters(),
            return_exceptions=True,
        )

        candidates: list[str] = []
        catalyst_tags: dict[str, list[str]] = {}

        def add(syms: Any, tag: str) -> None:
            if isinstance(syms, Exception) or not syms:
                return
            for item in syms:
                sym = item if isinstance(item, str) else getattr(item, "symbol", "")
                if not sym:
                    continue
                sym = sym.upper()
                candidates.append(sym)
                catalyst_tags.setdefault(sym, []).append(tag)

        add(gainers, "top gainer")
        add(losers, "top loser / dip")
        add(active, "high volume")
        add(trending, "trending")

        cluster_map: dict[str, dict[str, Any]] = {}
        if not isinstance(clusters, Exception) and clusters:
            for c in clusters[:15]:
                sym = str(c["symbol"]).upper()
                cluster_map[sym] = c
                candidates.append(sym)
                catalyst_tags.setdefault(sym, []).append(
                    f"{c['insider_count']} insiders bought ${c['total_value_usd']:,.0f}"
                )

        universe = list(dict.fromkeys(candidates))
        report = await self.scan_stocks(
            symbols=universe, limit=len(universe), action="all", include_news=deep
        )

        # Fold in discovery context and reward insider conviction
        for opp in report.opportunities:
            tags = catalyst_tags.get(opp.symbol, [])
            opp.catalysts.extend(t for t in tags if t not in opp.catalysts)
            cluster = cluster_map.get(opp.symbol)
            if not cluster or opp.action == TradeAction.SELL:
                continue
            # A multi-insider buy is a thesis on its own, so it can carry a name
            # the technicals alone would have left as HOLD.
            opp.score += min(20.0, 5.0 * float(cluster["insider_count"]))
            opp.action = TradeAction.BUY
            opp.setup = "insider cluster buy"
            opp.metadata["insider_cluster"] = cluster

        report.opportunities = [
            o for o in report.opportunities if o.action != TradeAction.HOLD
        ]
        report.opportunities.sort(key=lambda o: o.score, reverse=True)
        report.opportunities = report.opportunities[:limit]
        report.scan_type = "best_trades"
        report.summary = _summarize(
            report.opportunities, report.universe_size, report.scanned
        )
        return report

    async def scan_sector(self, sector: str, limit: int = 8) -> ScanReport:
        universe = await self.screener.sector_universe(sector)
        report = await self.scan_stocks(symbols=universe, limit=limit)
        report.scan_type = f"sector:{sector}"
        return report

    async def scan_insider_buys(
        self, days: int = 14, min_insiders: int = 2, limit: int = 10
    ) -> ScanReport:
        """Rank stocks with recent multi-insider buying, enriched with price data."""
        clusters = await self.researcher.insider.get_cluster_buys(
            days=days, min_insiders=min_insiders, limit=limit * 2
        )
        if not clusters:
            return ScanReport(
                scan_type="insider_buys",
                summary=f"No insider cluster buys found in the last {days} days.",
            )

        symbols = [str(c["symbol"]) for c in clusters]
        quotes = {q.symbol: q for q in await self.screener.get_universe_quotes(symbols)}

        opportunities = []
        for c in clusters:
            sym = str(c["symbol"]).upper()
            quote = quotes.get(sym)
            price = quote.price if quote else None
            score = min(60.0, 8.0 * float(c["insider_count"])) + min(
                25.0, float(c["total_value_usd"]) / 200_000
            )
            opportunities.append(
                TradeOpportunity(
                    symbol=sym,
                    name=(quote.extra.get("name", "") if quote else ""),
                    action=TradeAction.BUY,
                    score=round(score, 2),
                    confidence=round(min(0.8, 0.45 + 0.08 * float(c["insider_count"])), 2),
                    price=price,
                    change_pct=quote.change_pct if quote else None,
                    entry_price=price,
                    stop_loss=round(price * 0.92, 2) if price else None,
                    take_profit=round(price * 1.20, 2) if price else None,
                    risk_reward=2.5,
                    setup="insider cluster buy",
                    catalysts=[
                        f"{c['insider_count']} insiders bought "
                        f"${c['total_value_usd']:,.0f} since {c['latest_date']}"
                    ],
                    reasons=[f"Buyers: {', '.join(c['insiders'][:3])}"],
                    metadata={"cluster": c},
                )
            )

        opportunities.sort(key=lambda o: o.score, reverse=True)
        top = opportunities[:limit]
        return ScanReport(
            scan_type="insider_buys",
            universe_size=len(clusters),
            scanned=len(clusters),
            opportunities=top,
            summary=(
                f"{len(top)} stocks with {min_insiders}+ insiders buying in the last {days} days. "
                f"Top: {', '.join(o.symbol for o in top[:5])}"
            ),
        )

    async def compare(self, symbols: list[str]) -> list[TradeOpportunity]:
        """Score several symbols head-to-head so the strongest one is obvious."""
        results = await asyncio.gather(
            *(self._score_symbol(s.upper().strip(), include_news=True) for s in symbols),
            return_exceptions=True,
        )
        opportunities = [r for r in results if isinstance(r, TradeOpportunity)]
        opportunities.sort(key=lambda o: o.score, reverse=True)
        return opportunities

    # ── Prediction markets ──────────────────────────────────────────────────

    async def find_prediction_opportunities(
        self, platform: str = "kalshi", limit: int = 10
    ) -> ScanReport:
        """Find mispriced or high-carry contracts on Kalshi / Polymarket."""
        platform = platform.lower()
        if platform == "kalshi":
            opportunities = await self._scan_kalshi(limit)
        elif platform == "polymarket":
            opportunities = await self._scan_polymarket(limit)
        else:
            kalshi, poly = await asyncio.gather(
                self._scan_kalshi(limit), self._scan_polymarket(limit)
            )
            opportunities = kalshi + poly

        opportunities.sort(key=lambda o: o.score, reverse=True)
        top = opportunities[:limit]
        return ScanReport(
            scan_type=f"prediction:{platform}",
            universe_size=len(opportunities),
            scanned=len(opportunities),
            opportunities=top,
            summary=(
                f"{len(top)} contract opportunities on {platform}."
                if top
                else f"No qualifying {platform} contracts found "
                "(check credentials and market hours)."
            ),
        )

    async def _scan_kalshi(self, limit: int) -> list[TradeOpportunity]:
        if not self.kalshi:
            return []
        try:
            data = await self.kalshi.list_markets(limit=200, status="open")
        except Exception:
            return []

        opportunities = []
        for m in data.get("markets", []):
            yes_bid = m.get("yes_bid")
            yes_ask = m.get("yes_ask")
            volume = m.get("volume") or 0
            if not yes_bid or not yes_ask or volume < 100:
                continue

            spread = yes_ask - yes_bid
            mid = (yes_bid + yes_ask) / 2

            # High-probability carry: buy YES cheap relative to near-certain payout
            for side, cost in (("yes", yes_ask), ("no", 100 - yes_bid)):
                if not 1 <= cost <= 99:
                    continue
                payout_pct = (100 - cost) / cost * 100
                implied = cost  # cents == implied probability
                if implied < 85:
                    continue
                score = payout_pct - spread * 2 + min(15.0, volume / 5000)
                if score <= 0:
                    continue
                opportunities.append(
                    TradeOpportunity(
                        symbol=m.get("ticker", ""),
                        name=m.get("title", ""),
                        action=TradeAction.BUY,
                        score=round(score, 2),
                        confidence=round(min(0.9, implied / 100), 2),
                        price=cost / 100,
                        asset_type=AssetType.PREDICTION,
                        platform="kalshi",
                        setup=f"high-probability {side.upper()} carry",
                        reasons=[
                            f"Buy {side.upper()} at {cost:.0f}c for {payout_pct:.1f}% return if correct",
                            f"Implied probability {implied:.0f}%, spread {spread:.0f}c, volume {volume:,}",
                        ],
                        warnings=(
                            ["Wide spread — use limit orders"] if spread > 4 else []
                        ),
                        metadata={
                            "side": side,
                            "cost_cents": cost,
                            "close_time": m.get("close_time", ""),
                            "volume": volume,
                        },
                    )
                )

            if spread >= 6:
                opportunities.append(
                    TradeOpportunity(
                        symbol=m.get("ticker", ""),
                        name=m.get("title", ""),
                        action=TradeAction.BUY,
                        score=round(spread * 1.5 + min(10.0, volume / 5000), 2),
                        confidence=0.5,
                        price=mid / 100,
                        asset_type=AssetType.PREDICTION,
                        platform="kalshi",
                        setup="wide spread — provide liquidity",
                        reasons=[
                            f"{spread:.0f}c spread ({yes_bid:.0f}/{yes_ask:.0f}) with {volume:,} volume",
                            "Place a limit order inside the spread instead of paying the ask",
                        ],
                        metadata={"yes_bid": yes_bid, "yes_ask": yes_ask, "volume": volume},
                    )
                )

        return opportunities

    async def _scan_polymarket(self, limit: int) -> list[TradeOpportunity]:
        if not self.polymarket:
            return []
        try:
            markets = await self.polymarket.list_markets(
                limit=150, order="volume24hr", ascending=False
            )
        except Exception:
            return []

        opportunities = []
        for m in markets if isinstance(markets, list) else markets.get("data", []):
            try:
                prices = m.get("outcomePrices")
                if isinstance(prices, str):
                    import json

                    prices = json.loads(prices)
                if not prices:
                    continue
                best = max(float(p) for p in prices)
            except Exception:
                continue

            volume = _as_float(m.get("volume24hr")) or _as_float(m.get("volume")) or 0
            if volume < 5000 or not 0.85 <= best <= 0.99:
                continue

            payout_pct = (1 - best) / best * 100
            score = payout_pct + min(15.0, volume / 50_000)
            opportunities.append(
                TradeOpportunity(
                    symbol=m.get("conditionId", "") or m.get("slug", ""),
                    name=m.get("question", "")[:180],
                    action=TradeAction.BUY,
                    score=round(score, 2),
                    confidence=round(best, 2),
                    price=round(best, 4),
                    asset_type=AssetType.PREDICTION,
                    platform="polymarket",
                    setup="high-probability carry",
                    reasons=[
                        f"Favourite priced at {best:.0%} pays {payout_pct:.1f}% if it resolves as expected",
                        f"24h volume ${volume:,.0f}",
                    ],
                    metadata={
                        "slug": m.get("slug", ""),
                        "end_date": m.get("endDate", ""),
                        "volume24hr": volume,
                    },
                )
            )

        return opportunities

    # ── Internals ───────────────────────────────────────────────────────────

    async def _score_symbol(self, symbol: str, include_news: bool) -> TradeOpportunity:
        async with self._sem:
            research = await self.researcher.research_stock_fast(
                symbol, include_news=include_news
            )
            prediction = await self.predictor.predict(research)
        return _to_opportunity(symbol, research, prediction)

    async def _safe_clusters(self) -> list[dict[str, Any]]:
        try:
            return await self.researcher.insider.get_cluster_buys(days=14, min_insiders=2)
        except Exception:
            return []


def _to_opportunity(
    symbol: str, research: ResearchBundle, prediction: MarketPrediction
) -> TradeOpportunity:
    tech = research.technical_signals
    market = research.market
    price = prediction.current_price or (market.price if market else None)
    action = prediction.recommended_action

    upside = None
    if price and prediction.price_target_1w:
        upside = round((prediction.price_target_1w - price) / price * 100, 2)

    entry = prediction.sell_zone if action == TradeAction.SELL else prediction.buy_zone
    stop, target, rr = _risk_levels(price, action, prediction)

    reasons: list[str] = []
    score = 0.0

    # Conviction from the predictor is the backbone of the score
    directional = (prediction.confidence - 0.5) * 2
    if action == TradeAction.BUY:
        score += directional * 40
    elif action == TradeAction.SELL:
        score += directional * 35
    reasons.append(f"{prediction.direction.title()} forecast at {prediction.confidence:.0%} confidence")

    if upside is not None:
        score += max(-20.0, min(25.0, upside * 2 if action == TradeAction.BUY else -upside * 2))
        reasons.append(f"1-week target ${prediction.price_target_1w:.2f} ({upside:+.1f}%)")

    rsi = tech.get("rsi_14")
    setup = ""
    if rsi is not None:
        if rsi < 30 and action == TradeAction.BUY:
            score += 12
            setup = "oversold bounce"
            reasons.append(f"RSI {rsi:.0f} — oversold")
        elif rsi > 70 and action == TradeAction.SELL:
            score += 12
            setup = "overbought fade"
            reasons.append(f"RSI {rsi:.0f} — overbought")
        elif 45 <= rsi <= 60:
            score += 3

    trend = str(tech.get("trend", ""))
    if "strong_bullish" in trend and action == TradeAction.BUY:
        score += 10
        setup = setup or "momentum breakout"
        reasons.append("Price above rising 20/50-day averages")
    elif "strong_bearish" in trend and action == TradeAction.SELL:
        score += 10
        setup = setup or "downtrend continuation"

    if rr:
        score += min(12.0, rr * 4)
        reasons.append(f"Risk/reward {rr:.1f}:1")

    if market and market.volume and market.volume > 1_000_000:
        score += 4
    warnings: list[str] = []
    if market and market.volume is not None and market.volume < 200_000:
        warnings.append("Thin volume — slippage risk")
        score -= 8
    if market and market.change_pct is not None and abs(market.change_pct) > 8:
        warnings.append(f"Already moved {market.change_pct:+.1f}% today — chasing risk")
        score -= 5

    return TradeOpportunity(
        symbol=symbol,
        name=(market.extra.get("name", "") if market else ""),
        action=action,
        score=round(max(0.0, score), 2),
        confidence=prediction.confidence,
        price=price,
        change_pct=market.change_pct if market else None,
        price_target=prediction.price_target_1w,
        upside_pct=upside,
        entry_price=entry,
        stop_loss=stop,
        take_profit=target,
        risk_reward=rr,
        setup=setup or f"{prediction.direction} setup",
        reasons=reasons,
        warnings=warnings,
        metadata={
            "rsi_14": rsi,
            "trend": trend,
            "support": prediction.support,
            "resistance": prediction.resistance,
        },
    )


def _risk_levels(
    price: float | None, action: TradeAction, prediction: MarketPrediction
) -> tuple[float | None, float | None, float | None]:
    if not price:
        return None, None, None

    if action == TradeAction.SELL:
        stop = round((prediction.resistance or price * 1.05) * 1.01, 2)
        target = round(prediction.support or price * 0.94, 2)
        risk = stop - price
        reward = price - target
    else:
        stop = round((prediction.support or price * 0.94) * 0.99, 2)
        target = round(max(prediction.sell_zone or 0.0, price * 1.06), 2)
        risk = price - stop
        reward = target - price

    rr = round(reward / risk, 2) if risk and risk > 0 and reward > 0 else None
    return stop, target, rr


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _summarize(
    opportunities: list[TradeOpportunity],
    universe_size: int,
    scanned: int | None = None,
) -> str:
    if not opportunities:
        # Distinguish "nothing worth trading" from "we couldn't get any data",
        # which otherwise look identical to the user.
        if scanned == 0 and universe_size:
            return (
                f"Could not retrieve market data for any of {universe_size} symbols. "
                "The upstream price feed is rate limiting or unreachable — try again shortly."
            )
        if scanned is not None and scanned < universe_size:
            return (
                f"Scanned {scanned} of {universe_size} symbols "
                f"({universe_size - scanned} had no data available) — "
                "no setups met the criteria right now."
            )
        return f"Scanned {universe_size} symbols — no setups met the criteria right now."

    counts = {
        action: sum(1 for o in opportunities if o.action == action) for action in TradeAction
    }
    breakdown = ", ".join(
        f"{count} {action.value}" for action, count in counts.items() if count
    )
    noun = "opportunity" if len(opportunities) == 1 else "opportunities"
    best = opportunities[0]
    return (
        f"Scanned {universe_size} symbols → {len(opportunities)} {noun} ({breakdown}). "
        f"Best: {best.symbol} {best.action.value.upper()} "
        f"(score {best.score:.0f}, {best.confidence:.0%} confidence)"
    )
