from datetime import datetime, timezone, timedelta
from backtest.metrics import compute_metrics
from backtest.trade_log import TradeRecord


def _make_trades(pnls: list[float], duration_hours: int = 24) -> list[TradeRecord]:
    trades = []
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i, pnl in enumerate(pnls):
        entry_time = base + timedelta(days=i)
        exit_time = entry_time + timedelta(hours=duration_hours)
        entry_price = 100.0
        exit_price = entry_price + pnl / 0.1  # size=0.1
        trades.append(TradeRecord(
            symbol="BTC", direction="long",
            entry_price=entry_price, exit_price=exit_price,
            size=0.1, entry_time=entry_time, exit_time=exit_time,
            pnl=pnl, fee=0.5, exit_reason="test",
        ))
    return trades


def _make_equity_curve(returns: list[float], initial: float = 10000.0) -> list[float]:
    curve = [initial]
    for r in returns:
        curve.append(curve[-1] * (1 + r))
    return curve


def test_total_return() -> None:
    curve = [10000.0, 10500.0, 11000.0]
    m = compute_metrics(trades=[], equity_curve=curve, initial_equity=10000)
    assert abs(m["total_return"] - 0.10) < 0.001


def test_win_rate() -> None:
    trades = _make_trades([100, -50, 200, -30, 150])
    m = compute_metrics(trades=trades, equity_curve=[10000, 10370], initial_equity=10000)
    assert abs(m["win_rate"] - 0.60) < 0.01  # 3 wins / 5 trades


def test_profit_factor() -> None:
    trades = _make_trades([100, -50, 200])
    m = compute_metrics(trades=trades, equity_curve=[10000, 10250], initial_equity=10000)
    assert abs(m["profit_factor"] - (300 / 50)) < 0.01


def test_max_drawdown() -> None:
    curve = [10000, 11000, 9000, 9500, 10500]
    m = compute_metrics(trades=[], equity_curve=curve, initial_equity=10000)
    # Peak 11000 -> trough 9000 = -2000 / 11000 = -18.18%
    assert abs(m["max_drawdown_pct"] - 0.1818) < 0.01


def test_max_consecutive_losses() -> None:
    trades = _make_trades([100, -50, -30, -20, 200, -10])
    m = compute_metrics(trades=trades, equity_curve=[10000, 10190], initial_equity=10000)
    assert m["max_consecutive_losses"] == 3


def test_empty_trades() -> None:
    m = compute_metrics(trades=[], equity_curve=[10000], initial_equity=10000)
    assert m["total_trades"] == 0
    assert m["win_rate"] == 0
    assert m["profit_factor"] == 0
