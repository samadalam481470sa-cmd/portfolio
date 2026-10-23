"""Track capital growth toward 2x/3x targets across all platforms."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class CapitalTracker:
    """Persists starting capital, milestones, and trade history."""

    def __init__(self, path: str = "growth_portfolio.json") -> None:
        self.path = Path(path)
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {
            "starting_capital": 0.0,
            "targets": {"2x": 0.0, "3x": 0.0},
            "milestones_hit": [],
            "peak_value": 0.0,
            "current_value": 0.0,
            "total_pnl": 0.0,
            "total_pnl_pct": 0.0,
            "multiplier": 1.0,
            "trades": [],
            "daily_pnl": {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_updated": None,
        }

    def _save(self) -> None:
        self.path.write_text(json.dumps(self._data, indent=2, default=str))

    def initialize(self, starting_capital: float, targets: list[float] | None = None) -> dict[str, Any]:
        """Set starting capital and growth targets (e.g. [2.0, 3.0] for 2x and 3x)."""
        multipliers = targets or [2.0, 3.0]
        self._data["starting_capital"] = starting_capital
        self._data["current_value"] = starting_capital
        self._data["peak_value"] = starting_capital
        self._data["targets"] = {f"{int(m)}x": starting_capital * m for m in multipliers}
        self._data["multiplier"] = 1.0
        self._data["milestones_hit"] = []
        self._save()
        return self.status()

    def update_value(self, current_value: float) -> dict[str, Any]:
        """Update portfolio value and check milestone progress."""
        start = self._data["starting_capital"]
        if start <= 0:
            return self.status()

        self._data["current_value"] = current_value
        self._data["peak_value"] = max(self._data["peak_value"], current_value)
        self._data["total_pnl"] = current_value - start
        self._data["total_pnl_pct"] = round(((current_value - start) / start) * 100, 2)
        self._data["multiplier"] = round(current_value / start, 3)
        self._data["last_updated"] = datetime.now(timezone.utc).isoformat()

        for label, target in self._data["targets"].items():
            if current_value >= target and label not in self._data["milestones_hit"]:
                self._data["milestones_hit"].append(label)

        self._save()
        return self.status()

    def record_trade(self, trade: dict[str, Any]) -> None:
        trade["timestamp"] = datetime.now(timezone.utc).isoformat()
        self._data["trades"].append(trade)
        if len(self._data["trades"]) > 500:
            self._data["trades"] = self._data["trades"][-500:]
        self._save()

    def record_daily_pnl(self, pnl: float) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self._data["daily_pnl"][today] = self._data["daily_pnl"].get(today, 0.0) + pnl
        self._save()

    def get_daily_pnl(self) -> float:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._data["daily_pnl"].get(today, 0.0)

    def drawdown_pct(self) -> float:
        peak = self._data["peak_value"]
        current = self._data["current_value"]
        if peak <= 0:
            return 0.0
        return round(((peak - current) / peak) * 100, 2)

    def status(self) -> dict[str, Any]:
        start = self._data["starting_capital"]
        current = self._data["current_value"]
        targets = self._data["targets"]
        progress = {}
        for label, target in targets.items():
            if target > 0:
                progress[label] = {
                    "target_usd": target,
                    "progress_pct": min(100, round((current / target) * 100, 1)),
                    "remaining_usd": max(0, round(target - current, 2)),
                    "hit": label in self._data["milestones_hit"],
                }

        return {
            "starting_capital": start,
            "current_value": current,
            "total_pnl": self._data["total_pnl"],
            "total_pnl_pct": self._data["total_pnl_pct"],
            "multiplier": self._data["multiplier"],
            "peak_value": self._data["peak_value"],
            "drawdown_pct": self.drawdown_pct(),
            "targets": targets,
            "milestones_hit": self._data["milestones_hit"],
            "progress": progress,
            "trade_count": len(self._data["trades"]),
            "daily_pnl": self.get_daily_pnl(),
            "last_updated": self._data["last_updated"],
        }

    @property
    def is_initialized(self) -> bool:
        return self._data["starting_capital"] > 0

    @property
    def starting_capital(self) -> float:
        return self._data["starting_capital"]
