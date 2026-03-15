import math
from datetime import timedelta
from typing import Any

import numpy as np

from backtest.trade_log import TradeRecord


def compute_metrics(
    trades: list[TradeRecord],
    equity_curve: list[float],
    initial_equity: float,
) -> dict[str, Any]:
    total_trades = len(trades)
    if not equity_curve:
        equity_curve = [initial_equity]

    # Return
    final_equity = equity_curve[-1]
    total_return = (final_equity / initial_equity) - 1 if initial_equity > 0 else 0

    # Annualized return
    if len(equity_curve) > 1:
        n_hours = len(equity_curve)  # Approximate: 1 data point per bar (1h)
        years = n_hours / (365.25 * 24)
        if years > 0 and final_equity / initial_equity > 0:
            annualized_return = (final_equity / initial_equity) ** (1 / years) - 1
        else:
            annualized_return = 0.0
    else:
        annualized_return = 0.0

    # Sharpe & Sortino (from equity curve returns)
    if len(equity_curve) > 2:
        returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns, ddof=1))
        sharpe = (mean_ret / std_ret * math.sqrt(len(returns))) if std_ret > 0 else 0

        downside = returns[returns < 0]
        downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0
        sortino = (mean_ret / downside_std * math.sqrt(len(returns))) if downside_std > 0 else 0
    else:
        sharpe = 0.0
        sortino = 0.0

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        dd_pct = dd / peak if peak > 0 else 0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd = dd

    # Win rate, profit factor
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / total_trades if total_trades > 0 else 0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Avg duration
    if total_trades > 0:
        durations = [(t.exit_time - t.entry_time) for t in trades]
        avg_duration = sum(durations, timedelta()) / total_trades
    else:
        avg_duration = timedelta()

    # Max consecutive losses
    max_consec = 0
    current_consec = 0
    for t in trades:
        if t.pnl <= 0:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0

    return {
        "total_return": round(total_return, 4),
        "annualized_return": round(annualized_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_trade_duration": str(avg_duration),
        "max_consecutive_losses": max_consec,
        "total_trades": total_trades,
    }
