import pytest
from core.event_bus import EventBus
from core.events import MarketDataEvent, OrderFilledEvent
from strategy.base import Strategy


class DummyStrategy(Strategy):
    def __init__(self, bus: EventBus, config: dict, **kwargs: object) -> None:
        self.bus = bus
        self.received: list = []

    async def on_market_data(self, event: MarketDataEvent) -> None:
        self.received.append(event)


def test_cannot_instantiate_abc() -> None:
    with pytest.raises(TypeError):
        Strategy(bus=EventBus(), config={})  # type: ignore[abstract]


def test_dummy_strategy_instantiates() -> None:
    s = DummyStrategy(bus=EventBus(), config={})
    assert s is not None


async def test_on_order_filled_default_noop() -> None:
    s = DummyStrategy(bus=EventBus(), config={})
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="o1", fee=5.0, timestamp=1000,
    )
    await s.on_order_filled(fill)  # Should not raise


def test_clear_cycle_cooldowns_default_noop() -> None:
    s = DummyStrategy(bus=EventBus(), config={})
    s.clear_cycle_cooldowns()  # Should not raise
