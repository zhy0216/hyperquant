import pytest
from core.event_bus import EventBus
from core.events import OrderFilledEvent, OrderRequestEvent
from backtest.simulated_executor import SimulatedExecutor


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def current_prices() -> dict[str, float]:
    return {"BTC": 50000.0, "ETH": 3000.0}


@pytest.fixture
def executor(bus: EventBus, current_prices: dict[str, float]) -> SimulatedExecutor:
    return SimulatedExecutor(
        bus=bus, current_prices=current_prices,
        slippage=0.001, fee_rate=0.00035,
    )


async def test_open_long_fill(bus: EventBus, executor: SimulatedExecutor, current_prices: dict[str, float]) -> None:
    fills: list[OrderFilledEvent] = []

    async def on_fill(e: OrderFilledEvent) -> None:
        fills.append(e)

    bus.subscribe(OrderFilledEvent, on_fill)

    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="open",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=48000, take_profit=54000, reason="test", timestamp=1000,
    )
    await bus.publish(req)

    assert len(fills) == 1
    f = fills[0]
    assert f.symbol == "BTC"
    assert f.direction == "long"
    assert f.action == "open"
    assert f.filled_size == 0.1
    # Buy: price * (1 + slippage) = 50000 * 1.001 = 50050
    assert abs(f.filled_price - 50050.0) < 0.01
    # Fee: 50050 * 0.1 * 0.00035 = 1.75175
    assert abs(f.fee - 1.75175) < 0.001


async def test_open_short_fill(bus: EventBus, executor: SimulatedExecutor, current_prices: dict[str, float]) -> None:
    fills: list[OrderFilledEvent] = []

    async def on_fill(e: OrderFilledEvent) -> None:
        fills.append(e)

    bus.subscribe(OrderFilledEvent, on_fill)

    req = OrderRequestEvent(
        symbol="BTC", direction="short", action="open",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=52000, take_profit=46000, reason="test", timestamp=1000,
    )
    await bus.publish(req)

    f = fills[0]
    # Sell: price * (1 - slippage) = 50000 * 0.999 = 49950
    assert abs(f.filled_price - 49950.0) < 0.01


async def test_close_long_fill(bus: EventBus, executor: SimulatedExecutor, current_prices: dict[str, float]) -> None:
    """Closing a long = selling -> adverse slippage is downward."""
    fills: list[OrderFilledEvent] = []

    async def on_fill(e: OrderFilledEvent) -> None:
        fills.append(e)

    bus.subscribe(OrderFilledEvent, on_fill)

    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="close",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=0, take_profit=0, reason="trailing_stop", timestamp=2000,
    )
    await bus.publish(req)

    f = fills[0]
    # Close long = sell: price * (1 - slippage) = 49950
    assert abs(f.filled_price - 49950.0) < 0.01


async def test_close_short_fill(bus: EventBus, executor: SimulatedExecutor, current_prices: dict[str, float]) -> None:
    """Closing a short = buying -> adverse slippage is upward."""
    fills: list[OrderFilledEvent] = []

    async def on_fill(e: OrderFilledEvent) -> None:
        fills.append(e)

    bus.subscribe(OrderFilledEvent, on_fill)

    req = OrderRequestEvent(
        symbol="BTC", direction="short", action="close",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=0, take_profit=0, reason="stop_loss", timestamp=2000,
    )
    await bus.publish(req)

    f = fills[0]
    # Close short = buy: price * (1 + slippage) = 50050
    assert abs(f.filled_price - 50050.0) < 0.01


async def test_missing_symbol_logs_warning(bus: EventBus, executor: SimulatedExecutor, caplog: pytest.LogCaptureFixture) -> None:
    req = OrderRequestEvent(
        symbol="UNKNOWN", direction="long", action="open",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=0, take_profit=0, reason="test", timestamp=1000,
    )
    await bus.publish(req)
    assert "No price available" in caplog.text
