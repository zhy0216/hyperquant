import logging
from core.event_bus import EventBus
from core.events import OrderRequestEvent, OrderFilledEvent

logger = logging.getLogger(__name__)


class OrderExecutor:
    def __init__(self, bus: EventBus, client, config: dict) -> None:
        self._bus = bus
        self._client = client
        self._config = config["exchange"]
        bus.subscribe(OrderRequestEvent, self.on_order_request)

    async def on_order_request(self, req: OrderRequestEvent) -> None:
        try:
            if req.order_type == "market" or req.action == "close":
                await self._execute_market(req)
            else:
                await self._execute_limit(req)
        except Exception:
            logger.exception("Order execution failed for %s", req.symbol)

    async def _execute_limit(self, req: OrderRequestEvent) -> None:
        slippage = self._config["slippage_tolerance"]
        limit_price = req.limit_price * (1 + slippage) if req.direction == "long" else req.limit_price * (1 - slippage)
        result = await self._client.place_limit_order(req.symbol, req.direction, req.size, limit_price)
        filled_size = result["filled_size"]
        if filled_size > 0:
            fill = OrderFilledEvent(
                symbol=req.symbol, direction=req.direction, action=req.action,
                filled_size=filled_size, filled_price=result["filled_price"],
                order_id=result["order_id"], fee=result["fee"], timestamp=req.timestamp,
            )
            await self._bus.publish(fill)
        if result["status"] == "partial":
            remaining = req.size - filled_size
            await self._client.cancel_order(result["order_id"])
            if remaining > 0:
                market_result = await self._client.place_market_order(req.symbol, req.direction, remaining)
                fill2 = OrderFilledEvent(
                    symbol=req.symbol, direction=req.direction, action=req.action,
                    filled_size=market_result["filled_size"], filled_price=market_result["filled_price"],
                    order_id=market_result["order_id"], fee=market_result["fee"], timestamp=req.timestamp,
                )
                await self._bus.publish(fill2)
        if req.action == "open" and filled_size > 0:
            await self._client.set_tp_sl(req.symbol, req.stop_loss, req.take_profit)

    async def _execute_market(self, req: OrderRequestEvent) -> None:
        result = await self._client.place_market_order(req.symbol, req.direction, req.size)
        fill = OrderFilledEvent(
            symbol=req.symbol, direction=req.direction, action=req.action,
            filled_size=result["filled_size"], filled_price=result["filled_price"],
            order_id=result["order_id"], fee=result["fee"], timestamp=req.timestamp,
        )
        await self._bus.publish(fill)
        if req.action == "open":
            await self._client.set_tp_sl(req.symbol, req.stop_loss, req.take_profit)
