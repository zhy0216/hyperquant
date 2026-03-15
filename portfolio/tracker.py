import logging
import time
from collections.abc import Callable

from core.event_bus import EventBus
from core.events import CloseSignalEvent, OrderFilledEvent

logger = logging.getLogger(__name__)

class PortfolioTracker:
    def __init__(self, bus: EventBus, config: dict, time_fn: Callable[[], float] | None = None) -> None:
        self._bus = bus
        self._sl_cfg = config["stop_loss"]
        self._time_fn = time_fn or time.time
        self.positions: dict[str, dict] = {}
        bus.subscribe(OrderFilledEvent, self.on_order_filled)

    async def on_order_filled(self, event: OrderFilledEvent) -> None:
        if event.action == "open":
            # Initialize with safe stop/TP values until ATR is set via set_atr().
            # Use extreme values that won't trigger false exits.
            self.positions[event.symbol] = {
                "direction": event.direction, "size": event.filled_size,
                "entry_price": event.filled_price, "atr": 0,
                "stop_loss": 0 if event.direction == "long" else float("inf"),
                "take_profit": float("inf") if event.direction == "long" else 0,
                "highest_price": event.filled_price, "lowest_price": event.filled_price,
                "timestamp": event.timestamp,
            }
        elif event.action == "close":
            self.positions.pop(event.symbol, None)

    def set_atr(self, symbol: str, atr: float) -> None:
        if symbol in self.positions:
            pos = self.positions[symbol]
            pos["atr"] = atr
            atr_sl = self._sl_cfg["initial_atr_multiple"]
            atr_tp = self._sl_cfg["take_profit_atr_multiple"]
            if pos["direction"] == "long":
                pos["stop_loss"] = pos["entry_price"] - atr_sl * atr
                pos["take_profit"] = pos["entry_price"] + atr_tp * atr
            else:
                pos["stop_loss"] = pos["entry_price"] + atr_sl * atr
                pos["take_profit"] = pos["entry_price"] - atr_tp * atr

    def update_price(self, symbol: str, current_price: float) -> None:
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        atr = pos["atr"]
        if atr <= 0:
            return
        entry = pos["entry_price"]
        direction = pos["direction"]
        if direction == "long":
            pos["highest_price"] = max(pos["highest_price"], current_price)
            profit = current_price - entry
        else:
            pos["lowest_price"] = min(pos["lowest_price"], current_price)
            profit = entry - current_price
        be_trigger = self._sl_cfg["breakeven_trigger_atr"] * atr
        trail_trigger = self._sl_cfg["trailing_trigger_atr"] * atr
        trail_dist = self._sl_cfg["trailing_distance_atr"] * atr
        if profit >= trail_trigger:
            if direction == "long":
                new_sl = pos["highest_price"] - trail_dist
                pos["stop_loss"] = max(pos["stop_loss"], new_sl)
            else:
                new_sl = pos["lowest_price"] + trail_dist
                pos["stop_loss"] = min(pos["stop_loss"], new_sl)
        elif profit >= be_trigger:
            if direction == "long":
                pos["stop_loss"] = max(pos["stop_loss"], entry)
            else:
                pos["stop_loss"] = min(pos["stop_loss"], entry)
        # Stage 1 (profit < breakeven trigger): no stop-loss movement

    async def check_exits(self, symbol: str, current_price: float) -> None:
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        direction = pos["direction"]
        hit_sl = ((direction == "long" and current_price <= pos["stop_loss"])
                  or (direction == "short" and current_price >= pos["stop_loss"]))
        hit_tp = ((direction == "long" and current_price >= pos["take_profit"])
                  or (direction == "short" and current_price <= pos["take_profit"]))
        if hit_sl:
            reason = "trailing_stop" if pos["stop_loss"] != (
                pos["entry_price"] - self._sl_cfg["initial_atr_multiple"] * pos["atr"]
                if direction == "long"
                else pos["entry_price"] + self._sl_cfg["initial_atr_multiple"] * pos["atr"]
            ) else "stop_loss"
            await self._bus.publish(CloseSignalEvent(
                symbol=symbol, reason=reason,
                close_price=current_price, timestamp=int(self._time_fn() * 1000),
            ))
        elif hit_tp:
            await self._bus.publish(CloseSignalEvent(
                symbol=symbol, reason="take_profit",
                close_price=current_price, timestamp=int(self._time_fn() * 1000),
            ))
