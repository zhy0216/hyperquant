import pytest
from core.event_bus import EventBus
from core.events import SignalEvent, OrderRequestEvent


@pytest.mark.asyncio
async def test_subscribe_and_publish():
    bus = EventBus()
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(SignalEvent, handler)

    sig = SignalEvent(
        symbol="BTC", direction="long", score=80.0,
        entry_price=50000.0, atr=1500.0,
        stop_loss=47000.0, take_profit=54500.0,
        timestamp=1700000000000,
    )
    await bus.publish(sig)

    assert len(received) == 1
    assert received[0].symbol == "BTC"


@pytest.mark.asyncio
async def test_multiple_subscribers():
    bus = EventBus()
    calls = []

    async def handler_a(event):
        calls.append("a")

    async def handler_b(event):
        calls.append("b")

    bus.subscribe(SignalEvent, handler_a)
    bus.subscribe(SignalEvent, handler_b)

    sig = SignalEvent(
        symbol="ETH", direction="short", score=70.0,
        entry_price=3000.0, atr=100.0,
        stop_loss=3300.0, take_profit=2700.0,
        timestamp=1700000000000,
    )
    await bus.publish(sig)

    assert sorted(calls) == ["a", "b"]


@pytest.mark.asyncio
async def test_no_subscribers_noop():
    bus = EventBus()
    # Publishing with no subscribers should not raise
    sig = SignalEvent(
        symbol="BTC", direction="long", score=75.0,
        entry_price=50000.0, atr=1500.0,
        stop_loss=47000.0, take_profit=54500.0,
        timestamp=1700000000000,
    )
    await bus.publish(sig)  # Should complete without error


@pytest.mark.asyncio
async def test_handler_exception_isolation():
    bus = EventBus()
    calls = []

    async def bad_handler(event):
        raise RuntimeError("Handler failure")

    async def good_handler(event):
        calls.append("good")

    bus.subscribe(SignalEvent, bad_handler)
    bus.subscribe(SignalEvent, good_handler)

    sig = SignalEvent(
        symbol="BTC", direction="long", score=80.0,
        entry_price=50000.0, atr=1500.0,
        stop_loss=47000.0, take_profit=54500.0,
        timestamp=1700000000000,
    )
    # Should not raise even though bad_handler throws
    await bus.publish(sig)

    # good_handler must still have been called
    assert calls == ["good"]
