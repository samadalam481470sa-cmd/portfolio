"""Configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class PolymarketSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="POLYMARKET_", extra="ignore")

    clob_api_key: str = ""
    clob_secret: str = ""
    clob_passphrase: str = ""
    wallet_address: str = ""
    use_demo: bool = False

    @property
    def is_authenticated(self) -> bool:
        return bool(
            self.clob_api_key
            and self.clob_secret
            and self.clob_passphrase
            and self.wallet_address
        )


class KalshiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="KALSHI_", extra="ignore")

    api_key_id: str = ""
    private_key_path: str = ""
    private_key_pem: str = ""
    use_demo: bool = True

    @property
    def base_url(self) -> str:
        if self.use_demo:
            return "https://external-api.demo.kalshi.co"
        return "https://external-api.kalshi.com"

    @property
    def is_authenticated(self) -> bool:
        return bool(self.api_key_id and (self.private_key_path or self.private_key_pem))


class RobinhoodSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ROBINHOOD_", extra="ignore")

    client_id: str = ""
    client_secret: str = ""
    redirect_uri: str = "http://localhost:8080/callback"
    access_token: str = ""
    refresh_token: str = ""
    use_sandbox: bool = True

    @property
    def base_url(self) -> str:
        if self.use_sandbox:
            return "https://sandbox.robinhood.com"
        return "https://api.robinhood.com"

    @property
    def is_authenticated(self) -> bool:
        return bool(self.access_token)


class AISettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AI_", extra="ignore")

    api_key: str = ""
    model: str = "gpt-4o-mini"
    base_url: str = "https://api.openai.com/v1"
    finnhub_api_key: str = ""

    # Risk controls
    dry_run: bool = True
    require_confirmation: bool = True
    min_confidence: float = 0.65
    max_position_usd: float = 1000.0
    max_single_trade_usd: float = 500.0

    # Paper trading
    paper_portfolio_path: str = "paper_portfolio.json"
    paper_starting_cash: float = 10000.0

    # Default watchlist (comma-separated)
    watchlist: str = "AAPL,MSFT,GOOGL,NVDA,TSLA"

    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.watchlist.split(",") if s.strip()]


class GrowthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GROWTH_", extra="ignore")

    # Your starting capital (USD) — money YOU deposit in your broker accounts
    starting_capital: float = 1000.0

    # Growth targets as multipliers (2x = double, 3x = triple)
    targets: str = "2,3"

    # Platform capital allocation (must sum to 1.0)
    alloc_robinhood: float = 0.50
    alloc_kalshi: float = 0.30
    alloc_polymarket: float = 0.20

    # Live trading gates — BOTH required for real money trades
    live_enabled: bool = False
    live_ack: str = ""  # Must be: I_ACCEPT_FINANCIAL_RISK

    # Risk limits for live trading
    risk_per_trade_pct: float = 0.03
    max_position_pct: float = 0.15
    max_drawdown_pct: float = 20.0
    max_daily_loss_pct: float = 10.0

    # Daemon settings
    cycle_interval_min: int = 30
    state_path: str = "growth_portfolio.json"

    def target_multipliers(self) -> list[float]:
        return [float(t.strip()) for t in self.targets.split(",") if t.strip()]

    def allocations(self) -> dict[str, float]:
        return {
            "robinhood": self.alloc_robinhood,
            "kalshi": self.alloc_kalshi,
            "polymarket": self.alloc_polymarket,
        }


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", populate_by_name=True)

    telegram_token: str = Field(
        default="",
        validation_alias=AliasChoices("TELEGRAM_BOT_TOKEN", "telegram_token"),
    )
    discord_token: str = Field(
        default="",
        validation_alias=AliasChoices("DISCORD_BOT_TOKEN", "discord_token"),
    )
    allowed_users: str = Field(
        default="",
        validation_alias=AliasChoices("BOT_ALLOWED_USERS", "allowed_users"),
    )

    def allowed_user_ids(self) -> set[str]:
        if not self.allowed_users.strip():
            return set()
        return {uid.strip() for uid in self.allowed_users.split(",") if uid.strip()}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    polymarket: PolymarketSettings = Field(default_factory=PolymarketSettings)
    kalshi: KalshiSettings = Field(default_factory=KalshiSettings)
    robinhood: RobinhoodSettings = Field(default_factory=RobinhoodSettings)
    ai: AISettings = Field(default_factory=AISettings)
    growth: GrowthSettings = Field(default_factory=GrowthSettings)
    bot: BotSettings = Field(default_factory=BotSettings)
    api_host: str = Field(default="0.0.0.0", validation_alias="MARKET_AGENT_API_HOST")
    api_port: int = Field(default=8000, validation_alias="MARKET_AGENT_API_PORT")


def load_settings() -> Settings:
    return Settings(
        polymarket=PolymarketSettings(),
        kalshi=KalshiSettings(),
        robinhood=RobinhoodSettings(),
        ai=AISettings(),
        growth=GrowthSettings(),
        bot=BotSettings(),
    )


def read_private_key_pem(settings: KalshiSettings) -> str:
    if settings.private_key_pem:
        return settings.private_key_pem
    if settings.private_key_path:
        return Path(settings.private_key_path).read_text(encoding="utf-8")
    raise ValueError("Kalshi private key not configured (set KALSHI_PRIVATE_KEY_PATH or KALSHI_PRIVATE_KEY_PEM)")
