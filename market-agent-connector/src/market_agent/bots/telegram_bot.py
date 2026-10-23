"""Telegram bot for Market Agent."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from market_agent.bots.service import BotService
from market_agent.config import load_settings

logger = logging.getLogger(__name__)


def _check_auth(service: BotService, update: Update) -> bool:
    user = update.effective_user
    if not user:
        return False
    return service.is_authorized(str(user.id))


async def _reply(update: Update, text: str, parse_mode: str = "Markdown") -> None:
    if update.message:
        # Telegram limit is 4096 chars
        for i in range(0, len(text), 4000):
            await update.message.reply_text(text[i : i + 4000], parse_mode=parse_mode)


def _arg(context: ContextTypes.DEFAULT_TYPE, index: int = 0, default: str = "") -> str:
    args = context.args or []
    return args[index] if len(args) > index else default


def _symbol_list(context: ContextTypes.DEFAULT_TYPE) -> list[str]:
    """Accept symbols separated by spaces, commas, or both."""
    raw = " ".join(context.args or []).replace(",", " ")
    return [s.upper() for s in raw.split() if s.strip()]


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, await service.cmd_help())


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, await service.cmd_status())


async def quote_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    symbol = _arg(context)
    if not symbol:
        await _reply(update, "Usage: /quote AAPL")
        return
    await _reply(update, await service.cmd_quote(symbol))


async def news_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    symbol = _arg(context)
    if not symbol:
        await _reply(update, "Usage: /news AAPL")
        return
    await _reply(update, await service.cmd_news(symbol))


async def research_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    symbol = _arg(context)
    if not symbol:
        await _reply(update, "Usage: /research AAPL")
        return
    await _reply(update, await service.cmd_research(symbol))


async def analyze_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    symbol = _arg(context)
    if not symbol:
        await _reply(update, "Usage: /analyze AAPL")
        return
    platform = _arg(context, 1, "paper")
    await _reply(update, await service.cmd_analyze(symbol, platform))


async def trade_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    symbol = _arg(context)
    if not symbol:
        await _reply(update, "Usage: /trade AAPL [platform]")
        return
    platform = _arg(context, 1, "paper")
    force = _arg(context, 2, "").lower() in ("force", "live", "true")
    await _reply(update, f"⏳ Analyzing and trading `{symbol}`...")
    await _reply(update, await service.cmd_trade(symbol, platform, force))


async def portfolio_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, await service.cmd_portfolio())


async def cycle_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    platform = _arg(context, 0, "paper")
    force = _arg(context, 1, "").lower() in ("force", "live")
    await _reply(update, "⏳ Running trading cycle...")
    await _reply(update, await service.cmd_cycle(platform, force))


async def growth_setup_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    capital_str = _arg(context)
    if not capital_str:
        await _reply(update, "Usage: /growth_setup 1000")
        return
    try:
        capital = float(capital_str.replace(",", "").replace("$", ""))
    except ValueError:
        await _reply(update, "Invalid amount. Usage: /growth_setup 1000")
        return
    await _reply(update, await service.cmd_growth_setup(capital))


async def growth_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, await service.cmd_growth_status())


async def growth_run_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    force = _arg(context, 0, "").lower() in ("force", "live", "true")
    await _reply(update, "⏳ Running live growth cycle on all platforms...")
    await _reply(update, await service.cmd_growth_run(force))


async def insider_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    symbol = _arg(context)
    if not symbol:
        await _reply(update, "Usage: /insider AAPL")
        return
    days = int(_arg(context, 1, "180") or "180")
    await _reply(update, f"⏳ Fetching insider trades for `{symbol}`...")
    await _reply(update, await service.cmd_insider(symbol, days))


async def predict_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    symbol = _arg(context)
    if not symbol:
        await _reply(update, "Usage: /predict AAPL")
        return
    await _reply(update, f"⏳ Predicting `{symbol}`...")
    await _reply(update, await service.cmd_predict(symbol))


async def signals_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, "⏳ Scanning watchlist...")
    await _reply(update, await service.cmd_signals())


async def best_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    limit = int(_arg(context, 0, "8") or "8")
    deep = _arg(context, 1, "").lower() in ("deep", "full", "news")
    await _reply(update, "⏳ Scanning the market for the best setups (this takes ~30s)...")
    await _reply(update, await service.cmd_best_trades(limit=limit, deep=deep))


async def scan_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    symbols = _symbol_list(context)
    await _reply(update, "⏳ Scoring symbols...")
    await _reply(update, await service.cmd_scan(symbols or None))


async def sector_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    sector = _arg(context)
    if not sector:
        await _reply(
            update,
            "Usage: /sector tech\nOptions: tech, ai, finance, healthcare, energy, consumer, crypto",
        )
        return
    await _reply(update, f"⏳ Scanning {sector} sector...")
    await _reply(update, await service.cmd_sector_scan(sector))


async def movers_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, await service.cmd_movers())


async def trending_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, await service.cmd_trending())


async def insider_buys_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    days = int(_arg(context, 0, "14") or "14")
    await _reply(update, "⏳ Searching SEC Form 4 filings for insider cluster buys...")
    await _reply(update, await service.cmd_insider_buys(days=days))


async def opportunities_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    platform = _arg(context, 0, "kalshi")
    await _reply(update, f"⏳ Scanning {platform} contracts...")
    await _reply(update, await service.cmd_opportunities(platform))


async def compare_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    symbols = _symbol_list(context)
    if len(symbols) < 2:
        await _reply(update, "Usage: /compare AAPL MSFT NVDA")
        return
    await _reply(update, await service.cmd_compare(symbols))


async def watchlist_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    args = context.args or []
    action = args[0] if args else "list"
    symbols = [s.upper() for a in args[1:] for s in a.split(",")]
    await _reply(update, await service.cmd_watchlist(action, symbols))


async def auto_start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    platform = _arg(context, 0, "paper")
    interval = int(_arg(context, 1, "15") or "15")
    force = _arg(context, 2, "").lower() in ("force", "live")

    async def notify(msg: str) -> None:
        if update.message:
            await update.message.reply_text(msg, parse_mode="Markdown")

    await _reply(update, await service.cmd_auto_start(platform, interval, force, notify))


async def auto_stop_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, await service.cmd_auto_stop())


async def auto_status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, await service.cmd_auto_status())


async def platforms_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    service: BotService = context.bot_data["service"]
    if not _check_auth(service, update):
        await _reply(update, service.auth_denied_message())
        return
    await _reply(update, await service.cmd_platforms())


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    uid = user.id if user else "?"
    await _reply(
        update,
        f"👋 Welcome to *Market Agent Bot*!\nYour user ID: `{uid}`\n\n"
        f"Type /help for all commands.",
    )


def build_telegram_app(token: str, service: BotService) -> Application:
    app = Application.builder().token(token).build()
    app.bot_data["service"] = service

    handlers = [
        ("start", start_cmd),
        ("help", help_cmd),
        ("status", status_cmd),
        ("best", best_cmd),
        ("scan", scan_cmd),
        ("sector", sector_cmd),
        ("movers", movers_cmd),
        ("trending", trending_cmd),
        ("insider_buys", insider_buys_cmd),
        ("opportunities", opportunities_cmd),
        ("compare", compare_cmd),
        ("watchlist", watchlist_cmd),
        ("quote", quote_cmd),
        ("news", news_cmd),
        ("research", research_cmd),
        ("insider", insider_cmd),
        ("predict", predict_cmd),
        ("analyze", analyze_cmd),
        ("signals", signals_cmd),
        ("trade", trade_cmd),
        ("auto_start", auto_start_cmd),
        ("auto_stop", auto_stop_cmd),
        ("auto_status", auto_status_cmd),
        ("portfolio", portfolio_cmd),
        ("cycle", cycle_cmd),
        ("growth_setup", growth_setup_cmd),
        ("growth", growth_cmd),
        ("growth_run", growth_run_cmd),
        ("platforms", platforms_cmd),
    ]
    for name, handler in handlers:
        app.add_handler(CommandHandler(name, handler))

    return app


async def run_telegram() -> None:
    settings = load_settings()
    token = settings.bot.telegram_token
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN not set in .env")

    service = BotService(settings)
    app = build_telegram_app(token, service)
    logger.info("Telegram bot starting...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(drop_pending_updates=True)
    logger.info("Telegram bot is running. Press Ctrl+C to stop.")

    import asyncio
    try:
        await asyncio.Event().wait()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()
        await service.close()
