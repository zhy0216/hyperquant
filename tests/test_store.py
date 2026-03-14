import pytest

from core.events import Candle, OrderFilledEvent
from data.store import Store


@pytest.fixture
async def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    s = Store(db_path)
    await s.initialize()
    yield s
    await s.close()


async def test_save_and_load_candles(store):
    candles = [
        Candle(open=100, high=105, low=99, close=103, volume=1000, timestamp=1000),
        Candle(open=103, high=108, low=101, close=107, volume=1200, timestamp=2000),
    ]
    await store.save_candles("BTC", "1h", candles)
    loaded = await store.load_candles("BTC", "1h", limit=10)
    assert len(loaded) == 2
    assert loaded[0].open == 100
    assert loaded[1].close == 107


async def test_load_candles_respects_limit(store):
    candles = [
        Candle(open=i, high=i+1, low=i-1, close=i, volume=100, timestamp=i * 1000)
        for i in range(10)
    ]
    await store.save_candles("ETH", "1h", candles)
    loaded = await store.load_candles("ETH", "1h", limit=3)
    assert len(loaded) == 3
    # Should return the latest 3
    assert loaded[-1].timestamp == 9000


async def test_save_candles_upserts_on_duplicate(store):
    c1 = Candle(open=100, high=105, low=99, close=103, volume=1000, timestamp=1000)
    await store.save_candles("BTC", "1h", [c1])
    c1_updated = Candle(open=100, high=106, low=99, close=104, volume=1100, timestamp=1000)
    await store.save_candles("BTC", "1h", [c1_updated])
    loaded = await store.load_candles("BTC", "1h", limit=10)
    assert len(loaded) == 1
    assert loaded[0].close == 104


async def test_record_and_list_trades(store):
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="abc123",
        fee=5.0, timestamp=1000,
    )
    await store.record_trade(fill)
    trades = await store.list_trades(symbol="BTC", limit=10)
    assert len(trades) == 1
    assert trades[0]["order_id"] == "abc123"


async def test_save_and_load_position(store):
    pos = {
        "symbol": "ETH", "direction": "long", "size": 1.5,
        "entry_price": 3000, "stop_loss": 2700, "take_profit": 3450,
        "timestamp": 1000,
    }
    await store.save_position(pos)
    loaded = await store.load_positions()
    assert len(loaded) == 1
    assert loaded[0]["symbol"] == "ETH"


async def test_remove_position(store):
    pos = {
        "symbol": "ETH", "direction": "long", "size": 1.5,
        "entry_price": 3000, "stop_loss": 2700, "take_profit": 3450,
        "timestamp": 1000,
    }
    await store.save_position(pos)
    await store.remove_position("ETH")
    loaded = await store.load_positions()
    assert len(loaded) == 0
