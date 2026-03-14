import time
from data.symbol_filter import filter_symbols


def test_filters_by_volume():
    tickers = [
        {"symbol": "BTC", "volume_24h": 5_000_000, "listing_time": 0},
        {"symbol": "SHIB", "volume_24h": 500_000, "listing_time": 0},
        {"symbol": "ETH", "volume_24h": 3_000_000, "listing_time": 0},
    ]
    result = filter_symbols(tickers, min_volume=1_000_000, min_listing_days=0)
    symbols = [t["symbol"] for t in result]
    assert "BTC" in symbols
    assert "ETH" in symbols
    assert "SHIB" not in symbols


def test_filters_by_listing_age():
    now = time.time()
    tickers = [
        {"symbol": "BTC", "volume_24h": 5_000_000, "listing_time": now - 30 * 86400},
        {"symbol": "NEW", "volume_24h": 5_000_000, "listing_time": now - 3 * 86400},
    ]
    result = filter_symbols(tickers, min_volume=1_000_000, min_listing_days=7)
    symbols = [t["symbol"] for t in result]
    assert "BTC" in symbols
    assert "NEW" not in symbols


def test_empty_input_returns_empty():
    assert filter_symbols([], min_volume=1_000_000, min_listing_days=7) == []
