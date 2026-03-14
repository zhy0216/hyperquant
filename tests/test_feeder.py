import time
from unittest.mock import AsyncMock

import pytest

from core.event_bus import EventBus
from core.events import Candle, MarketDataEvent
from data.feeder import DataFeeder


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def mock_client():
    client = AsyncMock()
    # Simulate candle response: list of dicts with OHLCV
    client.fetch_candles.return_value = [
        {"o": 100, "h": 105, "l": 99, "c": 103, "v": 1000, "t": 1000},
        {"o": 103, "h": 108, "l": 101, "c": 107, "v": 1200, "t": 2000},
    ]
    client.fetch_tickers.return_value = [
        {"symbol": "BTC", "volume_24h": 5_000_000, "listing_time": 0},
        {"symbol": "ETH", "volume_24h": 3_000_000, "listing_time": 0},
        # 3 days old - should be filtered out
        {"symbol": "NEW", "volume_24h": 5_000_000, "listing_time": time.time() - 3 * 86400},
    ]
    return client


async def test_fetch_candles_publishes_market_data_event(bus, mock_client):
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe(MarketDataEvent, handler)

    feeder = DataFeeder(bus=bus, client=mock_client, config={
        "data": {"warmup_candles": 200, "pool_refresh_interval": 300,
                 "min_volume_24h": 1_000_000, "min_listing_days": 7},
        "strategy": {"primary_timeframe": "1h", "confirm_timeframe": "4h"},
    })
    await feeder.fetch_and_publish_candles("BTC", "1h")

    assert len(received) == 1
    assert received[0].symbol == "BTC"
    assert received[0].timeframe == "1h"
    assert len(received[0].candles) == 2
    assert isinstance(received[0].candles[0], Candle)


async def test_fetch_tickers_returns_filtered_symbols(bus, mock_client):
    feeder = DataFeeder(bus=bus, client=mock_client, config={
        "data": {"warmup_candles": 200, "pool_refresh_interval": 300,
                 "min_volume_24h": 1_000_000, "min_listing_days": 7},
        "strategy": {"primary_timeframe": "1h", "confirm_timeframe": "4h"},
    })
    symbols = await feeder.refresh_symbol_pool()
    assert "BTC" in symbols
    assert "ETH" in symbols
    assert "NEW" not in symbols  # Filtered out: listed < 7 days ago
