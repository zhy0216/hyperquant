import logging
import time
from typing import Any

from core.event_bus import EventBus
from core.events import Candle, MarketDataEvent
from data.symbol_filter import filter_symbols

logger = logging.getLogger(__name__)


class DataFeeder:
    def __init__(self, bus: EventBus, client: Any, config: dict) -> None:  # type: ignore[type-arg]
        self._bus = bus
        self._client = client
        self._config = config
        self._symbol_pool: list[str] = []

    async def fetch_and_publish_candles(self, symbol: str, timeframe: str) -> None:
        raw = await self._client.fetch_candles(symbol, timeframe)
        candles = [
            Candle(
                open=c["o"], high=c["h"], low=c["l"],
                close=c["c"], volume=c["v"], timestamp=c["t"],
            )
            for c in raw
        ]
        event = MarketDataEvent(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            timestamp=int(time.time() * 1000),
        )
        await self._bus.publish(event)

    async def refresh_symbol_pool(self) -> list[str]:
        data_cfg = self._config["data"]
        tickers = await self._client.fetch_tickers()
        filtered = filter_symbols(
            tickers,
            min_volume=data_cfg["min_volume_24h"],
            min_listing_days=data_cfg["min_listing_days"],
        )
        self._symbol_pool = [t["symbol"] for t in filtered]
        logger.info("Symbol pool refreshed: %d symbols", len(self._symbol_pool))
        return self._symbol_pool

    @property
    def symbol_pool(self) -> list[str]:
        return self._symbol_pool
