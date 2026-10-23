"""Discord bot for Market Agent."""

from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from market_agent.bots.service import BotService
from market_agent.config import load_settings

logger = logging.getLogger(__name__)


class MarketAgentBot(commands.Bot):
    def __init__(self, service: BotService, **kwargs):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, **kwargs)
        self.service = service

    def _authorized(self, user: discord.User | discord.Member) -> bool:
        return self.service.is_authorized(str(user.id))

    async def setup_hook(self) -> None:
        await self.tree.sync()
        logger.info("Discord slash commands synced")

    async def on_ready(self) -> None:
        logger.info("Discord bot logged in as %s", self.user)


async def _send_long(interaction: discord.Interaction, text: str) -> None:
    """Discord caps messages at 2000 chars — split on line boundaries."""
    chunks: list[str] = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > 1900:
            chunks.append(current)
            current = line
        else:
            current = f"{current}\n{line}" if current else line
    if current:
        chunks.append(current)

    for chunk in chunks or ["_(no output)_"]:
        await interaction.followup.send(chunk)


def create_discord_bot(service: BotService) -> MarketAgentBot:
    bot = MarketAgentBot(service)

    @bot.tree.command(name="help", description="Show all commands")
    async def help_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.send_message(await bot.service.cmd_help())

    @bot.tree.command(name="status", description="System health check")
    async def status_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_status())

    @bot.tree.command(name="quote", description="Get live stock quote")
    @app_commands.describe(symbol="Stock ticker e.g. AAPL")
    async def quote_command(interaction: discord.Interaction, symbol: str):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_quote(symbol))

    @bot.tree.command(name="news", description="Get stock news")
    @app_commands.describe(symbol="Stock ticker e.g. AAPL")
    async def news_command(interaction: discord.Interaction, symbol: str):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_news(symbol))

    @bot.tree.command(name="research", description="Full intelligence report")
    @app_commands.describe(symbol="Stock ticker e.g. AAPL")
    async def research_command(interaction: discord.Interaction, symbol: str):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_research(symbol))

    @bot.tree.command(name="analyze", description="AI buy/sell/hold analysis")
    @app_commands.describe(symbol="Stock ticker", platform="paper, robinhood, kalshi")
    async def analyze_command(interaction: discord.Interaction, symbol: str, platform: str = "paper"):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_analyze(symbol, platform))

    @bot.tree.command(name="trade", description="Analyze and execute a trade")
    @app_commands.describe(
        symbol="Stock ticker",
        platform="paper, robinhood, kalshi, polymarket",
        force="Set true for live execution",
    )
    async def trade_command(
        interaction: discord.Interaction, symbol: str, platform: str = "paper", force: bool = False
    ):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_trade(symbol, platform, force))

    @bot.tree.command(name="portfolio", description="View paper trading portfolio")
    async def portfolio_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_portfolio())

    @bot.tree.command(name="cycle", description="Run AI trading cycle on watchlist")
    @app_commands.describe(platform="paper, robinhood, kalshi", force="Force live execution")
    async def cycle_command(interaction: discord.Interaction, platform: str = "paper", force: bool = False):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_cycle(platform, force))

    @bot.tree.command(name="growth_setup", description="Initialize growth trading targets")
    @app_commands.describe(capital="Starting capital in USD")
    async def growth_setup_command(interaction: discord.Interaction, capital: float):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_growth_setup(capital))

    @bot.tree.command(name="growth", description="Growth progress toward 2x/3x targets")
    async def growth_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_growth_status())

    @bot.tree.command(name="growth_run", description="Run live multi-platform growth cycle")
    @app_commands.describe(force="Force live execution")
    async def growth_run_command(interaction: discord.Interaction, force: bool = False):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_growth_run(force))

    @bot.tree.command(name="insider", description="SEC insider trade history from OpenInsider.com")
    @app_commands.describe(symbol="Stock ticker e.g. AAPL", days="Lookback days (default 180)")
    async def insider_command(interaction: discord.Interaction, symbol: str, days: int = 180):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_insider(symbol, days))

    @bot.tree.command(name="predict", description="Market prediction with price targets and buy/sell zones")
    @app_commands.describe(symbol="Stock ticker e.g. AAPL")
    async def predict_command(interaction: discord.Interaction, symbol: str):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_predict(symbol))

    @bot.tree.command(name="signals", description="Buy/sell signals for entire watchlist")
    async def signals_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_signals())

    @bot.tree.command(name="best", description="Scan the market and rank the best trades to make now")
    @app_commands.describe(limit="How many setups to return", deep="Include news analysis (slower)")
    async def best_command(interaction: discord.Interaction, limit: int = 8, deep: bool = False):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await _send_long(interaction, await bot.service.cmd_best_trades(limit=limit, deep=deep))

    @bot.tree.command(name="scan", description="Score and rank specific symbols")
    @app_commands.describe(symbols="Comma or space separated tickers, blank for watchlist")
    async def scan_command(interaction: discord.Interaction, symbols: str = ""):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        parsed = [s.upper() for s in symbols.replace(",", " ").split() if s.strip()]
        await _send_long(interaction, await bot.service.cmd_scan(parsed or None))

    @bot.tree.command(name="sector", description="Best setups within a sector")
    @app_commands.describe(sector="tech, ai, finance, healthcare, energy, consumer, crypto")
    async def sector_command(interaction: discord.Interaction, sector: str):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await _send_long(interaction, await bot.service.cmd_sector_scan(sector))

    @bot.tree.command(name="movers", description="Biggest gainers and losers today")
    async def movers_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await _send_long(interaction, await bot.service.cmd_movers())

    @bot.tree.command(name="trending", description="Tickers the market is watching right now")
    async def trending_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await _send_long(interaction, await bot.service.cmd_trending())

    @bot.tree.command(name="insider_buys", description="Stocks where multiple insiders are buying")
    @app_commands.describe(days="Lookback window", min_insiders="Minimum distinct insider buyers")
    async def insider_buys_command(
        interaction: discord.Interaction, days: int = 14, min_insiders: int = 2
    ):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await _send_long(
            interaction, await bot.service.cmd_insider_buys(days=days, min_insiders=min_insiders)
        )

    @bot.tree.command(name="opportunities", description="Best prediction-market contracts")
    @app_commands.describe(platform="kalshi, polymarket, or both")
    async def opportunities_command(interaction: discord.Interaction, platform: str = "kalshi"):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await _send_long(interaction, await bot.service.cmd_opportunities(platform))

    @bot.tree.command(name="compare", description="Rank several symbols head-to-head")
    @app_commands.describe(symbols="Comma or space separated tickers e.g. AAPL MSFT NVDA")
    async def compare_command(interaction: discord.Interaction, symbols: str):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        parsed = [s.upper() for s in symbols.replace(",", " ").split() if s.strip()]
        await _send_long(interaction, await bot.service.cmd_compare(parsed))

    @bot.tree.command(name="watchlist", description="View or edit the trading watchlist")
    @app_commands.describe(action="list, add, remove, clear", symbols="Tickers to add or remove")
    async def watchlist_command(
        interaction: discord.Interaction, action: str = "list", symbols: str = ""
    ):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        parsed = [s.upper() for s in symbols.replace(",", " ").split() if s.strip()]
        await interaction.followup.send(await bot.service.cmd_watchlist(action, parsed))

    @bot.tree.command(name="auto_start", description="Start automatic buy/sell on watchlist")
    @app_commands.describe(platform="paper, robinhood, kalshi", interval_min="Minutes between scans")
    async def auto_start_command(interaction: discord.Interaction, platform: str = "paper", interval_min: int = 15):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        channel = interaction.channel

        async def notify(msg: str) -> None:
            if channel:
                await channel.send(msg)

        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_auto_start(platform, interval_min, False, notify))

    @bot.tree.command(name="auto_stop", description="Stop automatic trading")
    async def auto_stop_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.send_message(await bot.service.cmd_auto_stop())

    @bot.tree.command(name="auto_status", description="Auto-trader status and recent trades")
    async def auto_status_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_auto_status())

    @bot.tree.command(name="platforms", description="Check broker connection status")
    async def platforms_command(interaction: discord.Interaction):
        if not bot._authorized(interaction.user):
            await interaction.response.send_message(bot.service.auth_denied_message(), ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.followup.send(await bot.service.cmd_platforms())

    @bot.event
    async def on_message(message: discord.Message):
        if message.author.bot:
            return
        if bot.user and message.content.strip() == f"<@{bot.user.id}>":
            uid = message.author.id
            await message.reply(
                f"👋 Market Agent Bot ready!\nYour user ID: `{uid}`\nUse `/help` for commands."
            )

    return bot


async def run_discord() -> None:
    settings = load_settings()
    token = settings.bot.discord_token
    if not token:
        raise ValueError("DISCORD_BOT_TOKEN not set in .env")

    service = BotService(settings)
    bot = create_discord_bot(service)
    logger.info("Discord bot starting...")
    try:
        await bot.start(token)
    finally:
        await service.close()
