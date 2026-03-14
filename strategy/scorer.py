import numpy as np

from strategy.indicators import compute_donchian, compute_ema, compute_macd, compute_rsi

# Weights per spec Section 3
WEIGHT_TREND = 0.40
WEIGHT_MOMENTUM = 0.35
WEIGHT_BREAKOUT = 0.25


def compute_trend_score(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    ema_fast: int = 20,
    ema_slow: int = 60,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    donchian_period: int = 20,
) -> tuple[float, str]:
    """Return (score 0-100, direction 'long'|'short')."""
    ema_f = compute_ema(closes, ema_fast)
    ema_s = compute_ema(closes, ema_slow)
    rsi = compute_rsi(closes, rsi_period)
    macd_line, signal_line, histogram = compute_macd(closes, macd_fast, macd_slow, macd_signal)
    don_upper, don_lower = compute_donchian(highs, lows, donchian_period)

    # Use last valid values
    ef = ema_f[-1]
    es = ema_s[-1]
    if np.isnan(ef) or np.isnan(es):
        return 0.0, "long"

    # Determine direction from EMA cross
    is_long = ef > es

    # --- Trend direction score (0-100) ---
    ema_gap = abs(ef - es) / es * 100  # gap as percentage
    # Check if gap is expanding (compare to 5 bars ago)
    prev_gap = abs(ema_f[-5] - ema_s[-5]) / ema_s[-5] * 100 if not np.isnan(ema_f[-5]) else 0
    expanding = ema_gap > prev_gap
    trend_score = min(ema_gap * 20, 100)  # Scale: 5% gap = 100
    if expanding:
        trend_score = min(trend_score * 1.2, 100)

    # --- Momentum score (0-100) ---
    rsi_val = rsi[-1] if not np.isnan(rsi[-1]) else 50
    hist_val = histogram[-1] if not np.isnan(histogram[-1]) else 0

    if is_long:
        # RSI 50-70 is ideal for long momentum
        if 50 <= rsi_val <= 70:
            rsi_score = 100 - abs(rsi_val - 60) * 5
        elif rsi_val > 70:
            rsi_score = max(100 - (rsi_val - 70) * 5, 20)
        else:
            rsi_score = max(rsi_val * 2 - 20, 0)
        hist_score = min(max(hist_val / (abs(closes[-1]) * 0.001 + 1e-10) * 10, 0), 100)
    else:
        # RSI 30-50 is ideal for short momentum
        if 30 <= rsi_val <= 50:
            rsi_score = 100 - abs(rsi_val - 40) * 5
        elif rsi_val < 30:
            rsi_score = max(100 - (30 - rsi_val) * 5, 20)
        else:
            rsi_score = max((100 - rsi_val) * 2 - 20, 0)
        hist_score = min(max(-hist_val / (abs(closes[-1]) * 0.001 + 1e-10) * 10, 0), 100)

    momentum_score = (rsi_score + hist_score) / 2

    # --- Breakout score (0-100) ---
    du = don_upper[-1] if not np.isnan(don_upper[-1]) else closes[-1]
    dl = don_lower[-1] if not np.isnan(don_lower[-1]) else closes[-1]
    if is_long:
        channel_range = du - dl + 1e-10
        breakout_score = (
            100 if closes[-1] >= du
            else max((1 - (du - closes[-1]) / channel_range) * 100, 0)
        )
    else:
        channel_range = du - dl + 1e-10
        breakout_score = (
            100 if closes[-1] <= dl
            else max((1 - (closes[-1] - dl) / channel_range) * 100, 0)
        )

    # Weighted total
    total = (
        trend_score * WEIGHT_TREND
        + momentum_score * WEIGHT_MOMENTUM
        + breakout_score * WEIGHT_BREAKOUT
    )
    total = max(0, min(100, total))
    direction = "long" if is_long else "short"
    return round(total, 2), direction
