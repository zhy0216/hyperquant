import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from backtest.data_loader import DataLoader
from backtest.simulated_executor import SimulatedExecutor
from backtest.trade_log import TradeLog
from core.event_bus import EventBus
from core.events import (
    Candle,
    CloseSignalEvent,
    MarketDataEvent,
    OrderFilledEvent,
    OrderRequestEvent,
    SignalEvent,
)
from execution.risk_manager import RiskManager
from portfolio.tracker import PortfolioTracker
from strategy.base import Strategy

logger = logging.getLogger(__name__)


@dataclass
class BacktestResult:
    trade_log: TradeLog
    equity_curve: list[float] = field(default_factory=list)
    timestamps: list[int] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)


class BacktestEngine:
    def __init__(
        self,
        config: dict[str, Any],
        strategy_cls: type[Strategy],
        loader: DataLoader,
        symbols: list[str],
        start: datetime,
        end: datetime,
    ) -> None:
        self._config = config
        self._strategy_cls = strategy_cls
        self._loader = loader
        self._symbols = symbols
        self._start = start
        self._end = end

        bt_cfg = config.get("backtest", {})
        self._initial_equity: float = bt_cfg.get("initial_equity", 10000)
        self._slippage: float = bt_cfg.get("slippage", 0.001)
        self._fee_rate: float = bt_cfg.get("fee_rate", 0.00035)

    async def run(self) -> BacktestResult:
        bus = EventBus()
        current_prices: dict[str, float] = {}
        trade_log = TradeLog()

        # Current simulated time
        current_ts = 0

        def time_fn() -> float:
            return current_ts / 1000.0

        # IMPORTANT: Subscribe ATR capture BEFORE instantiating RiskManager,
        # because EventBus processes handlers in subscription order.
        # RiskManager.on_signal may cascade to OrderFilledEvent, so
        # on_signal_for_atr must fire first.
        pending_atrs: dict[str, float] = {}

        async def on_signal_for_atr(event: SignalEvent) -> None:
            pending_atrs[event.symbol] = event.atr

        bus.subscribe(SignalEvent, on_signal_for_atr)

        # Instantiate components (pass time_fn via kwargs)
        strategy = self._strategy_cls(bus=bus, config=self._config, time_fn=time_fn)
        bus.subscribe(MarketDataEvent, strategy.on_market_data)
        bus.subscribe(OrderFilledEvent, strategy.on_order_filled)
        risk_manager = RiskManager(
            bus=bus, config=self._config,
            equity=self._initial_equity, time_fn=time_fn,
        )
        tracker = PortfolioTracker(bus=bus, config=self._config, time_fn=time_fn)
        SimulatedExecutor(
            bus=bus, current_prices=current_prices,
            slippage=self._slippage, fee_rate=self._fee_rate,
        )

        # Wiring: CloseSignalEvent -> OrderRequestEvent
        last_close_reasons: dict[str, str] = {}

        async def on_close_signal(event: CloseSignalEvent) -> None:
            if event.symbol in tracker.positions:
                pos = tracker.positions[event.symbol]
                last_close_reasons[event.symbol] = event.reason
                order = OrderRequestEvent(
                    symbol=event.symbol, direction=pos["direction"], action="close",
                    size=pos["size"], order_type="market", limit_price=None,
                    stop_loss=0, take_profit=0, reason=event.reason,
                    timestamp=event.timestamp,
                )
                await bus.publish(order)

        bus.subscribe(CloseSignalEvent, on_close_signal)

        # Wiring: OrderFilledEvent -> set ATR + record trades + track wins/losses
        realized_pnl = 0.0

        async def on_fill(event: OrderFilledEvent) -> None:
            nonlocal realized_pnl
            if event.action == "open":
                if event.symbol in pending_atrs:
                    tracker.set_atr(event.symbol, pending_atrs.pop(event.symbol))
                trade_log.record_entry(event)
            elif event.action == "close":
                reason = last_close_reasons.pop(event.symbol, "force_close")
                entry = trade_log.open_entries.get(event.symbol)
                if entry:
                    if entry.direction == "long":
                        pnl = (event.filled_price - entry.filled_price) * entry.filled_size
                    else:
                        pnl = (entry.filled_price - event.filled_price) * entry.filled_size
                    pnl -= entry.fee + event.fee
                    realized_pnl += pnl
                    if pnl >= 0:
                        risk_manager.record_win()
                    else:
                        risk_manager.record_loss(abs(pnl))
                trade_log.record_exit(event, reason=reason)

        bus.subscribe(OrderFilledEvent, on_fill)

        # Load data
        primary_tf = self._config["strategy"]["primary_timeframe"]
        confirm_tf = self._config["strategy"]["confirm_timeframe"]
        warmup: int = self._config.get("data", {}).get("warmup_candles", 200)

        warmup_delta_ms = warmup * 3600000  # Assume 1h bars for warmup calc
        load_start_ms = int(self._start.timestamp() * 1000) - warmup_delta_ms
        load_start = datetime.fromtimestamp(load_start_ms / 1000, tz=timezone.utc)

        candles_by_key: dict[tuple[str, str], list[Candle]] = {}
        for symbol in self._symbols:
            for tf in [primary_tf, confirm_tf]:
                candles = await self._loader.load(symbol, tf, load_start, self._end)
                if candles:
                    candles_by_key[(symbol, tf)] = candles
                else:
                    logger.warning("No %s data for %s", tf, symbol)

        # Build timeline from primary timeframe timestamps within test period
        start_ms = int(self._start.timestamp() * 1000)
        end_ms = int(self._end.timestamp() * 1000)
        timeline: set[int] = set()
        for symbol in self._symbols:
            for c in candles_by_key.get((symbol, primary_tf), []):
                if start_ms <= c.timestamp <= end_ms:
                    timeline.add(c.timestamp)
        sorted_timeline = sorted(timeline)

        if not sorted_timeline:
            logger.warning("No candle data in test period")
            return BacktestResult(
                trade_log=trade_log,
                equity_curve=[self._initial_equity],
                timestamps=[],
                config=self._config,
            )

        # Run loop
        equity_curve: list[float] = [self._initial_equity]
        timestamps: list[int] = []
        last_utc_date = None

        for ts in sorted_timeline:
            current_ts = ts

            # Daily reset check
            utc_date = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date()
            if last_utc_date is not None and utc_date != last_utc_date:
                risk_manager.reset_daily_loss()
            last_utc_date = utc_date

            # Clear cycle cooldowns
            strategy.clear_cycle_cooldowns()

            # Update current prices
            for symbol in self._symbols:
                primary_candles = candles_by_key.get((symbol, primary_tf), [])
                for c in primary_candles:
                    if c.timestamp == ts:
                        current_prices[symbol] = c.close
                        break

            # Publish MarketDataEvents
            for symbol in self._symbols:
                for tf in [primary_tf, confirm_tf]:
                    all_candles = candles_by_key.get((symbol, tf), [])
                    window = [c for c in all_candles if c.timestamp <= ts]
                    if window:
                        event = MarketDataEvent(
                            symbol=symbol, timeframe=tf,
                            candles=window, timestamp=ts,
                        )
                        await bus.publish(event)

            # Update positions and check exits
            for symbol in list(tracker.positions.keys()):
                if symbol in current_prices:
                    tracker.update_price(symbol, current_prices[symbol])
                    await tracker.check_exits(symbol, current_prices[symbol])

            # Record equity
            unrealized = 0.0
            for symbol, pos in tracker.positions.items():
                price = current_prices.get(symbol, pos["entry_price"])
                if pos["direction"] == "long":
                    unrealized += (price - pos["entry_price"]) * pos["size"]
                else:
                    unrealized += (pos["entry_price"] - price) * pos["size"]

            equity = self._initial_equity + realized_pnl + unrealized
            equity_curve.append(round(equity, 2))
            timestamps.append(ts)
            risk_manager.update_equity(equity)

        # Force-close remaining positions
        for symbol in list(tracker.positions.keys()):
            pos = tracker.positions[symbol]
            last_close_reasons[symbol] = "force_close"
            close_order = OrderRequestEvent(
                symbol=symbol, direction=pos["direction"], action="close",
                size=pos["size"], order_type="market", limit_price=None,
                stop_loss=0, take_profit=0, reason="force_close",
                timestamp=current_ts,
            )
            await bus.publish(close_order)

        # Final equity after force-close
        if equity_curve:
            final_equity = self._initial_equity + realized_pnl
            equity_curve[-1] = round(final_equity, 2)

        return BacktestResult(
            trade_log=trade_log,
            equity_curve=equity_curve,
            timestamps=timestamps,
            config=self._config,
        )
