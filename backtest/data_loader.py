import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime

from core.events import Candle

logger = logging.getLogger(__name__)


class DataLoader(ABC):
    @abstractmethod
    async def load(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> list[Candle]:
        """Load candles for a symbol/timeframe in [start, end].
        Returns list[Candle] sorted by timestamp ascending."""


class HyperliquidLoader(DataLoader):
    """Loads candles from Hyperliquid API with local SQLite caching.

    Not yet implemented — requires a production Hyperliquid client.
    """

    async def load(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> list[Candle]:
        raise NotImplementedError(
            "HyperliquidLoader requires a production Hyperliquid client. "
            "Use CsvLoader or ParquetLoader instead."
        )


class CsvLoader(DataLoader):
    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir

    async def load(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> list[Candle]:
        import csv

        filename = f"{symbol}_{timeframe}.csv"
        filepath = os.path.join(self._data_dir, filename)
        if not os.path.exists(filepath):
            logger.warning("CSV file not found: %s", filepath)
            return []

        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        candles: list[Candle] = []

        with open(filepath, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = int(row["timestamp"])
                if ts < start_ms or ts > end_ms:
                    continue
                candles.append(Candle(
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    timestamp=ts,
                ))

        candles.sort(key=lambda c: c.timestamp)
        return candles


class ParquetLoader(DataLoader):
    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir

    async def load(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> list[Candle]:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            logger.error("pyarrow is required for ParquetLoader. Install with: pip install pyarrow")
            return []

        filename = f"{symbol}_{timeframe}.parquet"
        filepath = os.path.join(self._data_dir, filename)
        if not os.path.exists(filepath):
            logger.warning("Parquet file not found: %s", filepath)
            return []

        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        table = pq.read_table(filepath)
        df = table.to_pandas()
        df = df[(df["timestamp"] >= start_ms) & (df["timestamp"] <= end_ms)]
        df = df.sort_values("timestamp")

        return [
            Candle(
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                timestamp=int(row["timestamp"]),
            )
            for _, row in df.iterrows()
        ]
