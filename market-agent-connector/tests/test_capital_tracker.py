"""Tests for capital tracker."""

from market_agent.growth.capital_tracker import CapitalTracker


def test_initialize_and_track_growth(tmp_path):
    path = str(tmp_path / "growth.json")
    tracker = CapitalTracker(path)

    tracker.initialize(1000.0, [2.0, 3.0])
    assert tracker.is_initialized
    assert tracker.starting_capital == 1000.0

    status = tracker.update_value(1500.0)
    assert status["multiplier"] == 1.5
    assert status["total_pnl"] == 500.0
    assert status["total_pnl_pct"] == 50.0

    status = tracker.update_value(2000.0)
    assert "2x" in status["milestones_hit"]
    assert status["progress"]["2x"]["hit"] is True


def test_drawdown(tmp_path):
    path = str(tmp_path / "growth.json")
    tracker = CapitalTracker(path)
    tracker.initialize(1000.0)
    tracker.update_value(1500.0)
    tracker.update_value(1200.0)
    assert tracker.drawdown_pct() == 20.0


def test_record_trade(tmp_path):
    path = str(tmp_path / "growth.json")
    tracker = CapitalTracker(path)
    tracker.initialize(500.0)
    tracker.record_trade({"symbol": "AAPL", "action": "buy", "quantity": 5})
    status = tracker.status()
    assert status["trade_count"] == 1
