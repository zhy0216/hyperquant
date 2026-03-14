import pytest

from core.event_bus import EventBus
from core.events import Candle, CloseSignalEvent, MarketDataEvent, SignalEvent
from strategy.signal_engine import SignalEngine


def _make_uptrend_candles(n=100, start=100.0):
    return [
        Candle(
            open=start + i - 0.5, high=start + i + 2,
            low=start + i - 1, close=start + i,
            volume=1000, timestamp=i * 3600000,
        )
        for i in range(n)
    ]


def _make_downtrend_candles(n=100, start=200.0):
    return [
        Candle(
            open=start - i + 0.5, high=start - i + 1,
            low=start - i - 2, close=start - i,
            volume=1000, timestamp=i * 3600000,
        )
        for i in range(n)
    ]


@pytest.fixture
def config():
    return {
        "strategy": {
            "primary_timeframe": "1h", "confirm_timeframe": "4h",
            "score_threshold": 65, "max_new_positions": 3,
            "ema_fast": 20, "ema_slow": 60, "rsi_period": 14,
            "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
            "donchian_period": 20, "atr_period": 14,
            "exit_score_threshold": 30,
        },
        "risk": {"max_open_positions": 5},
        "stop_loss": {
            "initial_atr_multiple": 2.0,
            "take_profit_atr_multiple": 3.0,
        },
    }


@pytest.fixture
def bus():
    return EventBus()


async def test_uptrend_emits_signal(bus, config):
    signals = []

    async def handler(event):
        signals.append(event)

    bus.subscribe(SignalEvent, handler)
    engine = SignalEngine(bus=bus, config=config)

    candles_1h = _make_uptrend_candles(100)
    candles_4h = _make_uptrend_candles(100)

    # Feed 4h data first for confirmation
    event_4h = MarketDataEvent(symbol="BTC", timeframe="4h", candles=candles_4h, timestamp=1000)
    await engine.on_market_data(event_4h)

    # Feed 1h data to trigger signal evaluation
    event_1h = MarketDataEvent(symbol="BTC", timeframe="1h", candles=candles_1h, timestamp=1000)
    await engine.on_market_data(event_1h)

    # With strong uptrend, should emit a long signal
    long_signals = [s for s in signals if s.direction == "long"]
    assert len(long_signals) >= 1
    assert long_signals[0].symbol == "BTC"
    assert long_signals[0].score > 0


async def test_no_signal_when_below_threshold(bus, config):
    config["strategy"]["score_threshold"] = 99  # Nearly impossible to reach
    signals = []

    async def handler(event):
        signals.append(event)

    bus.subscribe(SignalEvent, handler)
    engine = SignalEngine(bus=bus, config=config)

    candles = _make_uptrend_candles(100)
    event_4h = MarketDataEvent(symbol="BTC", timeframe="4h", candles=candles, timestamp=1000)
    await engine.on_market_data(event_4h)
    event_1h = MarketDataEvent(symbol="BTC", timeframe="1h", candles=candles, timestamp=1000)
    await engine.on_market_data(event_1h)

    assert len(signals) == 0


async def test_close_signal_on_trend_reversal(bus, config):
    close_signals = []

    async def handler(event):
        close_signals.append(event)

    bus.subscribe(CloseSignalEvent, handler)
    engine = SignalEngine(bus=bus, config=config)

    # Simulate existing position
    engine._open_positions.add("BTC")
    engine._position_directions["BTC"] = "long"

    # Feed downtrend data (reversal from long position)
    candles_down = _make_downtrend_candles(100)
    event_4h = MarketDataEvent(symbol="BTC", timeframe="4h", candles=candles_down, timestamp=1000)
    await engine.on_market_data(event_4h)
    event_1h = MarketDataEvent(symbol="BTC", timeframe="1h", candles=candles_down, timestamp=1000)
    await engine.on_market_data(event_1h)

    assert len(close_signals) >= 1
    assert close_signals[0].reason == "trend_reversal"
