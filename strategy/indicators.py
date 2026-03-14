import numpy as np


def compute_ema(prices: list[float], period: int) -> list[float]:
    result = [float("nan")] * len(prices)
    if len(prices) < period:
        return result
    # SMA for initial value
    result[period - 1] = sum(prices[:period]) / period
    multiplier = 2.0 / (period + 1)
    for i in range(period, len(prices)):
        result[i] = (prices[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def compute_rsi(prices: list[float], period: int = 14) -> list[float]:
    result = [float("nan")] * len(prices)
    if len(prices) < period + 1:
        return result
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(prices)):
        idx = i - 1  # delta index
        avg_gain = (avg_gain * (period - 1) + gains[idx]) / period
        avg_loss = (avg_loss * (period - 1) + losses[idx]) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))
    return result


def compute_macd(
    prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float], list[float], list[float]]:
    ema_fast = compute_ema(prices, fast)
    ema_slow = compute_ema(prices, slow)
    macd_line = [
        f - s if not (np.isnan(f) or np.isnan(s)) else float("nan")
        for f, s in zip(ema_fast, ema_slow, strict=True)
    ]
    # Compute signal line from valid MACD values only
    valid_start = slow - 1  # first valid MACD index
    macd_valid = [macd_line[i] for i in range(valid_start, len(macd_line))]
    signal_computed = compute_ema(macd_valid, signal)
    signal_line = [float("nan")] * valid_start + signal_computed

    histogram = [
        m - s if not (np.isnan(m) or np.isnan(s)) else float("nan")
        for m, s in zip(macd_line, signal_line, strict=True)
    ]
    return macd_line, signal_line, histogram


def compute_donchian(
    highs: list[float], lows: list[float], period: int = 20
) -> tuple[list[float], list[float]]:
    upper = [float("nan")] * len(highs)
    lower = [float("nan")] * len(lows)
    for i in range(period - 1, len(highs)):
        upper[i] = max(highs[i - period + 1 : i + 1])
        lower[i] = min(lows[i - period + 1 : i + 1])
    return upper, lower


def compute_atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[float]:
    result = [float("nan")] * len(closes)
    if len(closes) < 2:
        return result
    true_ranges = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return result
    result[period - 1] = sum(true_ranges[:period]) / period
    for i in range(period, len(true_ranges)):
        result[i] = (result[i - 1] * (period - 1) + true_ranges[i]) / period
    return result
