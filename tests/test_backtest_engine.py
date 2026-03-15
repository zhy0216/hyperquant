import pytest
from datetime import datetime, timezone
from typing import Any

from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine, BacktestResult
from core.event_bus import EventBus
from core.events import Candle, MarketDataEvent, OrderFilledEvent, SignalEvent
from strategy.base import Strategy


# --- Helpers ---

def _make_uptrend_candles(n: int = 100, start_price: float = 100.0, start_ts: int = 1704067200000) -> list[Candle]:
    """1h candles starting 2024-01-01, price going up."""
    return [
        Candle(
            open=start_price + i - 0.5, high=start_price + i + 2,
            low=start_price + i - 1, close=start_price + i,
            volume=1000, timestamp=start_ts + i * 3600000,
        )
        for i in range(n)
    ]


class MemoryLoader(DataLoader):
    """In-memory loader for testing."""
    def __init__(self, candles_by_key: dict[tuple[str, str], list[Candle]]) -> None:
        self._data = candles_by_key

    async def load(self, symbol: str, timeframe: str, start: datetime, end: datetime) -> list[Candle]:
        candles = self._data.get((symbol, timeframe), [])
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        return [c for c in candles if start_ms <= c.timestamp <= end_ms]


class AlwaysLongStrategy(Strategy):
    """Emits a long signal on every primary-timeframe bar, for testing."""
    def __init__(self, bus: EventBus, config: dict, **kwargs: object) -> None:
        self._bus = bus
        self._config = config
        self._open_symbols: set[str] = set()
        self._signaled: set[str] = set()
        bus.subscribe(MarketDataEvent, self.on_market_data)
        bus.subscribe(OrderFilledEvent, self.on_order_filled)

    async def on_market_data(self, event: MarketDataEvent) -> None:
        if event.timeframe != self._config["strategy"]["primary_timeframe"]:
            return
        if event.symbol in self._open_symbols or event.symbol in self._signaled:
            return
        if len(event.candles) < 2:
            return
        close = event.candles[-1].close
        atr = 2.0  # Fixed ATR for simplicity
        signal = SignalEvent(
            symbol=event.symbol, direction="long", score=80.0,
            entry_price=close, atr=atr,
            stop_loss=close - 4.0, take_profit=close + 6.0,
            timestamp=event.timestamp,
        )
        self._signaled.add(event.symbol)
        await self._bus.publish(signal)

    async def on_order_filled(self, event: OrderFilledEvent) -> None:
        if event.action == "open":
            self._open_symbols.add(event.symbol)
        elif event.action == "close":
            self._open_symbols.discard(event.symbol)
            self._signaled.discard(event.symbol)


@pytest.fixture
def config() -> dict[str, Any]:
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
        "data": {"warmup_candles": 10},
        "backtest": {
            "slippage": 0.001, "fee_rate": 0.00035, "initial_equity": 10000,
        },
    }


async def test_engine_runs_and_returns_result(config: dict[str, Any]) -> None:
    candles = _make_uptrend_candles(50)
    loader = MemoryLoader({("BTC", "1h"): candles, ("BTC", "4h"): candles})

    engine = BacktestEngine(
        config=config, strategy_cls=AlwaysLongStrategy,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 10, tzinfo=timezone.utc),
    )
    result = await engine.run()

    assert isinstance(result, BacktestResult)
    assert len(result.equity_curve) > 0
    assert result.equity_curve[0] == 10000.0


async def test_engine_force_closes_at_end(config: dict[str, Any]) -> None:
    candles = _make_uptrend_candles(50)
    loader = MemoryLoader({("BTC", "1h"): candles, ("BTC", "4h"): candles})

    engine = BacktestEngine(
        config=config, strategy_cls=AlwaysLongStrategy,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 10, tzinfo=timezone.utc),
    )
    result = await engine.run()

    # All positions should be closed at end
    assert len(result.trade_log.open_entries) == 0
    # Should have at least 1 completed trade (entry + force-close)
    assert len(result.trade_log.get_trades()) >= 1


async def test_engine_equity_curve_tracks_pnl(config: dict[str, Any]) -> None:
    candles = _make_uptrend_candles(50)
    loader = MemoryLoader({("BTC", "1h"): candles, ("BTC", "4h"): candles})

    engine = BacktestEngine(
        config=config, strategy_cls=AlwaysLongStrategy,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 10, tzinfo=timezone.utc),
    )
    result = await engine.run()

    # In an uptrend, final equity should differ from initial (fees at minimum)
    assert result.equity_curve[-1] != result.equity_curve[0]
