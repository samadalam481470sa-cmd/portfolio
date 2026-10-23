"""Manual smoke test for the opportunity scanner against live data sources.

Run with: python3 scripts/smoke_scan.py
Requires network access; nothing is traded and no credentials are needed.
"""

from __future__ import annotations

import asyncio

from market_agent.ai.opportunity_scanner import OpportunityScanner
from market_agent.intelligence.researcher import IntelligenceResearcher


async def main() -> None:
    researcher = IntelligenceResearcher()
    scanner = OpportunityScanner(researcher=researcher)

    try:
        print("── trending ──────────────────────────────────────────")
        trending = await scanner.screener.trending(10)
        print(trending)

        print("\n── gainers ───────────────────────────────────────────")
        for q in await scanner.screener.top_gainers(5):
            print(f"  {q.symbol:<8} ${q.price or 0:<10.2f} {q.change_pct}%")

        print("\n── losers ────────────────────────────────────────────")
        for q in await scanner.screener.top_losers(5):
            print(f"  {q.symbol:<8} ${q.price or 0:<10.2f} {q.change_pct}%")

        print("\n── scan_stocks(AAPL, MSFT, NVDA, TSLA, AMD) ──────────")
        report = await scanner.scan_stocks(
            symbols=["AAPL", "MSFT", "NVDA", "TSLA", "AMD"], action="all", limit=10
        )
        print(f"  {report.summary}")
        for o in report.opportunities:
            print(
                f"  {o.symbol:<6} {o.action.value.upper():<5} score={o.score:<7.1f} "
                f"${o.price or 0:<9.2f} entry={o.entry_price} stop={o.stop_loss} "
                f"target={o.take_profit} rr={o.risk_reward} setup={o.setup}"
            )

        print("\n── insider cluster buys (14d) ────────────────────────")
        insider = await scanner.scan_insider_buys(days=14, min_insiders=2, limit=5)
        print(f"  {insider.summary}")
        for o in insider.opportunities:
            print(f"  {o.symbol:<6} score={o.score:<7.1f} {o.catalysts[0] if o.catalysts else ''}")

        print("\n── best trades ───────────────────────────────────────")
        best = await scanner.find_best_trades(limit=5)
        print(f"  {best.summary}")
        for o in best.opportunities:
            print(
                f"  {o.symbol:<6} {o.action.value.upper():<5} score={o.score:<7.1f} "
                f"{o.setup} | {'; '.join(o.catalysts[:2])}"
            )
    finally:
        await scanner.close()
        await researcher.close()


if __name__ == "__main__":
    asyncio.run(main())
