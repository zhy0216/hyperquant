import logging
import time

import numpy as np

from core.event_bus import EventBus
from core.events import Candle, CloseSignalEvent, MarketDataEvent, OrderFilledEvent, SignalEvent
from strategy.base import Strategy
from strategy.indicators import compute_atr
from strategy.scorer import compute_trend_score

logger = logging.getLogger(__name__)


class SignalEngine(Strategy):
    def __init__(self, bus: EventBus, config: dict) -> None:
        self._bus = bus
        self._config = config
        self._strat = config["strategy"]
        self._sl_cfg = config["stop_loss"]
        # Cache latest candles per symbol per timeframe
        self._candle_cache: dict[str, dict[str, list[Candle]]] = {}
        # Track open positions to handle reversal signals
        self._open_positions: set[str] = set()
        self._position_directions: dict[str, str] = {}
        self._recently_closed: set[str] = set()  # Prevents re-entry in same cycle

        bus.subscribe(MarketDataEvent, self.on_market_data)
        bus.subscribe(OrderFilledEvent, self.on_order_filled)
        bus.subscribe(CloseSignalEvent, self._on_close_signal)

    async def on_market_data(self, event: MarketDataEvent) -> None:
        symbol = event.symbol
        tf = event.timeframe
        self._candle_cache.setdefault(symbol, {})[tf] = event.candles

        # Only evaluate signals on primary timeframe
        if tf != self._strat["primary_timeframe"]:
            return

        await self._evaluate_symbol(symbol)

    async def _evaluate_symbol(self, symbol: str) -> None:
        primary_tf = self._strat["primary_timeframe"]
        confirm_tf = self._strat["confirm_timeframe"]

        candles_1h = self._candle_cache.get(symbol, {}).get(primary_tf)
        candles_4h = self._candle_cache.get(symbol, {}).get(confirm_tf)
        if not candles_1h or len(candles_1h) < self._strat["ema_slow"]:
            return

        closes = [c.close for c in candles_1h]
        highs = [c.high for c in candles_1h]
        lows = [c.low for c in candles_1h]
        opens = [c.open for c in candles_1h]

        score, direction = compute_trend_score(
            opens, highs, lows, closes,
            ema_fast=self._strat["ema_fast"],
            ema_slow=self._strat["ema_slow"],
            rsi_period=self._strat["rsi_period"],
            macd_fast=self._strat["macd_fast"],
            macd_slow=self._strat["macd_slow"],
            macd_signal=self._strat["macd_signal"],
            donchian_period=self._strat["donchian_period"],
        )

        # 4h confirmation filter
        if candles_4h and len(candles_4h) >= self._strat["ema_slow"]:
            closes_4h = [c.close for c in candles_4h]
            highs_4h = [c.high for c in candles_4h]
            lows_4h = [c.low for c in candles_4h]
            opens_4h = [c.open for c in candles_4h]
            _, dir_4h = compute_trend_score(
                opens_4h, highs_4h, lows_4h, closes_4h,
                ema_fast=self._strat["ema_fast"],
                ema_slow=self._strat["ema_slow"],
                rsi_period=self._strat["rsi_period"],
                macd_fast=self._strat["macd_fast"],
                macd_slow=self._strat["macd_slow"],
                macd_signal=self._strat["macd_signal"],
                donchian_period=self._strat["donchian_period"],
            )
            if dir_4h != direction:
                return  # 4h disagrees, skip

        # Check for trend reversal on existing positions
        if symbol in self._open_positions:
            pos_dir = self._position_directions.get(symbol)
            if pos_dir and pos_dir != direction:
                await self._bus.publish(CloseSignalEvent(
                    symbol=symbol, reason="trend_reversal",
                    close_price=closes[-1], timestamp=int(time.time() * 1000),
                ))
                return
            if score < self._strat["exit_score_threshold"]:
                await self._bus.publish(CloseSignalEvent(
                    symbol=symbol, reason="trend_reversal",
                    close_price=closes[-1], timestamp=int(time.time() * 1000),
                ))
                return
            return  # Already has position in same direction, skip

        # Entry signal — skip if recently closed (same-cycle reversal prevention per spec)
        if symbol in self._recently_closed:
            return
        if score < self._strat["score_threshold"]:
            return

        atr_values = compute_atr(highs, lows, closes, self._strat["atr_period"])
        atr = atr_values[-1]
        if np.isnan(atr) or atr <= 0:
            return

        entry_price = closes[-1]
        atr_sl = self._sl_cfg["initial_atr_multiple"]
        atr_tp = self._sl_cfg["take_profit_atr_multiple"]

        if direction == "long":
            stop_loss = entry_price - atr_sl * atr
            take_profit = entry_price + atr_tp * atr
        else:
            stop_loss = entry_price + atr_sl * atr
            take_profit = entry_price - atr_tp * atr

        signal = SignalEvent(
            symbol=symbol, direction=direction, score=score,
            entry_price=entry_price, atr=atr,
            stop_loss=stop_loss, take_profit=take_profit,
            timestamp=int(time.time() * 1000),
        )
        logger.info("Signal: %s %s score=%.1f", symbol, direction, score)
        await self._bus.publish(signal)

    async def on_order_filled(self, event: OrderFilledEvent) -> None:
        if event.action == "open":
            self._open_positions.add(event.symbol)
            self._position_directions[event.symbol] = event.direction
        elif event.action == "close":
            self._open_positions.discard(event.symbol)
            self._position_directions.pop(event.symbol, None)

    async def _on_close_signal(self, event: CloseSignalEvent) -> None:
        self._open_positions.discard(event.symbol)
        self._position_directions.pop(event.symbol, None)
        self._recently_closed.add(event.symbol)  # Block re-entry this cycle

    def clear_cycle_cooldowns(self) -> None:
        """Call at the start of each new signal evaluation cycle."""
        self._recently_closed.clear()
