import argparse
import asyncio
import logging
import os
import signal
import time

from dotenv import load_dotenv

from core.event_bus import EventBus
from core.events import CloseSignalEvent, OrderFilledEvent, OrderRequestEvent, SignalEvent
from data.feeder import DataFeeder
from data.store import Store
from execution.order_executor import OrderExecutor
from execution.risk_manager import RiskManager
from notify.telegram import TelegramNotifier
from portfolio.tracker import PortfolioTracker
from strategy.signal_engine import SignalEngine
from utils.config import load_config
from utils.logger import setup_logging

logger = logging.getLogger(__name__)

class HyperQuant:
    def __init__(self, config: dict, dry_run: bool = False) -> None:
        self._config = config
        self._dry_run = dry_run
        self._running = False
        self._bus = EventBus()
        self._store: Store | None = None
        self._notifier: TelegramNotifier | None = None

    async def start(self) -> None:
        logger.info("Starting HyperQuant (dry_run=%s)", self._dry_run)
        self._store = Store("hyperquant.db")
        await self._store.initialize()
        notify_cfg = self._config["notify"]
        self._notifier = TelegramNotifier(
            token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            enabled=notify_cfg["enabled"],
        )
        if self._dry_run:
            from unittest.mock import AsyncMock
            client = AsyncMock()
            client.fetch_candles.return_value = []
            client.fetch_tickers.return_value = []
            client.get_account_equity.return_value = 10_000
        else:
            raise NotImplementedError(
                "Production Hyperliquid client not yet implemented. Use --dry-run."
            )
        equity = await client.get_account_equity()
        feeder = DataFeeder(bus=self._bus, client=client, config=self._config)
        signal_engine = SignalEngine(bus=self._bus, config=self._config)
        risk_manager = RiskManager(bus=self._bus, config=self._config, equity=equity)
        tracker = PortfolioTracker(bus=self._bus, config=self._config)
        if not self._dry_run:
            OrderExecutor(bus=self._bus, client=client, config=self._config)

        # Wire CloseSignalEvent -> OrderRequestEvent
        async def on_close_signal(event):
            if event.symbol in tracker.positions:
                pos = tracker.positions[event.symbol]
                order = OrderRequestEvent(
                    symbol=event.symbol, direction=pos["direction"], action="close",
                    size=pos["size"], order_type="market", limit_price=None,
                    stop_loss=0, take_profit=0, reason=event.reason, timestamp=event.timestamp,
                )
                await self._bus.publish(order)
        self._bus.subscribe(CloseSignalEvent, on_close_signal)

        # Wire ATR from signal to tracker
        self._pending_atrs = {}
        async def on_signal_for_atr(event):
            self._pending_atrs[event.symbol] = event.atr
        async def on_fill_set_atr(event):
            if event.action == "open" and event.symbol in self._pending_atrs:
                tracker.set_atr(event.symbol, self._pending_atrs.pop(event.symbol))
        self._bus.subscribe(SignalEvent, on_signal_for_atr)
        self._bus.subscribe(OrderFilledEvent, on_fill_set_atr)

        await feeder.refresh_symbol_pool()
        self._running = True
        await self._run_loop(feeder, risk_manager, signal_engine)

    async def _run_loop(self, feeder: DataFeeder, risk_manager: RiskManager,
                        signal_engine: SignalEngine) -> None:
        import datetime
        pool_refresh_interval = self._config["data"]["pool_refresh_interval"]
        last_pool_refresh = time.time()
        last_utc_date = datetime.datetime.now(datetime.UTC).date()
        while self._running:
            now = time.time()

            # Reset daily loss only at UTC midnight
            current_utc_date = datetime.datetime.now(datetime.UTC).date()
            if current_utc_date != last_utc_date:
                risk_manager.reset_daily_loss()
                last_utc_date = current_utc_date

            if now - last_pool_refresh >= pool_refresh_interval:
                try:
                    await feeder.refresh_symbol_pool()
                    last_pool_refresh = now
                except Exception:
                    logger.exception("Symbol pool refresh failed")

            # Clear same-cycle reversal cooldowns before each evaluation cycle
            signal_engine.clear_cycle_cooldowns()

            for symbol in feeder.symbol_pool:
                for tf in [self._config["strategy"]["primary_timeframe"],
                           self._config["strategy"]["confirm_timeframe"]]:
                    try:
                        await feeder.fetch_and_publish_candles(symbol, tf)
                    except Exception:
                        logger.exception("Candle fetch failed: %s %s", symbol, tf)
            await asyncio.sleep(60)

    def stop(self) -> None:
        self._running = False

    async def shutdown(self) -> None:
        self.stop()
        if self._store:
            await self._store.close()
        logger.info("HyperQuant shutdown complete")

def main():
    parser = argparse.ArgumentParser(description="HyperQuant Trading Bot")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--dry-run", action="store_true", help="Run without placing real orders")
    args = parser.parse_args()
    load_dotenv()
    config = load_config(args.config)
    log_cfg = config["logging"]
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("file", "logs/hyperquant.log"),
        max_size_mb=log_cfg.get("max_size_mb", 50),
        backup_count=log_cfg.get("backup_count", 5),
    )
    bot = HyperQuant(config=config, dry_run=args.dry_run)
    loop = asyncio.new_event_loop()
    def handle_signal(sig):
        logger.info("Received signal %s, shutting down...", sig)
        loop.create_task(bot.shutdown())
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal, sig)
    try:
        loop.run_until_complete(bot.start())
    except KeyboardInterrupt:
        loop.run_until_complete(bot.shutdown())
    finally:
        loop.close()

if __name__ == "__main__":
    main()
