import pytest

from core.event_bus import EventBus
from core.events import CloseSignalEvent, OrderFilledEvent
from portfolio.tracker import PortfolioTracker


@pytest.fixture
def config():
    return {
        "stop_loss": {
            "initial_atr_multiple": 2.0, "take_profit_atr_multiple": 3.0,
            "breakeven_trigger_atr": 1.0, "trailing_trigger_atr": 2.0,
            "trailing_distance_atr": 1.5,
        }
    }

@pytest.fixture
def bus():
    return EventBus()

async def test_open_fill_creates_position(bus, config):
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    assert "BTC" in tracker.positions
    assert tracker.positions["BTC"]["entry_price"] == 50000

async def test_close_fill_removes_position(bus, config):
    tracker = PortfolioTracker(bus=bus, config=config)
    fill_open = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill_open)
    fill_close = OrderFilledEvent(
        symbol="BTC", direction="long", action="close",
        filled_size=0.1, filled_price=52000, order_id="o2", fee=5.0, timestamp=2000,
    )
    await tracker.on_order_filled(fill_close)
    assert "BTC" not in tracker.positions

async def test_trailing_stop_stage1_no_move(bus, config):
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.set_atr("BTC", 1500)
    # Price moved up 500 (< 1*ATR=1500): stop stays at initial
    tracker.update_price("BTC", 50500)
    pos = tracker.positions["BTC"]
    assert pos["stop_loss"] == 50000 - 2 * 1500

async def test_trailing_stop_stage2_breakeven(bus, config):
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.set_atr("BTC", 1500)
    tracker.update_price("BTC", 51800)
    pos = tracker.positions["BTC"]
    assert pos["stop_loss"] == 50000

async def test_trailing_stop_stage3_trailing(bus, config):
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.set_atr("BTC", 1500)
    tracker.update_price("BTC", 53500)
    pos = tracker.positions["BTC"]
    expected_sl = 53500 - 1.5 * 1500
    assert pos["stop_loss"] == expected_sl

async def test_stop_loss_emits_close_signal(bus, config):
    close_signals = []
    async def handler(event):
        close_signals.append(event)
    bus.subscribe(CloseSignalEvent, handler)
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.set_atr("BTC", 1500)
    tracker.positions["BTC"]["stop_loss"] = 47000
    await tracker.check_exits("BTC", 46500)
    assert len(close_signals) == 1
    assert close_signals[0].reason == "stop_loss"

async def test_take_profit_emits_close_signal(bus, config):
    close_signals = []
    async def handler(event):
        close_signals.append(event)
    bus.subscribe(CloseSignalEvent, handler)
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.set_atr("BTC", 1500)
    tracker.positions["BTC"]["take_profit"] = 54500
    await tracker.check_exits("BTC", 55000)
    assert len(close_signals) == 1
    assert close_signals[0].reason == "take_profit"

async def test_trailing_stop_short_direction(bus, config):
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="ETH", direction="short", action="open",
        filled_size=1.0, filled_price=3000, order_id="o1", fee=3.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.set_atr("ETH", 100)
    tracker.update_price("ETH", 2750)
    pos = tracker.positions["ETH"]
    expected_sl = 2750 + 1.5 * 100
    assert pos["stop_loss"] == expected_sl
