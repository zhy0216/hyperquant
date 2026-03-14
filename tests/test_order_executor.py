import pytest
from unittest.mock import AsyncMock
from core.event_bus import EventBus
from core.events import OrderRequestEvent, OrderFilledEvent
from execution.order_executor import OrderExecutor

@pytest.fixture
def bus():
    return EventBus()

@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.place_limit_order.return_value = {
        "order_id": "ord_123", "filled_size": 0.1, "filled_price": 50000, "status": "filled", "fee": 5.0,
    }
    client.place_market_order.return_value = {
        "order_id": "ord_124", "filled_size": 0.1, "filled_price": 50050, "status": "filled", "fee": 5.0,
    }
    client.cancel_order.return_value = True
    client.set_tp_sl.return_value = True
    return client

@pytest.fixture
def config():
    return {"exchange": {"slippage_tolerance": 0.001, "order_timeout_sec": 30}}

async def test_limit_order_filled_emits_event(bus, mock_client, config):
    fills = []
    async def handler(event):
        fills.append(event)
    bus.subscribe(OrderFilledEvent, handler)
    executor = OrderExecutor(bus=bus, client=mock_client, config=config)
    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="open", size=0.1,
        order_type="limit", limit_price=50000, stop_loss=47000, take_profit=54500,
        reason="trend score 75", timestamp=1000,
    )
    await executor.on_order_request(req)
    assert len(fills) == 1
    assert fills[0].symbol == "BTC"
    assert fills[0].filled_size == 0.1
    assert fills[0].order_id == "ord_123"

async def test_partial_fill_triggers_market_order(bus, mock_client, config):
    mock_client.place_limit_order.return_value = {
        "order_id": "ord_125", "filled_size": 0.05, "filled_price": 50000, "status": "partial", "fee": 2.5,
    }
    fills = []
    async def handler(event):
        fills.append(event)
    bus.subscribe(OrderFilledEvent, handler)
    executor = OrderExecutor(bus=bus, client=mock_client, config=config)
    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="open", size=0.1,
        order_type="limit", limit_price=50000, stop_loss=47000, take_profit=54500,
        reason="trend score 75", timestamp=1000,
    )
    await executor.on_order_request(req)
    mock_client.cancel_order.assert_called_once()
    mock_client.place_market_order.assert_called_once()
    assert len(fills) == 2

async def test_tp_sl_set_after_open_fill(bus, mock_client, config):
    fills = []
    async def handler(event):
        fills.append(event)
    bus.subscribe(OrderFilledEvent, handler)
    executor = OrderExecutor(bus=bus, client=mock_client, config=config)
    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="open", size=0.1,
        order_type="limit", limit_price=50000, stop_loss=47000, take_profit=54500,
        reason="trend score 75", timestamp=1000,
    )
    await executor.on_order_request(req)
    mock_client.set_tp_sl.assert_called_once_with("BTC", 47000, 54500)
