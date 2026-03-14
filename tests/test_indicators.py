import numpy as np
import pytest
from strategy.indicators import compute_ema, compute_rsi, compute_macd, compute_donchian, compute_atr


def _make_prices(n=100, start=100.0, trend=0.5, noise=2.0):
    """Generate synthetic price series with upward trend + noise."""
    np.random.seed(42)
    return [start + i * trend + np.random.randn() * noise for i in range(n)]


def _make_ohlcv(closes, spread=2.0):
    """Generate OHLCV lists from close prices."""
    highs = [c + abs(spread * np.random.randn()) for c in closes]
    lows = [c - abs(spread * np.random.randn()) for c in closes]
    opens = [closes[0]] + closes[:-1]
    volumes = [1000.0] * len(closes)
    return opens, highs, lows, closes, volumes


class TestEMA:
    def test_ema_length_matches_input(self):
        prices = _make_prices(50)
        result = compute_ema(prices, period=20)
        assert len(result) == len(prices)

    def test_ema_first_values_are_nan(self):
        prices = _make_prices(50)
        result = compute_ema(prices, period=20)
        assert np.isnan(result[0])

    def test_ema_tracks_uptrend(self):
        prices = _make_prices(100, trend=1.0, noise=0.1)
        result = compute_ema(prices, period=20)
        # EMA should be below price in uptrend (lagging)
        assert result[-1] < prices[-1]


class TestRSI:
    def test_rsi_range(self):
        prices = _make_prices(100)
        result = compute_rsi(prices, period=14)
        valid = [v for v in result if not np.isnan(v)]
        assert all(0 <= v <= 100 for v in valid)

    def test_rsi_uptrend_above_50(self):
        prices = _make_prices(100, trend=2.0, noise=0.1)
        result = compute_rsi(prices, period=14)
        assert result[-1] > 50


class TestMACD:
    def test_macd_returns_three_series(self):
        prices = _make_prices(100)
        macd_line, signal_line, histogram = compute_macd(prices, fast=12, slow=26, signal=9)
        assert len(macd_line) == len(prices)
        assert len(signal_line) == len(prices)
        assert len(histogram) == len(prices)

    def test_histogram_is_macd_minus_signal(self):
        prices = _make_prices(100)
        macd_line, signal_line, histogram = compute_macd(prices, fast=12, slow=26, signal=9)
        # Check last value where both are valid
        idx = -1
        if not np.isnan(macd_line[idx]) and not np.isnan(signal_line[idx]):
            assert abs(histogram[idx] - (macd_line[idx] - signal_line[idx])) < 1e-10


class TestDonchian:
    def test_donchian_channel(self):
        np.random.seed(42)
        highs = [100 + i + abs(np.random.randn()) for i in range(30)]
        lows = [100 + i - abs(np.random.randn()) for i in range(30)]
        upper, lower = compute_donchian(highs, lows, period=20)
        assert len(upper) == 30
        # Upper channel should be >= last high in the window
        assert upper[-1] >= max(highs[-20:]) - 1e-10


class TestATR:
    def test_atr_positive(self):
        np.random.seed(42)
        closes = _make_prices(50)
        opens, highs, lows, closes, _ = _make_ohlcv(closes)
        result = compute_atr(highs, lows, closes, period=14)
        valid = [v for v in result if not np.isnan(v)]
        assert all(v > 0 for v in valid)
