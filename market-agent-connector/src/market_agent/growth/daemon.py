"""Continuous growth trading daemon."""

from __future__ import annotations

import asyncio
import signal
import sys

from market_agent.config import load_settings
from market_agent.growth.growth_trader import GrowthTrader


async def run_daemon(cycles: int = 0) -> None:
    settings = load_settings()
    growth = GrowthTrader(settings)
    interval = settings.growth.cycle_interval_min * 60
    count = 0

    print("=" * 60)
    print("  MARKET AGENT — LIVE GROWTH TRADER")
    print("=" * 60)
    print("  DISCLAIMER: You trade with YOUR money. Losses are possible.")
    print("  2x/3x targets are goals, NOT guarantees.")
    print("=" * 60)

    setup = await growth.setup()
    print(f"\nInitialized: ${setup['growth_status']['starting_capital']:.2f}")
    print(f"Targets: {setup['growth_status']['targets']}")
    print(f"Live ready: {setup['live_ready']}\n")

    stop = False

    def handle_stop(*_):
        nonlocal stop
        stop = True
        print("\nStopping after current cycle...")

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    try:
        while not stop:
            count += 1
            print(f"\n--- Cycle {count} ---")
            result = await growth.run_live_cycle()
            if result.get("halted"):
                print(f"HALTED: {result['reason']}")
                break
            print(result.get("summary", result))
            if cycles > 0 and count >= cycles:
                break
            if not stop:
                print(f"Next cycle in {settings.growth.cycle_interval_min} min...")
                await asyncio.sleep(interval)
    finally:
        final = await growth.status()
        g = final["growth"]
        print(f"\nFinal: ${g['current_value']:.2f} ({g['multiplier']:.2f}x, {g['total_pnl_pct']:+.1f}%)")
        print(f"Milestones hit: {g['milestones_hit']}")
        await growth.close()


def main() -> None:
    cycles = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    asyncio.run(run_daemon(cycles))
