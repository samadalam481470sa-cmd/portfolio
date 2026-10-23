"""Run Telegram and/or Discord bots."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from market_agent.config import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def run_both() -> None:
    settings = load_settings()
    has_telegram = bool(settings.bot.telegram_token)
    has_discord = bool(settings.bot.discord_token)

    if not has_telegram and not has_discord:
        print("Error: Set TELEGRAM_BOT_TOKEN and/or DISCORD_BOT_TOKEN in .env")
        sys.exit(1)

    tasks = []
    if has_telegram:
        from market_agent.bots.telegram_bot import run_telegram
        tasks.append(asyncio.create_task(run_telegram()))
        logger.info("Telegram bot enabled")
    if has_discord:
        from market_agent.bots.discord_bot import run_discord
        tasks.append(asyncio.create_task(run_discord()))
        logger.info("Discord bot enabled")

    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Market Agent Telegram/Discord bot")
    parser.add_argument(
        "--platform",
        choices=["telegram", "discord", "both"],
        default="both",
        help="Which bot platform to run",
    )
    args = parser.parse_args()

    if args.platform == "telegram":
        from market_agent.bots.telegram_bot import run_telegram
        asyncio.run(run_telegram())
    elif args.platform == "discord":
        from market_agent.bots.discord_bot import run_discord
        asyncio.run(run_discord())
    else:
        asyncio.run(run_both())


if __name__ == "__main__":
    main()
