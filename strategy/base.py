from abc import ABC, abstractmethod

from core.event_bus import EventBus
from core.events import MarketDataEvent, OrderFilledEvent


class Strategy(ABC):
    @abstractmethod
    def __init__(self, bus: EventBus, config: dict, **kwargs) -> None: ...

    @abstractmethod
    async def on_market_data(self, event: MarketDataEvent) -> None:
        """Receive candle data. Publish SignalEvent or CloseSignalEvent as needed."""

    async def on_order_filled(self, event: OrderFilledEvent) -> None:
        """Optional: receive fill notifications to update internal state."""
        pass

    def clear_cycle_cooldowns(self) -> None:
        """Optional: called at the start of each evaluation cycle."""
        pass
