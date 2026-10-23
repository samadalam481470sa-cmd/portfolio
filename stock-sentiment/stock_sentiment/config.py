"""Typed configuration loaded from config.yaml."""
from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.yaml"


class HttpConfig(BaseModel):
    user_agent: str = "Mozilla/5.0"
    sec_user_agent: str = ""
    timeout: float = 15
    max_retries: int = 3
    min_interval_seconds: float = 2.0
    respect_robots: bool = True


class SentimentConfig(BaseModel):
    model: str = "finbert"
    baseline_model: str | None = "vader"
    batch_size: int = 16


class SourceConfig(BaseModel):
    enabled: bool = True
    weight: float = 1.0


class SignalConfig(BaseModel):
    lookback_hours: float = 72
    half_life_hours: float = 24
    baseline_days: int = 30
    confidence_k: float = 3.0
    near_dup_threshold: int = 88
    rehash_novelty: float = 0.3


class AlertConfig(BaseModel):
    enabled: bool = False
    webhook_url: str = ""
    kind: str = "discord"
    min_abs_delta: float = 0.35
    min_volume_z: float = 2.0
    min_confidence: float = 0.5


class ScheduleConfig(BaseModel):
    fetch_minutes: int = 15
    signals_minutes: int = 60
    daily_eval_time: str = "17:30"


class TickerEntry(BaseModel):
    ticker: str
    name: str
    aliases: list[str] = Field(default_factory=list)
    # Aliases that are also common words ("Apple", "Visa") only count next to finance context words.
    context_required: bool = False


class Settings(BaseModel):
    db_path: Path = Path("data/sentiment.db")
    raw_cache_dir: Path = Path("data/raw")
    http: HttpConfig = HttpConfig()
    sentiment: SentimentConfig = SentimentConfig()
    sources: dict[str, SourceConfig] = Field(default_factory=dict)
    signal: SignalConfig = SignalConfig()
    alerts: AlertConfig = AlertConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    ambiguous_tickers: list[str] = Field(default_factory=list)
    universe: list[TickerEntry] = Field(default_factory=list)
    # Optional extra universe (e.g. written by `cli universe --sp500`); entries in `universe` take precedence.
    universe_file: Path | None = Path("data/universe.yaml")
    benchmark: str = "SPY"

    def full_universe(self) -> list[TickerEntry]:
        entries = {e.ticker: e for e in self.universe}
        if self.universe_file and self.universe_file.exists():
            for raw in yaml.safe_load(self.universe_file.read_text()) or []:
                e = TickerEntry(**raw)
                entries.setdefault(e.ticker, e)
        return list(entries.values())

    def source_weight(self, name: str) -> float:
        cfg = self.sources.get(name)
        return cfg.weight if cfg else 1.0


def load_settings(path: str | Path | None = None) -> Settings:
    path = Path(path) if path else DEFAULT_CONFIG
    data = yaml.safe_load(path.read_text()) or {}
    settings = Settings(**data)
    base = path.resolve().parent
    if not settings.db_path.is_absolute():
        settings.db_path = base / settings.db_path
    if not settings.raw_cache_dir.is_absolute():
        settings.raw_cache_dir = base / settings.raw_cache_dir
    if settings.universe_file and not settings.universe_file.is_absolute():
        settings.universe_file = base / settings.universe_file
    return settings
