import os
from datetime import datetime, timezone
from typing import Any

import pytest

from backtest.data_loader import CsvLoader, ParquetLoader
from core.events import Candle


def _make_csv(tmp_path: Any, symbol: str = "BTC-PERP", timeframe: str = "1h", rows: int = 10) -> str:
    path = tmp_path / f"{symbol}_{timeframe}.csv"
    with open(path, "w") as f:
        f.write("timestamp,open,high,low,close,volume\n")
        for i in range(rows):
            ts = 1704067200000 + i * 3600000  # 2024-01-01 + i hours
            f.write(f"{ts},{100+i},{102+i},{99+i},{101+i},{1000}\n")
    return str(tmp_path)


async def test_csv_loader_basic(tmp_path: Any) -> None:
    csv_dir = _make_csv(tmp_path)
    loader = CsvLoader(data_dir=csv_dir)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    candles = await loader.load("BTC-PERP", "1h", start, end)
    assert len(candles) > 0
    assert all(isinstance(c, Candle) for c in candles)
    # Sorted ascending
    for i in range(1, len(candles)):
        assert candles[i].timestamp >= candles[i - 1].timestamp


async def test_csv_loader_filters_by_date(tmp_path: Any) -> None:
    csv_dir = _make_csv(tmp_path, rows=100)
    loader = CsvLoader(data_dir=csv_dir)
    start = datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc)  # Skip first 2 hours
    end = datetime(2024, 1, 1, 5, 0, tzinfo=timezone.utc)

    candles = await loader.load("BTC-PERP", "1h", start, end)
    for c in candles:
        assert c.timestamp >= int(start.timestamp() * 1000)
        assert c.timestamp <= int(end.timestamp() * 1000)


async def test_csv_loader_missing_file(tmp_path: Any) -> None:
    loader = CsvLoader(data_dir=str(tmp_path))
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    candles = await loader.load("NONEXISTENT", "1h", start, end)
    assert candles == []


async def test_parquet_loader_basic(tmp_path: Any) -> None:
    """Test ParquetLoader with a real parquet file."""
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        pytest.skip("pyarrow not installed")

    import pyarrow as pa
    import pyarrow.parquet as pq

    # Create test parquet file
    rows = 10
    ts = [1704067200000 + i * 3600000 for i in range(rows)]
    table = pa.table({
        "timestamp": ts,
        "open": [100.0 + i for i in range(rows)],
        "high": [102.0 + i for i in range(rows)],
        "low": [99.0 + i for i in range(rows)],
        "close": [101.0 + i for i in range(rows)],
        "volume": [1000.0] * rows,
    })
    path = tmp_path / "BTC-PERP_1h.parquet"
    pq.write_table(table, path)

    loader = ParquetLoader(data_dir=str(tmp_path))
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    candles = await loader.load("BTC-PERP", "1h", start, end)
    assert len(candles) > 0
    assert all(isinstance(c, Candle) for c in candles)
