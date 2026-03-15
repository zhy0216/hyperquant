import os
from datetime import datetime, timezone
from typing import Any

import pytest

from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine
from backtest.metrics import compute_metrics
from backtest.report import ReportGenerator
from core.events import Candle
from strategy.signal_engine import SignalEngine


def _make_uptrend_candles(n: int = 200, start_price: float = 100.0, start_ts: int = 1704067200000) -> list[Candle]:
    return [
        Candle(
            open=start_price + i - 0.5, high=start_price + i + 2,
            low=start_price + i - 1, close=start_price + i,
            volume=1000, timestamp=start_ts + i * 3600000,
        )
        for i in range(n)
    ]


class MemoryLoader(DataLoader):
    def __init__(self, candles_by_key: dict[tuple[str, str], list[Candle]]) -> None:
        self._data = candles_by_key

    async def load(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        candles = self._data.get((symbol, timeframe), [])
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        return [c for c in candles if start_ms <= c.timestamp <= end_ms]


@pytest.fixture
def full_config() -> dict[str, Any]:
    return {
        "strategy": {
            "primary_timeframe": "1h", "confirm_timeframe": "4h",
            "score_threshold": 65, "ema_fast": 20, "ema_slow": 60,
            "rsi_period": 14, "macd_fast": 12, "macd_slow": 26,
            "macd_signal": 9, "donchian_period": 20, "atr_period": 14,
            "exit_score_threshold": 30, "max_new_positions": 3,
        },
        "risk": {
            "risk_per_trade": 0.02, "max_open_positions": 5,
            "max_single_exposure": 0.20, "max_total_exposure": 0.80,
            "max_leverage": 3.0, "max_daily_loss": 0.05,
            "consecutive_loss_limit": 5, "cooldown_hours": 24,
        },
        "stop_loss": {
            "initial_atr_multiple": 2.0, "take_profit_atr_multiple": 3.0,
            "breakeven_trigger_atr": 1.0, "trailing_trigger_atr": 2.0,
            "trailing_distance_atr": 1.5,
        },
        "data": {"warmup_candles": 100},
        "backtest": {
            "slippage": 0.001, "fee_rate": 0.00035, "initial_equity": 10000,
        },
    }


async def test_full_pipeline_with_signal_engine(full_config: dict[str, Any]) -> None:
    """Integration: real SignalEngine strategy through full backtest pipeline."""
    candles = _make_uptrend_candles(300)
    loader = MemoryLoader({
        ("BTC", "1h"): candles,
        ("BTC", "4h"): candles,  # Use same data for simplicity
    })

    engine = BacktestEngine(
        config=full_config, strategy_cls=SignalEngine,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 5, tzinfo=timezone.utc),  # After warmup
        end=datetime(2024, 1, 12, tzinfo=timezone.utc),
    )
    result = await engine.run()

    # Should have equity curve
    assert len(result.equity_curve) > 0

    # Compute metrics
    trades = result.trade_log.get_trades()
    metrics = compute_metrics(
        trades=trades,
        equity_curve=result.equity_curve,
        initial_equity=10000,
    )
    assert "total_return" in metrics
    assert "sharpe_ratio" in metrics
    assert metrics["total_trades"] >= 0


async def test_full_pipeline_generates_reports(full_config: dict[str, Any], tmp_path: Any) -> None:
    """Integration: verify report generation from real backtest result."""
    candles = _make_uptrend_candles(300)
    loader = MemoryLoader({
        ("BTC", "1h"): candles,
        ("BTC", "4h"): candles,
    })

    engine = BacktestEngine(
        config=full_config, strategy_cls=SignalEngine,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 5, tzinfo=timezone.utc),
        end=datetime(2024, 1, 12, tzinfo=timezone.utc),
    )
    result = await engine.run()

    trades = result.trade_log.get_trades()
    metrics = compute_metrics(
        trades=trades, equity_curve=result.equity_curve, initial_equity=10000,
    )
    gen = ReportGenerator(
        trades=trades, metrics=metrics,
        equity_curve=result.equity_curve, timestamps=result.timestamps,
    )

    # CSV
    csv_path = str(tmp_path / "trades.csv")
    gen.export_csv(csv_path)
    assert os.path.exists(csv_path)

    # HTML
    html_path = str(tmp_path / "report.html")
    gen.generate_html(html_path)
    assert os.path.exists(html_path)
