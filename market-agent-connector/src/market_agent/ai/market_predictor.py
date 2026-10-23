"""Market prediction engine — price targets, trend forecast, buy/sell timing."""

from __future__ import annotations

from typing import Any

from market_agent.ai.models import MarketPrediction, MarketSnapshot, ResearchBundle, TradeAction


class MarketPredictor:
    """Predicts short-term price direction and optimal buy/sell timing."""

    async def predict(self, research: ResearchBundle) -> MarketPrediction:
        tech = research.technical_signals
        market = research.market
        closes = tech.get("_closes", [])  # injected by researcher if available

        current = (
            market.price
            if market and market.price
            else tech.get("current_price", 0)
        )
        if not current:
            return MarketPrediction(
                symbol=research.symbol,
                current_price=0,
                direction="neutral",
                confidence=0.0,
                summary="Insufficient price data",
            )

        # Compute components
        momentum = self._momentum_score(tech, market)
        trend_forecast = self._trend_direction(tech)
        price_target = self._price_target(current, tech, momentum)
        support, resistance = self._support_resistance(current, tech, market)
        buy_zone, sell_zone = self._buy_sell_zones(current, support, resistance, tech)
        timing = self._entry_exit_timing(tech, momentum, research)
        sentiment = self._news_sentiment_score(research)
        insider = self._insider_sentiment_score(research)

        # Combined direction score (-1 to +1)
        score = (
            momentum * 0.25
            + trend_forecast * 0.20
            + sentiment * 0.15
            + insider * 0.20
            + timing * 0.20
        )

        if score >= 0.25:
            direction = "bullish"
            action = TradeAction.BUY
        elif score <= -0.25:
            direction = "bearish"
            action = TradeAction.SELL
        else:
            direction = "neutral"
            action = TradeAction.HOLD

        confidence = min(0.85, 0.50 + abs(score) * 0.5)
        upside = ((price_target - current) / current * 100) if price_target else 0

        summary_parts = [
            f"Direction: {direction.upper()} ({confidence:.0%} confidence)",
            f"Current: ${current:.2f} → Target: ${price_target:.2f} ({upside:+.1f}%)",
            f"Buy zone: ${buy_zone:.2f} | Sell zone: ${sell_zone:.2f}",
            f"Support: ${support:.2f} | Resistance: ${resistance:.2f}",
        ]

        return MarketPrediction(
            symbol=research.symbol,
            current_price=current,
            price_target_1d=price_target,
            price_target_1w=round(current * (1 + score * 0.05), 2),
            direction=direction,
            confidence=round(confidence, 2),
            recommended_action=action,
            buy_zone=buy_zone,
            sell_zone=sell_zone,
            support=support,
            resistance=resistance,
            momentum_score=round(momentum, 2),
            sentiment_score=round(sentiment, 2),
            summary="\n".join(summary_parts),
            factors=self._build_factors(tech, market, research, momentum, sentiment, insider),
        )

    def _momentum_score(self, tech: dict, market: MarketSnapshot | None) -> float:
        score = 0.0
        rsi = tech.get("rsi_14")
        if rsi is not None:
            if rsi < 30:
                score += 0.6
            elif rsi < 40:
                score += 0.3
            elif rsi > 70:
                score -= 0.6
            elif rsi > 60:
                score -= 0.3

        trend = tech.get("trend", "")
        if "strong_bullish" in trend:
            score += 0.5
        elif "bullish" in trend:
            score += 0.25
        elif "strong_bearish" in trend:
            score -= 0.5
        elif "bearish" in trend:
            score -= 0.25

        if market and market.change_pct is not None:
            if market.change_pct > 2:
                score += 0.15
            elif market.change_pct < -2:
                score -= 0.15

        return max(-1.0, min(1.0, score))

    def _trend_direction(self, tech: dict) -> float:
        sma20 = tech.get("sma_20")
        sma50 = tech.get("sma_50")
        current = tech.get("current_price")
        if not all([sma20, current]):
            return 0.0
        if sma50:
            if current > sma20 > sma50:
                return 0.7
            if current < sma20 < sma50:
                return -0.7
        return 0.3 if current > sma20 else -0.3

    def _price_target(self, current: float, tech: dict, momentum: float) -> float:
        sma20 = tech.get("sma_20", current)
        # Blend SMA mean-reversion with momentum extrapolation
        mean_revert = (sma20 - current) * 0.3
        momentum_move = current * momentum * 0.02
        target = current + mean_revert + momentum_move
        return round(max(target, current * 0.85), 2)

    def _support_resistance(
        self, current: float, tech: dict, market: MarketSnapshot | None
    ) -> tuple[float, float]:
        low = tech.get("fifty_two_week_low") or (market.fifty_two_week_low if market else None)
        high = tech.get("fifty_two_week_high") or (market.fifty_two_week_high if market else None)
        sma20 = tech.get("sma_20") or current

        # Use the NEAREST level on each side. The 52-week extremes are often far
        # from spot, and anchoring entries there produces orders that never fill.
        below = [c for c in (sma20 * 0.97, low, current * 0.95) if c and c < current]
        above = [c for c in (sma20 * 1.03, high, current * 1.05) if c and c > current]

        support = max(below) if below else current * 0.95
        resistance = min(above) if above else current * 1.05
        return round(support, 2), round(resistance, 2)

    def _buy_sell_zones(
        self, current: float, support: float, resistance: float, tech: dict
    ) -> tuple[float, float]:
        rsi = tech.get("rsi_14", 50)
        if rsi and rsi < 35:
            buy_zone = current * 0.99
        else:
            buy_zone = support * 1.01

        if rsi and rsi > 65:
            sell_zone = current * 1.01
        else:
            sell_zone = resistance * 0.99

        return round(buy_zone, 2), round(sell_zone, 2)

    def _entry_exit_timing(
        self, tech: dict, momentum: float, research: ResearchBundle
    ) -> float:
        rsi = tech.get("rsi_14")
        if rsi is None:
            return momentum * 0.5

        # Golden cross timing
        sma20 = tech.get("sma_20")
        sma50 = tech.get("sma_50")
        current = tech.get("current_price")
        if sma20 and sma50 and current:
            if current > sma20 and sma20 > sma50:
                return 0.5
            if current < sma20 and sma20 < sma50:
                return -0.5

        if rsi < 30:
            return 0.7  # strong buy timing
        if rsi > 70:
            return -0.7  # strong sell timing
        return momentum * 0.3

    def _news_sentiment_score(self, research: ResearchBundle) -> float:
        if not research.news:
            return 0.0
        pos_words = ("beat", "surge", "rally", "upgrade", "bullish", "growth", "record", "profit")
        neg_words = ("miss", "drop", "fall", "downgrade", "bearish", "loss", "weak", "warning", "cut")
        score = 0.0
        for item in research.news[:10]:
            text = f"{item.title} {item.summary}".lower()
            score += sum(0.1 for w in pos_words if w in text)
            score -= sum(0.1 for w in neg_words if w in text)
        return max(-1.0, min(1.0, score))

    def _insider_sentiment_score(self, research: ResearchBundle) -> float:
        summary = research.insider_summary
        if not summary:
            return 0.0
        if summary.net_sentiment == "bullish":
            return 0.5
        if summary.net_sentiment == "bearish":
            return -0.5
        return 0.0

    def _build_factors(
        self,
        tech: dict,
        market: MarketSnapshot | None,
        research: ResearchBundle,
        momentum: float,
        sentiment: float,
        insider: float = 0.0,
    ) -> list[str]:
        factors = []
        if tech.get("rsi_14"):
            factors.append(f"RSI: {tech['rsi_14']} ({'oversold' if tech['rsi_14'] < 30 else 'overbought' if tech['rsi_14'] > 70 else 'neutral'})")
        if tech.get("trend"):
            factors.append(f"Trend: {tech['trend']}")
        if market and market.change_pct is not None:
            factors.append(f"Today: {market.change_pct:+.2f}%")
        if sentiment > 0.2:
            factors.append(f"News sentiment: bullish ({len(research.news)} articles)")
        elif sentiment < -0.2:
            factors.append("News sentiment: bearish")
        if research.insider_summary:
            s = research.insider_summary
            factors.append(
                f"Insider trades ({s.period_days}d): {s.purchases} buys / {s.sales} sells "
                f"→ {s.net_sentiment}"
            )
        elif insider > 0.2:
            factors.append("Insider activity: net buying")
        elif insider < -0.2:
            factors.append("Insider activity: net selling")
        factors.append(f"Momentum score: {momentum:+.2f}")
        return factors
