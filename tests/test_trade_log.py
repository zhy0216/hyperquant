import os
import pytest
from core.events import OrderFilledEvent
from backtest.trade_log import TradeLog, TradeRecord


def _make_entry_fill(symbol="BTC", direction="long", price=50000.0, size=0.1, fee=1.75, ts=1000):
    return OrderFilledEvent(
        symbol=symbol, direction=direction, action="open",
        filled_size=size, filled_price=price, order_id="o1", fee=fee, timestamp=ts,
    )


def _make_exit_fill(symbol="BTC", direction="long", price=52000.0, size=0.1, fee=1.82, ts=2000):
    return OrderFilledEvent(
        symbol=symbol, direction=direction, action="close",
        filled_size=size, filled_price=price, order_id="o2", fee=fee, timestamp=ts,
    )


def test_record_entry_and_exit():
    log = TradeLog()
    log.record_entry(_make_entry_fill())
    log.record_exit(_make_exit_fill(), reason="take_profit")

    trades = log.get_trades()
    assert len(trades) == 1
    t = trades[0]
    assert t.symbol == "BTC"
    assert t.direction == "long"
    assert t.entry_price == 50000.0
    assert t.exit_price == 52000.0
    assert t.exit_reason == "take_profit"
    # PnL: (52000 - 50000) * 0.1 - 1.75 - 1.82 = 200 - 3.57 = 196.43
    assert abs(t.pnl - 196.43) < 0.01
    assert abs(t.fee - 3.57) < 0.01


def test_short_trade_pnl():
    log = TradeLog()
    log.record_entry(_make_entry_fill(direction="short", price=50000.0))
    log.record_exit(_make_exit_fill(direction="short", price=48000.0), reason="stop_loss")

    t = log.get_trades()[0]
    # PnL: (50000 - 48000) * 0.1 - fees = 200 - 3.57 = 196.43
    assert abs(t.pnl - 196.43) < 0.01


def test_open_entries_not_in_trades():
    log = TradeLog()
    log.record_entry(_make_entry_fill())
    assert len(log.get_trades()) == 0
    assert len(log.open_entries) == 1


def test_to_csv(tmp_path):
    log = TradeLog()
    log.record_entry(_make_entry_fill())
    log.record_exit(_make_exit_fill(), reason="trailing_stop")

    path = str(tmp_path / "trades.csv")
    log.to_csv(path)
    assert os.path.exists(path)

    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 2  # header + 1 trade
    assert "BTC" in lines[1]
    assert "trailing_stop" in lines[1]
