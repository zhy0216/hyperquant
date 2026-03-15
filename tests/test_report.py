import os
from datetime import datetime, timezone, timedelta
from typing import Any

import pytest

from backtest.report import ReportGenerator
from backtest.trade_log import TradeRecord


def _sample_trades() -> list[TradeRecord]:
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        TradeRecord(
            symbol="BTC", direction="long", entry_price=100, exit_price=110,
            size=0.1, entry_time=base, exit_time=base + timedelta(hours=24),
            pnl=1.0, fee=0.5, exit_reason="take_profit",
        ),
        TradeRecord(
            symbol="ETH", direction="short", entry_price=50, exit_price=48,
            size=1.0, entry_time=base + timedelta(days=1),
            exit_time=base + timedelta(days=1, hours=12),
            pnl=2.0, fee=0.3, exit_reason="trailing_stop",
        ),
    ]


def _sample_metrics() -> dict[str, Any]:
    return {
        "total_return": 0.03, "annualized_return": 0.15,
        "sharpe_ratio": 1.5, "sortino_ratio": 2.0,
        "max_drawdown": 500, "max_drawdown_pct": 0.05,
        "win_rate": 0.6, "profit_factor": 2.0,
        "avg_trade_duration": "1 day, 0:00:00",
        "max_consecutive_losses": 2, "total_trades": 10,
    }


def test_print_summary(capsys: pytest.CaptureFixture[str]) -> None:
    gen = ReportGenerator(
        trades=_sample_trades(), metrics=_sample_metrics(),
        equity_curve=[10000, 10100, 10300], timestamps=[],
    )
    gen.print_summary()
    captured = capsys.readouterr()
    assert "total_return" in captured.out
    assert "sharpe_ratio" in captured.out


def test_export_csv(tmp_path: Any) -> None:
    gen = ReportGenerator(
        trades=_sample_trades(), metrics=_sample_metrics(),
        equity_curve=[], timestamps=[],
    )
    path = str(tmp_path / "trades.csv")
    gen.export_csv(path)
    assert os.path.exists(path)
    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 3  # header + 2 trades


def test_generate_html(tmp_path: Any) -> None:
    gen = ReportGenerator(
        trades=_sample_trades(), metrics=_sample_metrics(),
        equity_curve=[10000, 10100, 10300],
        timestamps=[1704067200000, 1704070800000, 1704074400000],
    )
    path = str(tmp_path / "report.html")
    gen.generate_html(path)
    assert os.path.exists(path)
    with open(path) as f:
        content = f.read()
    assert "<!DOCTYPE html>" in content
    assert "total_return" in content
