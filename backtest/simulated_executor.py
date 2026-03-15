import logging

from core.event_bus import EventBus
from core.events import OrderFilledEvent, OrderRequestEvent

logger = logging.getLogger(__name__)


class SimulatedExecutor:
    def __init__(
        self, bus: EventBus, current_prices: dict[str, float],
        slippage: float = 0.001, fee_rate: float = 0.00035,
    ) -> None:
        self._bus = bus
        self._current_prices = current_prices
        self._slippage = slippage
        self._fee_rate = fee_rate
        self._order_counter = 0
        bus.subscribe(OrderRequestEvent, self._on_order_request)

    async def _on_order_request(self, req: OrderRequestEvent) -> None:
        price = self._current_prices.get(req.symbol)
        if price is None:
            logger.warning("No price available for %s, skipping order", req.symbol)
            return

        is_buy = (
            (req.direction == "long" and req.action == "open")
            or (req.direction == "short" and req.action == "close")
        )

        if is_buy:
            fill_price = price * (1 + self._slippage)
        else:
            fill_price = price * (1 - self._slippage)

        fee = fill_price * req.size * self._fee_rate
        self._order_counter += 1

        fill = OrderFilledEvent(
            symbol=req.symbol,
            direction=req.direction,
            action=req.action,
            filled_size=req.size,
            filled_price=fill_price,
            order_id=f"sim-{self._order_counter}",
            fee=fee,
            timestamp=req.timestamp,
        )
        await self._bus.publish(fill)
