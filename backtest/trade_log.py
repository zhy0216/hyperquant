import csv
from dataclasses import dataclass, fields
from datetime import datetime, timezone

from core.events import OrderFilledEvent


@dataclass
class TradeRecord:
    symbol: str
    direction: str
    entry_price: float
    exit_price: float
    size: float
    entry_time: datetime
    exit_time: datetime
    pnl: float
    fee: float
    exit_reason: str


class TradeLog:
    def __init__(self) -> None:
        self._trades: list[TradeRecord] = []
        self.open_entries: dict[str, OrderFilledEvent] = {}

    def record_entry(self, event: OrderFilledEvent) -> None:
        self.open_entries[event.symbol] = event

    def record_exit(self, event: OrderFilledEvent, reason: str) -> None:
        entry = self.open_entries.pop(event.symbol, None)
        if entry is None:
            return
        entry_fee = entry.fee
        exit_fee = event.fee
        total_fee = entry_fee + exit_fee
        if entry.direction == "long":
            raw_pnl = (event.filled_price - entry.filled_price) * entry.filled_size
        else:
            raw_pnl = (entry.filled_price - event.filled_price) * entry.filled_size
        net_pnl = raw_pnl - total_fee

        self._trades.append(TradeRecord(
            symbol=entry.symbol,
            direction=entry.direction,
            entry_price=entry.filled_price,
            exit_price=event.filled_price,
            size=entry.filled_size,
            entry_time=datetime.fromtimestamp(entry.timestamp / 1000, tz=timezone.utc),
            exit_time=datetime.fromtimestamp(event.timestamp / 1000, tz=timezone.utc),
            pnl=round(net_pnl, 2),
            fee=round(total_fee, 2),
            exit_reason=reason,
        ))

    def get_trades(self) -> list[TradeRecord]:
        return list(self._trades)

    def to_csv(self, path: str) -> None:
        field_names = [f.name for f in fields(TradeRecord)]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            for t in self._trades:
                writer.writerow({f: getattr(t, f) for f in field_names})
