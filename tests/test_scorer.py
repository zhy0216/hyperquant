import numpy as np
import pytest
from strategy.scorer import compute_trend_score


def _uptrend_candles(n=100, start=100.0, step=1.0):
    """Generate strongly trending-up OHLCV data."""
    closes = [start + i * step for i in range(n)]
    highs = [c + 2 for c in closes]
    lows = [c - 1 for c in closes]
    opens = [closes[0]] + closes[:-1]
    volumes = [1000.0] * n
    return opens, highs, lows, closes, volumes


def _downtrend_candles(n=100, start=200.0, step=1.0):
    closes = [start - i * step for i in range(n)]
    highs = [c + 1 for c in closes]
    lows = [c - 2 for c in closes]
    opens = [closes[0]] + closes[:-1]
    volumes = [1000.0] * n
    return opens, highs, lows, closes, volumes


def _flat_candles(n=100, price=100.0):
    np.random.seed(42)
    closes = [price + np.random.randn() * 0.1 for _ in range(n)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    opens = closes[:]
    volumes = [1000.0] * n
    return opens, highs, lows, closes, volumes


class TestTrendScore:
    def test_strong_uptrend_high_score(self):
        opens, highs, lows, closes, volumes = _uptrend_candles()
        score, direction = compute_trend_score(
            opens, highs, lows, closes,
            ema_fast=20, ema_slow=60, rsi_period=14,
            macd_fast=12, macd_slow=26, macd_signal=9,
            donchian_period=20,
        )
        assert score > 60
        assert direction == "long"

    def test_strong_downtrend_high_score_short(self):
        opens, highs, lows, closes, volumes = _downtrend_candles()
        score, direction = compute_trend_score(
            opens, highs, lows, closes,
            ema_fast=20, ema_slow=60, rsi_period=14,
            macd_fast=12, macd_slow=26, macd_signal=9,
            donchian_period=20,
        )
        assert score > 60
        assert direction == "short"

    def test_flat_market_low_score(self):
        opens, highs, lows, closes, volumes = _flat_candles()
        score, direction = compute_trend_score(
            opens, highs, lows, closes,
            ema_fast=20, ema_slow=60, rsi_period=14,
            macd_fast=12, macd_slow=26, macd_signal=9,
            donchian_period=20,
        )
        assert score < 50

    def test_score_bounded_0_100(self):
        for factory in [_uptrend_candles, _downtrend_candles, _flat_candles]:
            opens, highs, lows, closes, volumes = factory()
            score, _ = compute_trend_score(
                opens, highs, lows, closes,
                ema_fast=20, ema_slow=60, rsi_period=14,
                macd_fast=12, macd_slow=26, macd_signal=9,
                donchian_period=20,
            )
            assert 0 <= score <= 100
