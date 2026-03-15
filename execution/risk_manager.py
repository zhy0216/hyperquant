import logging
import time
from collections.abc import Callable

from core.event_bus import EventBus
from core.events import OrderFilledEvent, OrderRequestEvent, SignalEvent
from execution.position_sizer import calculate_position_size

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, bus: EventBus, config: dict, equity: float, time_fn: Callable[[], float] | None = None) -> None:
        self._bus = bus
        self._risk = config["risk"]
        self._sl_cfg = config["stop_loss"]
        self._equity = equity
        self._time_fn = time_fn or time.time
        self._open_positions: dict[str, dict] = {}
        self._daily_loss: float = 0.0
        self._daily_reset_ts: float = 0.0
        self._consecutive_losses: int = 0
        self._cooldown_until: float = 0.0
        bus.subscribe(SignalEvent, self.on_signal)
        bus.subscribe(OrderFilledEvent, self._on_fill)

    def update_equity(self, equity: float) -> None:
        self._equity = equity

    async def on_signal(self, signal: SignalEvent) -> None:
        now = self._time_fn()
        if self._consecutive_losses >= self._risk["consecutive_loss_limit"]:
            if now < self._cooldown_until:
                logger.warning("Risk: in cooldown, rejecting %s", signal.symbol)
                return
            else:
                self._consecutive_losses = 0
        if self._daily_loss >= self._equity * self._risk["max_daily_loss"]:
            logger.warning("Risk: daily loss limit hit, rejecting %s", signal.symbol)
            return
        if len(self._open_positions) >= self._risk["max_open_positions"]:
            logger.warning("Risk: max positions reached, rejecting %s", signal.symbol)
            return
        if signal.symbol in self._open_positions:
            logger.warning("Risk: already have position in %s", signal.symbol)
            return
        pos = calculate_position_size(
            equity=self._equity, atr=signal.atr, entry_price=signal.entry_price,
            risk_per_trade=self._risk["risk_per_trade"],
            sl_atr_multiple=self._sl_cfg["initial_atr_multiple"],
            max_single_exposure=self._risk["max_single_exposure"],
            max_leverage=self._risk["max_leverage"],
        )
        if pos["size"] <= 0:
            return
        current_exposure = sum(p["notional"] for p in self._open_positions.values())
        max_total = self._equity * self._risk["max_total_exposure"]
        if current_exposure + pos["notional"] > max_total:
            available = max_total - current_exposure
            if available <= 0:
                logger.warning("Risk: total exposure limit, rejecting %s", signal.symbol)
                return
            pos["notional"] = available
            pos["size"] = available / signal.entry_price
        order = OrderRequestEvent(
            symbol=signal.symbol, direction=signal.direction, action="open",
            size=pos["size"], order_type="limit", limit_price=signal.entry_price,
            stop_loss=signal.stop_loss, take_profit=signal.take_profit,
            reason=f"trend score {signal.score:.1f}", timestamp=int(self._time_fn() * 1000),
        )
        logger.info("Risk approved: %s %s size=%.6f", signal.symbol, signal.direction, pos["size"])
        await self._bus.publish(order)

    async def _on_fill(self, event: OrderFilledEvent) -> None:
        if event.action == "open":
            self._open_positions[event.symbol] = {
                "notional": event.filled_size * event.filled_price, "direction": event.direction,
            }
        elif event.action == "close":
            self._open_positions.pop(event.symbol, None)

    def record_loss(self, amount: float) -> None:
        self._daily_loss += amount
        self._consecutive_losses += 1
        if self._consecutive_losses >= self._risk["consecutive_loss_limit"]:
            self._cooldown_until = self._time_fn() + self._risk["cooldown_hours"] * 3600

    def record_win(self) -> None:
        self._consecutive_losses = 0

    def reset_daily_loss(self) -> None:
        self._daily_loss = 0.0
