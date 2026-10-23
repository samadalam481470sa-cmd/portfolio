"""AI-powered trading decision engine with LLM and rule-based fallback."""

from __future__ import annotations

import re
from typing import Any

from market_agent.ai.llm_client import LLMClient
from market_agent.ai.models import AssetType, ResearchBundle, TradeAction, TradeSignal

SYSTEM_PROMPT = """You are an expert quantitative trading analyst. Analyze the provided market data,
news, technical indicators, and web research to produce a trading recommendation.

Respond ONLY with valid JSON in this exact schema:
{
  "action": "buy" | "sell" | "hold",
  "confidence": 0.0 to 1.0,
  "quantity": integer (suggested shares, 0 for hold),
  "limit_price": number or null,
  "reasoning": "detailed explanation citing specific news and technicals",
  "risk_factors": ["list of risks"],
  "news_catalysts": ["key news driving the decision"]
}

Rules:
- Only recommend BUY/SELL when you have strong conviction (confidence >= 0.65)
- Cite specific news headlines and technical signals in reasoning
- Consider RSI overbought (>70) / oversold (<30), trend, and recent news sentiment
- Default to HOLD when uncertain
- Be conservative — capital preservation matters"""


class DecisionEngine:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm

    async def analyze(self, research: ResearchBundle, platform: str = "paper") -> TradeSignal:
        if self.llm and self.llm.is_configured:
            return await self._llm_analyze(research, platform)
        return self._rules_analyze(research, platform)

    async def _llm_analyze(self, research: ResearchBundle, platform: str) -> TradeSignal:
        assert self.llm is not None
        context = _build_context(research)
        result = await self.llm.analyze_json(SYSTEM_PROMPT, context)

        action_str = result.get("action", "hold").lower()
        try:
            action = TradeAction(action_str)
        except ValueError:
            action = TradeAction.HOLD

        return TradeSignal(
            symbol=research.symbol,
            action=action,
            confidence=float(result.get("confidence", 0.5)),
            quantity=int(result.get("quantity", 0)),
            limit_price=result.get("limit_price"),
            reasoning=result.get("reasoning", ""),
            risk_factors=result.get("risk_factors", []),
            news_catalysts=result.get("news_catalysts", []),
            asset_type=research.asset_type,
            platform=platform,
        )

    def _rules_analyze(self, research: ResearchBundle, platform: str) -> TradeSignal:
        """Rule-based fallback when no LLM API key is configured."""
        score = 0.0
        reasons: list[str] = []
        risks: list[str] = []
        catalysts: list[str] = []

        tech = research.technical_signals
        market = research.market

        # Technical scoring
        rsi = tech.get("rsi_14")
        trend = tech.get("trend", "")
        if rsi is not None:
            if rsi < 30:
                score += 0.3
                reasons.append(f"RSI {rsi} indicates oversold conditions")
            elif rsi > 70:
                score -= 0.3
                reasons.append(f"RSI {rsi} indicates overbought conditions")
                risks.append("Overbought RSI — potential pullback")

        if "bullish" in trend:
            score += 0.2
            reasons.append(f"Technical trend is {trend}")
        elif "bearish" in trend:
            score -= 0.2
            reasons.append(f"Technical trend is {trend}")

        if market and market.change_pct is not None:
            if market.change_pct > 3:
                score -= 0.1
                risks.append(f"Already up {market.change_pct}% today — chasing risk")
            elif market.change_pct < -3:
                score += 0.1
                reasons.append(f"Down {market.change_pct}% today — potential dip buy")

        # News sentiment (keyword-based)
        news_score, news_reasons, news_catalysts = _score_news(research)
        score += news_score
        reasons.extend(news_reasons)
        catalysts.extend(news_catalysts)

        # Insider trading sentiment (OpenInsider / SEC Form 4)
        insider_score, insider_reasons = _score_insider(research)
        score += insider_score
        reasons.extend(insider_reasons)
        if insider_score < -0.15:
            risks.append("Heavy insider selling in recent months")
        elif insider_score > 0.15:
            catalysts.append("Recent insider buying activity")

        # Determine action
        if score >= 0.35:
            action = TradeAction.BUY
            confidence = min(0.55 + score, 0.85)
        elif score <= -0.35:
            action = TradeAction.SELL
            confidence = min(0.55 + abs(score), 0.85)
        else:
            action = TradeAction.HOLD
            confidence = 0.5

        price = market.price if market else tech.get("current_price")
        quantity = 0
        if action != TradeAction.HOLD and price:
            quantity = max(1, int(200 / price))  # ~$200 default position in rules mode

        return TradeSignal(
            symbol=research.symbol,
            action=action,
            confidence=round(confidence, 2),
            quantity=quantity,
            limit_price=price,
            reasoning=" | ".join(reasons) if reasons else "Insufficient signals — holding",
            risk_factors=risks,
            news_catalysts=catalysts,
            asset_type=research.asset_type,
            platform=platform,
            metadata={"engine": "rules", "score": round(score, 2)},
        )


def _build_context(research: ResearchBundle) -> str:
    parts = [f"Symbol: {research.symbol}", f"Asset type: {research.asset_type.value}"]

    if research.market:
        m = research.market
        parts.append(
            f"\nMarket: price=${m.price}, change={m.change_pct}%, "
            f"volume={m.volume}, sector={m.sector}, PE={m.pe_ratio}"
        )

    if research.technical_signals:
        parts.append(f"\nTechnicals: {research.technical_signals}")

    if research.news:
        parts.append("\nRecent News:")
        for n in research.news[:10]:
            parts.append(f"  - [{n.source}] {n.title}")

    if research.web_snippets:
        parts.append("\nWeb Research:")
        for s in research.web_snippets[:5]:
            parts.append(f"  - {s[:200]}")

    if research.insider_summary:
        s = research.insider_summary
        parts.append(
            f"\nInsider Trades ({s.period_days}d): {s.purchases} buys (${s.buy_value_usd:,.0f}), "
            f"{s.sales} sells (${s.sell_value_usd:,.0f}), sentiment={s.net_sentiment}"
        )
    if research.insider_trades:
        parts.append("\nRecent Insider Transactions:")
        for t in research.insider_trades[:8]:
            parts.append(
                f"  - {t.trade_date} {t.insider_name} ({t.title}): {t.trade_type} "
                f"{t.quantity:,} @ ${t.price or 0:.2f} = ${t.value or 0:,.0f}"
            )

    return "\n".join(parts)


_POSITIVE = re.compile(
    r"\b(beat|surge|rally|growth|upgrade|bullish|record|profit|gain|strong|outperform|buy)\b",
    re.I,
)
_NEGATIVE = re.compile(
    r"\b(miss|drop|fall|decline|downgrade|bearish|loss|weak|lawsuit|recall|cut|sell|warning)\b",
    re.I,
)


def _score_news(research: ResearchBundle) -> tuple[float, list[str], list[str]]:
    score = 0.0
    reasons: list[str] = []
    catalysts: list[str] = []

    for item in research.news[:8]:
        text = f"{item.title} {item.summary}"
        pos = len(_POSITIVE.findall(text))
        neg = len(_NEGATIVE.findall(text))
        if pos > neg:
            score += 0.05
            catalysts.append(item.title[:100])
        elif neg > pos:
            score -= 0.05
            reasons.append(f"Negative news: {item.title[:80]}")

    if catalysts:
        reasons.append(f"Positive news catalysts: {len(catalysts)} articles")
    return score, reasons, catalysts


def _score_insider(research: ResearchBundle) -> tuple[float, list[str]]:
    """Score based on insider buy/sell activity from OpenInsider."""
    reasons: list[str] = []
    summary = research.insider_summary
    if summary:
        if summary.net_sentiment == "bullish":
            reasons.append(
                f"Insider buying: ${summary.buy_value_usd:,.0f} bought vs "
                f"${summary.sell_value_usd:,.0f} sold ({summary.period_days}d)"
            )
            return 0.20, reasons
        if summary.net_sentiment == "bearish":
            reasons.append(
                f"Insider selling: ${summary.sell_value_usd:,.0f} sold vs "
                f"${summary.buy_value_usd:,.0f} bought ({summary.period_days}d)"
            )
            return -0.20, reasons
        return 0.0, reasons

    # Fallback: count recent purchases vs sales
    purchases = sum(1 for t in research.insider_trades if t.is_purchase)
    sales = sum(1 for t in research.insider_trades if t.is_sale)
    if purchases > sales + 2:
        reasons.append(f"Insider activity: {purchases} purchases vs {sales} sales")
        return 0.15, reasons
    if sales > purchases + 2:
        reasons.append(f"Insider activity: {sales} sales vs {purchases} purchases")
        return -0.15, reasons
    return 0.0, reasons
