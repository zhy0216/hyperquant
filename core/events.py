from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: int


@dataclass
class MarketDataEvent:
    symbol: str
    timeframe: str
    candles: list[Candle]
    timestamp: int


@dataclass
class SignalEvent:
    symbol: str
    direction: str        # "long" | "short"
    score: float
    entry_price: float
    atr: float
    stop_loss: float
    take_profit: float
    timestamp: int


@dataclass
class OrderRequestEvent:
    symbol: str
    direction: str        # "long" | "short"
    action: str           # "open" | "close"
    size: float
    order_type: str       # "market" | "limit"
    limit_price: Optional[float]
    stop_loss: float
    take_profit: float
    reason: str
    timestamp: int


@dataclass
class OrderFilledEvent:
    symbol: str
    direction: str        # "long" | "short"
    action: str           # "open" | "close"
    filled_size: float
    filled_price: float
    order_id: str
    fee: float
    timestamp: int


@dataclass
class PortfolioUpdateEvent:
    symbol: str
    unrealized_pnl: float
    current_price: float
    stop_loss: float
    take_profit: float
    timestamp: int


@dataclass
class CloseSignalEvent:
    symbol: str
    reason: str           # e.g. "trailing_stop", "take_profit", "exit_score"
    close_price: float
    timestamp: int
