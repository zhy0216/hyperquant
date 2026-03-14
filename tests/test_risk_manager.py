import pytest

from core.event_bus import EventBus
from core.events import OrderRequestEvent, SignalEvent
from execution.risk_manager import RiskManager


@pytest.fixture
def config():
    return {
        "risk": {
            "risk_per_trade": 0.02, "max_open_positions": 5,
            "max_single_exposure": 0.20, "max_total_exposure": 0.80,
            "max_leverage": 3.0, "max_daily_loss": 0.05,
            "consecutive_loss_limit": 5, "cooldown_hours": 24,
        },
        "stop_loss": {"initial_atr_multiple": 2.0, "take_profit_atr_multiple": 3.0},
    }

@pytest.fixture
def bus():
    return EventBus()

def _make_signal(symbol="BTC", direction="long", score=75, entry=50000, atr=1500):
    return SignalEvent(
        symbol=symbol, direction=direction, score=score,
        entry_price=entry, atr=atr,
        stop_loss=entry - 2 * atr if direction == "long" else entry + 2 * atr,
        take_profit=entry + 3 * atr if direction == "long" else entry - 3 * atr,
        timestamp=1000,
    )

async def test_valid_signal_emits_order_request(bus, config):
    orders = []
    async def handler(event):
        orders.append(event)
    bus.subscribe(OrderRequestEvent, handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    await rm.on_signal(_make_signal())
    assert len(orders) == 1
    assert orders[0].symbol == "BTC"
    assert orders[0].direction == "long"
    assert orders[0].size > 0

async def test_rejects_when_max_positions_reached(bus, config):
    orders = []
    async def handler(event):
        orders.append(event)
    bus.subscribe(OrderRequestEvent, handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    for sym in ["A", "B", "C", "D", "E"]:
        rm._open_positions[sym] = {"notional": 1000, "direction": "long"}
    await rm.on_signal(_make_signal())
    assert len(orders) == 0

async def test_rejects_when_total_exposure_exceeded(bus, config):
    orders = []
    async def handler(event):
        orders.append(event)
    bus.subscribe(OrderRequestEvent, handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    rm._open_positions["ETH"] = {"notional": 8000, "direction": "long"}
    await rm.on_signal(_make_signal(entry=100, atr=1))
    assert len(orders) == 0

async def test_rejects_during_daily_loss_breaker(bus, config):
    orders = []
    async def handler(event):
        orders.append(event)
    bus.subscribe(OrderRequestEvent, handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    rm._daily_loss = 600
    await rm.on_signal(_make_signal())
    assert len(orders) == 0

async def test_rejects_during_consecutive_loss_cooldown(bus, config):
    import time
    orders = []
    async def handler(event):
        orders.append(event)
    bus.subscribe(OrderRequestEvent, handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    rm._consecutive_losses = 5
    rm._cooldown_until = time.time() + 86400  # cooldown active
    await rm.on_signal(_make_signal())
    assert len(orders) == 0
