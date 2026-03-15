# Backtesting System Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a general-purpose backtesting system that replays historical candles through the existing event-driven architecture, producing performance reports.

**Architecture:** Reuse EventBus + RiskManager + PortfolioTracker with a new Strategy ABC, SimulatedExecutor (mock fills), DataLoader (CSV/Parquet/API), and ReportGenerator. The backtest engine orchestrates time-stepping and event wiring identical to main.py.

**Tech Stack:** Python 3.11+, pytest-asyncio, numpy, matplotlib, pyarrow (optional)

**Spec:** `docs/superpowers/specs/2026-03-15-backtesting-system-design.md`

---

## Chunk 1: Foundation (Tasks 1-3)

### Task 1: Strategy ABC + SignalEngine Refactor

**Files:**
- Create: `strategy/base.py`
- Modify: `strategy/signal_engine.py`
- Test: `tests/test_strategy_base.py`

- [ ] **Step 1: Write tests for Strategy ABC**

Create `tests/test_strategy_base.py`:

```python
import pytest
from core.event_bus import EventBus
from core.events import MarketDataEvent, OrderFilledEvent
from strategy.base import Strategy


class DummyStrategy(Strategy):
    def __init__(self, bus: EventBus, config: dict, **kwargs) -> None:
        self.bus = bus
        self.received: list = []

    async def on_market_data(self, event: MarketDataEvent) -> None:
        self.received.append(event)


def test_cannot_instantiate_abc():
    with pytest.raises(TypeError):
        Strategy(bus=EventBus(), config={})  # type: ignore[abstract]


def test_dummy_strategy_instantiates():
    s = DummyStrategy(bus=EventBus(), config={})
    assert s is not None


async def test_on_order_filled_default_noop():
    s = DummyStrategy(bus=EventBus(), config={})
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="o1", fee=5.0, timestamp=1000,
    )
    await s.on_order_filled(fill)  # Should not raise


def test_clear_cycle_cooldowns_default_noop():
    s = DummyStrategy(bus=EventBus(), config={})
    s.clear_cycle_cooldowns()  # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_strategy_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.base'`

- [ ] **Step 3: Implement Strategy ABC**

Create `strategy/base.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_strategy_base.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Refactor SignalEngine to extend Strategy**

Modify `strategy/signal_engine.py`:
- Add import: `from strategy.base import Strategy`
- Change class declaration: `class SignalEngine(Strategy):`
- Rename `_on_order_filled` to `on_order_filled` and keep event bus subscription pointing to the new name
- The existing `on_market_data` and `clear_cycle_cooldowns` already match the ABC signatures

The existing `_on_order_filled` method is subscribed via `bus.subscribe(OrderFilledEvent, self._on_order_filled)` — update to `self.on_order_filled`. Also update `_on_close_signal` subscription if needed.

- [ ] **Step 6: Run all existing tests to verify no regression**

Run: `pytest tests/ -v`
Expected: All existing tests PASS (especially `test_signal_engine.py`)

- [ ] **Step 7: Commit**

```bash
git add strategy/base.py strategy/signal_engine.py tests/test_strategy_base.py
git commit -m "feat: add Strategy ABC and refactor SignalEngine to extend it"
```

---

### Task 2: Time Source Injection

**Files:**
- Modify: `execution/risk_manager.py`
- Modify: `portfolio/tracker.py`
- Modify: `strategy/signal_engine.py`
- Test: `tests/test_risk_manager.py` (existing — verify no regression)
- Test: `tests/test_tracker.py` (existing — verify no regression)
- Test: `tests/test_signal_engine.py` (existing — verify no regression)

- [ ] **Step 1: Write test for injectable time in RiskManager**

Add to a new file `tests/test_time_injection.py`:

```python
import pytest
from core.event_bus import EventBus
from core.events import SignalEvent
from execution.risk_manager import RiskManager


@pytest.fixture
def config():
    return {
        "risk": {
            "risk_per_trade": 0.02, "max_open_positions": 5,
            "max_single_exposure": 0.20, "max_total_exposure": 0.80,
            "max_leverage": 3.0, "max_daily_loss": 0.05,
            "consecutive_loss_limit": 5, "cooldown_hours": 24,
        },
        "stop_loss": {"initial_atr_multiple": 2.0, "take_profit_atr_multiple": 3.0},
    }


async def test_risk_manager_uses_injected_time(config):
    bus = EventBus()
    fake_time = 1000000.0
    rm = RiskManager(bus=bus, config=config, equity=10000, time_fn=lambda: fake_time)

    # Trigger consecutive losses to activate cooldown
    for _ in range(5):
        rm.record_loss(100)

    # Cooldown should be at fake_time + 24*3600
    assert rm._cooldown_until == fake_time + 24 * 3600
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_time_injection.py -v`
Expected: FAIL — `TypeError: RiskManager.__init__() got an unexpected keyword argument 'time_fn'`

- [ ] **Step 3: Inject time_fn into RiskManager**

Modify `execution/risk_manager.py`:
- Add `time_fn` parameter to `__init__`: `def __init__(self, bus, config, equity, time_fn=None):`
- Store: `self._time_fn = time_fn or time.time`
- Replace `time.time()` with `self._time_fn()` at:
  - `on_signal()` method (line ~29): `now = self._time_fn()`
  - `on_signal()` method (line ~67): `timestamp=int(self._time_fn() * 1000)` in OrderRequestEvent
  - `record_loss()` method (line ~84): `self._cooldown_until = self._time_fn() + ...`

- [ ] **Step 4: Run test + all existing RiskManager tests**

Run: `pytest tests/test_time_injection.py tests/test_risk_manager.py -v`
Expected: All PASS

- [ ] **Step 5: Inject time_fn into PortfolioTracker**

Modify `portfolio/tracker.py`:
- Add `time_fn` parameter to `__init__`: `def __init__(self, bus, config, time_fn=None):`
- Store: `self._time_fn = time_fn or time.time`
- Replace `time.time()` with `self._time_fn()` in `check_exits()` (two occurrences, lines ~93 and ~98): `timestamp=int(self._time_fn() * 1000)`

- [ ] **Step 6: Inject time_fn into SignalEngine**

Modify `strategy/signal_engine.py`:
- Add `time_fn` parameter to `__init__`: `def __init__(self, bus, config, time_fn=None):`
- Store: `self._time_fn = time_fn or time.time`
- Replace all `time.time()` with `self._time_fn()` in `_evaluate_symbol()` (three occurrences, lines ~92, ~98, ~129): `timestamp=int(self._time_fn() * 1000)`

- [ ] **Step 7: Run all tests to verify no regression**

Run: `pytest tests/ -v`
Expected: All PASS

- [ ] **Step 8: Commit**

```bash
git add execution/risk_manager.py portfolio/tracker.py strategy/signal_engine.py tests/test_time_injection.py
git commit -m "feat: add injectable time source to RiskManager, PortfolioTracker, SignalEngine"
```

---

### Task 3: TradeLog

**Files:**
- Create: `backtest/__init__.py`
- Create: `backtest/trade_log.py`
- Modify: `pyproject.toml` (add `"backtest*"` to packages.find.include)
- Test: `tests/test_trade_log.py`

- [ ] **Step 1: Write tests for TradeLog**

Create `tests/test_trade_log.py`:

```python
import os
import pytest
from core.events import OrderFilledEvent
from backtest.trade_log import TradeLog, TradeRecord


def _make_entry_fill(symbol="BTC", direction="long", price=50000.0, size=0.1, fee=1.75, ts=1000):
    return OrderFilledEvent(
        symbol=symbol, direction=direction, action="open",
        filled_size=size, filled_price=price, order_id="o1", fee=fee, timestamp=ts,
    )


def _make_exit_fill(symbol="BTC", direction="long", price=52000.0, size=0.1, fee=1.82, ts=2000):
    return OrderFilledEvent(
        symbol=symbol, direction=direction, action="close",
        filled_size=size, filled_price=price, order_id="o2", fee=fee, timestamp=ts,
    )


def test_record_entry_and_exit():
    log = TradeLog()
    log.record_entry(_make_entry_fill())
    log.record_exit(_make_exit_fill(), reason="take_profit")

    trades = log.get_trades()
    assert len(trades) == 1
    t = trades[0]
    assert t.symbol == "BTC"
    assert t.direction == "long"
    assert t.entry_price == 50000.0
    assert t.exit_price == 52000.0
    assert t.exit_reason == "take_profit"
    # PnL: (52000 - 50000) * 0.1 - 1.75 - 1.82 = 200 - 3.57 = 196.43
    assert abs(t.pnl - 196.43) < 0.01
    assert abs(t.fee - 3.57) < 0.01


def test_short_trade_pnl():
    log = TradeLog()
    log.record_entry(_make_entry_fill(direction="short", price=50000.0))
    log.record_exit(_make_exit_fill(direction="short", price=48000.0), reason="stop_loss")

    t = log.get_trades()[0]
    # PnL: (50000 - 48000) * 0.1 - fees = 200 - 3.57 = 196.43
    assert abs(t.pnl - 196.43) < 0.01


def test_open_entries_not_in_trades():
    log = TradeLog()
    log.record_entry(_make_entry_fill())
    assert len(log.get_trades()) == 0
    assert len(log.open_entries) == 1


def test_to_csv(tmp_path):
    log = TradeLog()
    log.record_entry(_make_entry_fill())
    log.record_exit(_make_exit_fill(), reason="trailing_stop")

    path = str(tmp_path / "trades.csv")
    log.to_csv(path)
    assert os.path.exists(path)

    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 2  # header + 1 trade
    assert "BTC" in lines[1]
    assert "trailing_stop" in lines[1]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_trade_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest'`

- [ ] **Step 3: Implement TradeLog**

Create `backtest/__init__.py` (empty file).

Update `pyproject.toml`: add `"backtest*"` to `tool.setuptools.packages.find.include` list.

Create `backtest/trade_log.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_trade_log.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backtest/__init__.py backtest/trade_log.py tests/test_trade_log.py pyproject.toml
git commit -m "feat: add TradeLog with TradeRecord dataclass and CSV export"
```

---

## Chunk 2: Execution Layer (Tasks 4-5)

### Task 4: SimulatedExecutor

**Files:**
- Create: `backtest/simulated_executor.py`
- Test: `tests/test_simulated_executor.py`

- [ ] **Step 1: Write tests for SimulatedExecutor**

Create `tests/test_simulated_executor.py`:

```python
import pytest
from core.event_bus import EventBus
from core.events import OrderFilledEvent, OrderRequestEvent
from backtest.simulated_executor import SimulatedExecutor


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def current_prices():
    return {"BTC": 50000.0, "ETH": 3000.0}


@pytest.fixture
def executor(bus, current_prices):
    return SimulatedExecutor(
        bus=bus, current_prices=current_prices,
        slippage=0.001, fee_rate=0.00035,
    )


async def test_open_long_fill(bus, executor, current_prices):
    fills = []

    async def on_fill(e):
        fills.append(e)

    bus.subscribe(OrderFilledEvent, on_fill)

    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="open",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=48000, take_profit=54000, reason="test", timestamp=1000,
    )
    await bus.publish(req)

    assert len(fills) == 1
    f = fills[0]
    assert f.symbol == "BTC"
    assert f.direction == "long"
    assert f.action == "open"
    assert f.filled_size == 0.1
    # Buy: price * (1 + slippage) = 50000 * 1.001 = 50050
    assert abs(f.filled_price - 50050.0) < 0.01
    # Fee: 50050 * 0.1 * 0.00035 = 1.75175
    assert abs(f.fee - 1.75175) < 0.001


async def test_open_short_fill(bus, executor, current_prices):
    fills = []

    async def on_fill(e):
        fills.append(e)

    bus.subscribe(OrderFilledEvent, on_fill)

    req = OrderRequestEvent(
        symbol="BTC", direction="short", action="open",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=52000, take_profit=46000, reason="test", timestamp=1000,
    )
    await bus.publish(req)

    f = fills[0]
    # Sell: price * (1 - slippage) = 50000 * 0.999 = 49950
    assert abs(f.filled_price - 49950.0) < 0.01


async def test_close_long_fill(bus, executor, current_prices):
    """Closing a long = selling → adverse slippage is downward."""
    fills = []

    async def on_fill(e):
        fills.append(e)

    bus.subscribe(OrderFilledEvent, on_fill)

    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="close",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=0, take_profit=0, reason="trailing_stop", timestamp=2000,
    )
    await bus.publish(req)

    f = fills[0]
    # Close long = sell: price * (1 - slippage) = 49950
    assert abs(f.filled_price - 49950.0) < 0.01


async def test_close_short_fill(bus, executor, current_prices):
    """Closing a short = buying → adverse slippage is upward."""
    fills = []

    async def on_fill(e):
        fills.append(e)

    bus.subscribe(OrderFilledEvent, on_fill)

    req = OrderRequestEvent(
        symbol="BTC", direction="short", action="close",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=0, take_profit=0, reason="stop_loss", timestamp=2000,
    )
    await bus.publish(req)

    f = fills[0]
    # Close short = buy: price * (1 + slippage) = 50050
    assert abs(f.filled_price - 50050.0) < 0.01


async def test_missing_symbol_logs_warning(bus, executor, caplog):
    req = OrderRequestEvent(
        symbol="UNKNOWN", direction="long", action="open",
        size=0.1, order_type="market", limit_price=None,
        stop_loss=0, take_profit=0, reason="test", timestamp=1000,
    )
    await bus.publish(req)
    assert "No price available" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_simulated_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.simulated_executor'`

- [ ] **Step 3: Implement SimulatedExecutor**

Create `backtest/simulated_executor.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_simulated_executor.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backtest/simulated_executor.py tests/test_simulated_executor.py
git commit -m "feat: add SimulatedExecutor with slippage and fee modeling"
```

---

### Task 5: DataLoader (CSV + Parquet)

**Files:**
- Create: `backtest/data_loader.py`
- Test: `tests/test_data_loader.py`

Note: `HyperliquidLoader` is included as a stub that raises `NotImplementedError` — it depends on an API client that isn't implemented yet. CSV and Parquet loaders are fully functional.

- [ ] **Step 1: Write tests for CsvLoader and ParquetLoader**

Create `tests/test_data_loader.py`:

```python
import os
from datetime import datetime, timezone

import pytest

from backtest.data_loader import CsvLoader, ParquetLoader
from core.events import Candle


def _make_csv(tmp_path, symbol="BTC-PERP", timeframe="1h", rows=10):
    path = tmp_path / f"{symbol}_{timeframe}.csv"
    with open(path, "w") as f:
        f.write("timestamp,open,high,low,close,volume\n")
        for i in range(rows):
            ts = 1704067200000 + i * 3600000  # 2024-01-01 + i hours
            f.write(f"{ts},{100+i},{102+i},{99+i},{101+i},{1000}\n")
    return str(tmp_path)


async def test_csv_loader_basic(tmp_path):
    csv_dir = _make_csv(tmp_path)
    loader = CsvLoader(data_dir=csv_dir)
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    candles = await loader.load("BTC-PERP", "1h", start, end)
    assert len(candles) > 0
    assert all(isinstance(c, Candle) for c in candles)
    # Sorted ascending
    for i in range(1, len(candles)):
        assert candles[i].timestamp >= candles[i - 1].timestamp


async def test_csv_loader_filters_by_date(tmp_path):
    csv_dir = _make_csv(tmp_path, rows=100)
    loader = CsvLoader(data_dir=csv_dir)
    start = datetime(2024, 1, 1, 2, 0, tzinfo=timezone.utc)  # Skip first 2 hours
    end = datetime(2024, 1, 1, 5, 0, tzinfo=timezone.utc)

    candles = await loader.load("BTC-PERP", "1h", start, end)
    for c in candles:
        assert c.timestamp >= int(start.timestamp() * 1000)
        assert c.timestamp <= int(end.timestamp() * 1000)


async def test_csv_loader_missing_file(tmp_path):
    loader = CsvLoader(data_dir=str(tmp_path))
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)
    candles = await loader.load("NONEXISTENT", "1h", start, end)
    assert candles == []


async def test_parquet_loader_basic(tmp_path):
    """Test ParquetLoader with a real parquet file."""
    try:
        import pyarrow  # noqa: F401
    except ImportError:
        pytest.skip("pyarrow not installed")

    import pyarrow as pa
    import pyarrow.parquet as pq

    # Create test parquet file
    rows = 10
    ts = [1704067200000 + i * 3600000 for i in range(rows)]
    table = pa.table({
        "timestamp": ts,
        "open": [100.0 + i for i in range(rows)],
        "high": [102.0 + i for i in range(rows)],
        "low": [99.0 + i for i in range(rows)],
        "close": [101.0 + i for i in range(rows)],
        "volume": [1000.0] * rows,
    })
    path = tmp_path / "BTC-PERP_1h.parquet"
    pq.write_table(table, path)

    loader = ParquetLoader(data_dir=str(tmp_path))
    start = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end = datetime(2024, 1, 2, tzinfo=timezone.utc)

    candles = await loader.load("BTC-PERP", "1h", start, end)
    assert len(candles) > 0
    assert all(isinstance(c, Candle) for c in candles)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_data_loader.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.data_loader'`

- [ ] **Step 3: Implement DataLoader, CsvLoader, ParquetLoader, HyperliquidLoader stub**

Create `backtest/data_loader.py`:

```python
import logging
import os
from abc import ABC, abstractmethod
from datetime import datetime, timezone

from core.events import Candle

logger = logging.getLogger(__name__)


class DataLoader(ABC):
    @abstractmethod
    async def load(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> list[Candle]:
        """Load candles for a symbol/timeframe in [start, end].
        Returns list[Candle] sorted by timestamp ascending."""


class HyperliquidLoader(DataLoader):
    """Loads candles from Hyperliquid API with local SQLite caching.

    Not yet implemented — requires a production Hyperliquid client.
    """

    async def load(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> list[Candle]:
        raise NotImplementedError(
            "HyperliquidLoader requires a production Hyperliquid client. "
            "Use CsvLoader or ParquetLoader instead."
        )


class CsvLoader(DataLoader):
    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir

    async def load(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> list[Candle]:
        import csv

        filename = f"{symbol}_{timeframe}.csv"
        filepath = os.path.join(self._data_dir, filename)
        if not os.path.exists(filepath):
            logger.warning("CSV file not found: %s", filepath)
            return []

        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        candles: list[Candle] = []

        with open(filepath, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = int(row["timestamp"])
                if ts < start_ms or ts > end_ms:
                    continue
                candles.append(Candle(
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                    timestamp=ts,
                ))

        candles.sort(key=lambda c: c.timestamp)
        return candles


class ParquetLoader(DataLoader):
    def __init__(self, data_dir: str) -> None:
        self._data_dir = data_dir

    async def load(
        self, symbol: str, timeframe: str,
        start: datetime, end: datetime,
    ) -> list[Candle]:
        try:
            import pyarrow.parquet as pq
        except ImportError:
            logger.error("pyarrow is required for ParquetLoader. Install with: pip install pyarrow")
            return []

        filename = f"{symbol}_{timeframe}.parquet"
        filepath = os.path.join(self._data_dir, filename)
        if not os.path.exists(filepath):
            logger.warning("Parquet file not found: %s", filepath)
            return []

        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)

        table = pq.read_table(filepath)
        df = table.to_pandas()
        df = df[(df["timestamp"] >= start_ms) & (df["timestamp"] <= end_ms)]
        df = df.sort_values("timestamp")

        return [
            Candle(
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                timestamp=int(row["timestamp"]),
            )
            for _, row in df.iterrows()
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_data_loader.py -v`
Expected: All tests PASS (parquet test may skip if pyarrow not installed)

- [ ] **Step 5: Commit**

```bash
git add backtest/data_loader.py tests/test_data_loader.py
git commit -m "feat: add DataLoader ABC with CsvLoader and ParquetLoader implementations"
```

---

## Chunk 3: BacktestEngine (Task 6)

### Task 6: BacktestEngine

**Files:**
- Create: `backtest/engine.py`
- Test: `tests/test_backtest_engine.py`

This is the core orchestrator. It wires everything together and runs the time-stepping loop.

- [ ] **Step 1: Write integration test with synthetic data**

Create `tests/test_backtest_engine.py`:

```python
import pytest
from datetime import datetime, timezone

from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine, BacktestResult
from core.event_bus import EventBus
from core.events import Candle, MarketDataEvent, SignalEvent
from strategy.base import Strategy


# --- Helpers ---

def _make_uptrend_candles(n=100, start_price=100.0, start_ts=1704067200000):
    """1h candles starting 2024-01-01, price going up."""
    return [
        Candle(
            open=start_price + i - 0.5, high=start_price + i + 2,
            low=start_price + i - 1, close=start_price + i,
            volume=1000, timestamp=start_ts + i * 3600000,
        )
        for i in range(n)
    ]


class MemoryLoader(DataLoader):
    """In-memory loader for testing."""
    def __init__(self, candles_by_key: dict[tuple[str, str], list[Candle]]) -> None:
        self._data = candles_by_key

    async def load(self, symbol, timeframe, start, end):
        candles = self._data.get((symbol, timeframe), [])
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        return [c for c in candles if start_ms <= c.timestamp <= end_ms]


class AlwaysLongStrategy(Strategy):
    """Emits a long signal on every primary-timeframe bar, for testing."""
    def __init__(self, bus: EventBus, config: dict, **kwargs) -> None:
        self._bus = bus
        self._config = config
        self._open_symbols: set[str] = set()
        self._signaled: set[str] = set()

    async def on_market_data(self, event: MarketDataEvent) -> None:
        if event.timeframe != self._config["strategy"]["primary_timeframe"]:
            return
        if event.symbol in self._open_symbols or event.symbol in self._signaled:
            return
        if len(event.candles) < 2:
            return
        close = event.candles[-1].close
        atr = 2.0  # Fixed ATR for simplicity
        signal = SignalEvent(
            symbol=event.symbol, direction="long", score=80.0,
            entry_price=close, atr=atr,
            stop_loss=close - 4.0, take_profit=close + 6.0,
            timestamp=event.timestamp,
        )
        self._signaled.add(event.symbol)
        await self._bus.publish(signal)

    async def on_order_filled(self, event):
        if event.action == "open":
            self._open_symbols.add(event.symbol)
        elif event.action == "close":
            self._open_symbols.discard(event.symbol)
            self._signaled.discard(event.symbol)


@pytest.fixture
def config():
    return {
        "strategy": {
            "primary_timeframe": "1h", "confirm_timeframe": "4h",
            "score_threshold": 65, "ema_fast": 20, "ema_slow": 60,
            "rsi_period": 14, "macd_fast": 12, "macd_slow": 26,
            "macd_signal": 9, "donchian_period": 20, "atr_period": 14,
            "exit_score_threshold": 30, "max_new_positions": 3,
        },
        "risk": {
            "risk_per_trade": 0.02, "max_open_positions": 5,
            "max_single_exposure": 0.20, "max_total_exposure": 0.80,
            "max_leverage": 3.0, "max_daily_loss": 0.05,
            "consecutive_loss_limit": 5, "cooldown_hours": 24,
        },
        "stop_loss": {
            "initial_atr_multiple": 2.0, "take_profit_atr_multiple": 3.0,
            "breakeven_trigger_atr": 1.0, "trailing_trigger_atr": 2.0,
            "trailing_distance_atr": 1.5,
        },
        "data": {"warmup_candles": 10},
        "backtest": {
            "slippage": 0.001, "fee_rate": 0.00035, "initial_equity": 10000,
        },
    }


async def test_engine_runs_and_returns_result(config):
    candles = _make_uptrend_candles(50)
    loader = MemoryLoader({("BTC", "1h"): candles, ("BTC", "4h"): candles})

    engine = BacktestEngine(
        config=config, strategy_cls=AlwaysLongStrategy,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 10, tzinfo=timezone.utc),
    )
    result = await engine.run()

    assert isinstance(result, BacktestResult)
    assert len(result.equity_curve) > 0
    assert result.equity_curve[0] == 10000.0


async def test_engine_force_closes_at_end(config):
    candles = _make_uptrend_candles(50)
    loader = MemoryLoader({("BTC", "1h"): candles, ("BTC", "4h"): candles})

    engine = BacktestEngine(
        config=config, strategy_cls=AlwaysLongStrategy,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 10, tzinfo=timezone.utc),
    )
    result = await engine.run()

    # All positions should be closed at end
    assert len(result.trade_log.open_entries) == 0
    # Should have at least 1 completed trade (entry + force-close)
    assert len(result.trade_log.get_trades()) >= 1


async def test_engine_equity_curve_tracks_pnl(config):
    candles = _make_uptrend_candles(50)
    loader = MemoryLoader({("BTC", "1h"): candles, ("BTC", "4h"): candles})

    engine = BacktestEngine(
        config=config, strategy_cls=AlwaysLongStrategy,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 1, 10, tzinfo=timezone.utc),
        end=datetime(2024, 1, 2, 10, tzinfo=timezone.utc),
    )
    result = await engine.run()

    # In an uptrend, final equity should differ from initial (fees at minimum)
    assert result.equity_curve[-1] != result.equity_curve[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_backtest_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.engine'`

- [ ] **Step 3: Implement BacktestEngine**

Create `backtest/engine.py`:

```python
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

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
    config: dict = field(default_factory=dict)


class BacktestEngine:
    def __init__(
        self,
        config: dict,
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
        self._initial_equity = bt_cfg.get("initial_equity", 10000)
        self._slippage = bt_cfg.get("slippage", 0.001)
        self._fee_rate = bt_cfg.get("fee_rate", 0.00035)

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
        risk_manager = RiskManager(
            bus=bus, config=self._config,
            equity=self._initial_equity, time_fn=time_fn,
        )
        tracker = PortfolioTracker(bus=bus, config=self._config, time_fn=time_fn)
        SimulatedExecutor(
            bus=bus, current_prices=current_prices,
            slippage=self._slippage, fee_rate=self._fee_rate,
        )

        # Wiring: CloseSignalEvent → OrderRequestEvent
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

        # Wiring: OrderFilledEvent → set ATR + record trades + track wins/losses
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
        warmup = self._config.get("data", {}).get("warmup_candles", 200)

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
        equity_curve: list[float] = []
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_backtest_engine.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Run full test suite for regression**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backtest/engine.py tests/test_backtest_engine.py
git commit -m "feat: add BacktestEngine with event wiring, time-stepping, and equity tracking"
```

---

## Chunk 4: Metrics + Reports (Tasks 7-8)

### Task 7: Performance Metrics

**Files:**
- Create: `backtest/metrics.py`
- Test: `tests/test_metrics.py`

- [ ] **Step 1: Write tests for metrics calculations**

Create `tests/test_metrics.py`:

```python
from datetime import datetime, timezone, timedelta
from backtest.metrics import compute_metrics
from backtest.trade_log import TradeRecord


def _make_trades(pnls: list[float], duration_hours: int = 24) -> list[TradeRecord]:
    trades = []
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i, pnl in enumerate(pnls):
        entry_time = base + timedelta(days=i)
        exit_time = entry_time + timedelta(hours=duration_hours)
        entry_price = 100.0
        exit_price = entry_price + pnl / 0.1  # size=0.1
        trades.append(TradeRecord(
            symbol="BTC", direction="long",
            entry_price=entry_price, exit_price=exit_price,
            size=0.1, entry_time=entry_time, exit_time=exit_time,
            pnl=pnl, fee=0.5, exit_reason="test",
        ))
    return trades


def _make_equity_curve(returns: list[float], initial: float = 10000.0) -> list[float]:
    curve = [initial]
    for r in returns:
        curve.append(curve[-1] * (1 + r))
    return curve


def test_total_return():
    curve = [10000.0, 10500.0, 11000.0]
    m = compute_metrics(trades=[], equity_curve=curve, initial_equity=10000)
    assert abs(m["total_return"] - 0.10) < 0.001


def test_win_rate():
    trades = _make_trades([100, -50, 200, -30, 150])
    m = compute_metrics(trades=trades, equity_curve=[10000, 10370], initial_equity=10000)
    assert abs(m["win_rate"] - 0.60) < 0.01  # 3 wins / 5 trades


def test_profit_factor():
    trades = _make_trades([100, -50, 200])
    m = compute_metrics(trades=trades, equity_curve=[10000, 10250], initial_equity=10000)
    assert abs(m["profit_factor"] - (300 / 50)) < 0.01


def test_max_drawdown():
    curve = [10000, 11000, 9000, 9500, 10500]
    m = compute_metrics(trades=[], equity_curve=curve, initial_equity=10000)
    # Peak 11000 → trough 9000 = -2000 / 11000 ≈ -18.18%
    assert abs(m["max_drawdown_pct"] - 0.1818) < 0.01


def test_max_consecutive_losses():
    trades = _make_trades([100, -50, -30, -20, 200, -10])
    m = compute_metrics(trades=trades, equity_curve=[10000, 10190], initial_equity=10000)
    assert m["max_consecutive_losses"] == 3


def test_empty_trades():
    m = compute_metrics(trades=[], equity_curve=[10000], initial_equity=10000)
    assert m["total_trades"] == 0
    assert m["win_rate"] == 0
    assert m["profit_factor"] == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_metrics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.metrics'`

- [ ] **Step 3: Implement compute_metrics**

Create `backtest/metrics.py`:

```python
import math
from datetime import timedelta

import numpy as np

from backtest.trade_log import TradeRecord


def compute_metrics(
    trades: list[TradeRecord],
    equity_curve: list[float],
    initial_equity: float,
) -> dict:
    total_trades = len(trades)
    if not equity_curve:
        equity_curve = [initial_equity]

    # Return
    final_equity = equity_curve[-1]
    total_return = (final_equity / initial_equity) - 1 if initial_equity > 0 else 0

    # Annualized return
    if len(equity_curve) > 1:
        n_hours = len(equity_curve)  # Approximate: 1 data point per bar (1h)
        years = n_hours / (365.25 * 24)
        if years > 0 and final_equity / initial_equity > 0:
            annualized_return = (final_equity / initial_equity) ** (1 / years) - 1
        else:
            annualized_return = 0.0
    else:
        annualized_return = 0.0

    # Sharpe & Sortino (from equity curve returns)
    if len(equity_curve) > 2:
        returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
        mean_ret = float(np.mean(returns))
        std_ret = float(np.std(returns, ddof=1))
        sharpe = (mean_ret / std_ret * math.sqrt(len(returns))) if std_ret > 0 else 0

        downside = returns[returns < 0]
        downside_std = float(np.std(downside, ddof=1)) if len(downside) > 1 else 0
        sortino = (mean_ret / downside_std * math.sqrt(len(returns))) if downside_std > 0 else 0
    else:
        sharpe = 0.0
        sortino = 0.0

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    max_dd_pct = 0.0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = peak - eq
        dd_pct = dd / peak if peak > 0 else 0
        if dd_pct > max_dd_pct:
            max_dd_pct = dd_pct
            max_dd = dd

    # Win rate, profit factor
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl <= 0]
    win_rate = len(wins) / total_trades if total_trades > 0 else 0
    gross_profit = sum(t.pnl for t in wins)
    gross_loss = abs(sum(t.pnl for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

    # Avg duration
    if total_trades > 0:
        durations = [(t.exit_time - t.entry_time) for t in trades]
        avg_duration = sum(durations, timedelta()) / total_trades
    else:
        avg_duration = timedelta()

    # Max consecutive losses
    max_consec = 0
    current_consec = 0
    for t in trades:
        if t.pnl <= 0:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0

    return {
        "total_return": round(total_return, 4),
        "annualized_return": round(annualized_return, 4),
        "sharpe_ratio": round(sharpe, 4),
        "sortino_ratio": round(sortino, 4),
        "max_drawdown": round(max_dd, 2),
        "max_drawdown_pct": round(max_dd_pct, 4),
        "win_rate": round(win_rate, 4),
        "profit_factor": round(profit_factor, 4),
        "avg_trade_duration": str(avg_duration),
        "max_consecutive_losses": max_consec,
        "total_trades": total_trades,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_metrics.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backtest/metrics.py tests/test_metrics.py
git commit -m "feat: add performance metrics (Sharpe, drawdown, win rate, profit factor)"
```

---

### Task 8: ReportGenerator (Terminal + CSV + Charts + HTML)

**Files:**
- Create: `backtest/report.py`
- Create: `backtest/templates/report.html`
- Test: `tests/test_report.py`

- [ ] **Step 1: Write tests for ReportGenerator**

Create `tests/test_report.py`:

```python
import os
from datetime import datetime, timezone, timedelta

import pytest

from backtest.report import ReportGenerator
from backtest.trade_log import TradeRecord


def _sample_trades():
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    return [
        TradeRecord(
            symbol="BTC", direction="long", entry_price=100, exit_price=110,
            size=0.1, entry_time=base, exit_time=base + timedelta(hours=24),
            pnl=1.0, fee=0.5, exit_reason="take_profit",
        ),
        TradeRecord(
            symbol="ETH", direction="short", entry_price=50, exit_price=48,
            size=1.0, entry_time=base + timedelta(days=1),
            exit_time=base + timedelta(days=1, hours=12),
            pnl=2.0, fee=0.3, exit_reason="trailing_stop",
        ),
    ]


def _sample_metrics():
    return {
        "total_return": 0.03, "annualized_return": 0.15,
        "sharpe_ratio": 1.5, "sortino_ratio": 2.0,
        "max_drawdown": 500, "max_drawdown_pct": 0.05,
        "win_rate": 0.6, "profit_factor": 2.0,
        "avg_trade_duration": "1 day, 0:00:00",
        "max_consecutive_losses": 2, "total_trades": 10,
    }


def test_print_summary(capsys):
    gen = ReportGenerator(
        trades=_sample_trades(), metrics=_sample_metrics(),
        equity_curve=[10000, 10100, 10300], timestamps=[],
    )
    gen.print_summary()
    captured = capsys.readouterr()
    assert "total_return" in captured.out
    assert "sharpe_ratio" in captured.out


def test_export_csv(tmp_path):
    gen = ReportGenerator(
        trades=_sample_trades(), metrics=_sample_metrics(),
        equity_curve=[], timestamps=[],
    )
    path = str(tmp_path / "trades.csv")
    gen.export_csv(path)
    assert os.path.exists(path)
    with open(path) as f:
        lines = f.readlines()
    assert len(lines) == 3  # header + 2 trades


def test_generate_html(tmp_path):
    gen = ReportGenerator(
        trades=_sample_trades(), metrics=_sample_metrics(),
        equity_curve=[10000, 10100, 10300],
        timestamps=[1704067200000, 1704070800000, 1704074400000],
    )
    path = str(tmp_path / "report.html")
    gen.generate_html(path)
    assert os.path.exists(path)
    with open(path) as f:
        content = f.read()
    assert "<!DOCTYPE html>" in content
    assert "total_return" in content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_report.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'backtest.report'`

- [ ] **Step 3: Implement ReportGenerator**

Create `backtest/report.py`:

```python
import base64
import csv
import io
import os
from dataclasses import fields
from datetime import datetime, timezone

from backtest.trade_log import TradeRecord


class ReportGenerator:
    def __init__(
        self,
        trades: list[TradeRecord],
        metrics: dict,
        equity_curve: list[float],
        timestamps: list[int],
    ) -> None:
        self._trades = trades
        self._metrics = metrics
        self._equity_curve = equity_curve
        self._timestamps = timestamps

    def print_summary(self) -> None:
        print("\n" + "=" * 50)
        print("  BACKTEST RESULTS")
        print("=" * 50)
        for key, value in self._metrics.items():
            label = key.replace("_", " ").title()
            if isinstance(value, float):
                if "pct" in key or "return" in key or "rate" in key:
                    print(f"  {label:.<35} {value:>10.2%}")
                else:
                    print(f"  {label:.<35} {value:>10.4f}")
            else:
                print(f"  {label:.<35} {str(value):>10}")
        print("=" * 50 + "\n")

    def export_csv(self, path: str) -> None:
        field_names = [f.name for f in fields(TradeRecord)]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=field_names)
            writer.writeheader()
            for t in self._trades:
                writer.writerow({fn: getattr(t, fn) for fn in field_names})

    def generate_charts(self, output_dir: str) -> dict[str, str]:
        """Generate chart PNGs. Returns {name: filepath}."""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        os.makedirs(output_dir, exist_ok=True)
        charts: dict[str, str] = {}

        # Equity curve
        if self._equity_curve:
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(self._equity_curve, linewidth=1.5)
            ax.set_title("Equity Curve")
            ax.set_xlabel("Bar")
            ax.set_ylabel("Equity")
            ax.grid(True, alpha=0.3)
            path = os.path.join(output_dir, "equity_curve.png")
            fig.savefig(path, dpi=100, bbox_inches="tight")
            plt.close(fig)
            charts["equity_curve"] = path

        # Drawdown curve
        if self._equity_curve:
            peak = self._equity_curve[0]
            dd = []
            for eq in self._equity_curve:
                if eq > peak:
                    peak = eq
                dd.append((eq - peak) / peak * 100)

            fig, ax = plt.subplots(figsize=(12, 3))
            ax.fill_between(range(len(dd)), dd, alpha=0.4, color="red")
            ax.set_title("Drawdown (%)")
            ax.set_xlabel("Bar")
            ax.set_ylabel("Drawdown %")
            ax.grid(True, alpha=0.3)
            path = os.path.join(output_dir, "drawdown.png")
            fig.savefig(path, dpi=100, bbox_inches="tight")
            plt.close(fig)
            charts["drawdown"] = path

        # Monthly returns heatmap
        if self._equity_curve and self._timestamps and len(self._timestamps) > 1:
            from collections import defaultdict
            monthly: dict[tuple[int, int], float] = defaultdict(float)
            for i in range(1, len(self._equity_curve)):
                dt = datetime.fromtimestamp(self._timestamps[i] / 1000, tz=timezone.utc)
                ret = (self._equity_curve[i] - self._equity_curve[i - 1]) / self._equity_curve[i - 1]
                monthly[(dt.year, dt.month)] += ret

            if monthly:
                years = sorted(set(k[0] for k in monthly))
                months = list(range(1, 13))
                data = []
                for y in years:
                    data.append([monthly.get((y, m), 0) * 100 for m in months])

                fig, ax = plt.subplots(figsize=(12, max(3, len(years))))
                im = ax.imshow(data, cmap="RdYlGn", aspect="auto")
                ax.set_xticks(range(12))
                ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
                ax.set_yticks(range(len(years)))
                ax.set_yticklabels(years)
                ax.set_title("Monthly Returns (%)")
                fig.colorbar(im)
                for i_y in range(len(years)):
                    for i_m in range(12):
                        val = data[i_y][i_m]
                        ax.text(i_m, i_y, f"{val:.1f}", ha="center", va="center", fontsize=8)
                path = os.path.join(output_dir, "monthly_returns.png")
                fig.savefig(path, dpi=100, bbox_inches="tight")
                plt.close(fig)
                charts["monthly_returns"] = path

        return charts

    def generate_html(self, path: str) -> None:
        """Generate self-contained HTML report with embedded charts."""
        # Generate charts to temp dir
        chart_dir = os.path.join(os.path.dirname(path), ".charts_tmp")
        charts = self.generate_charts(chart_dir)

        # Embed charts as base64
        chart_html = ""
        for name, chart_path in charts.items():
            with open(chart_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            chart_html += f'<img src="data:image/png;base64,{b64}" style="max-width:100%;margin:10px 0;">\n'

        # Clean up temp charts
        for chart_path in charts.values():
            os.remove(chart_path)
        if os.path.exists(chart_dir):
            try:
                os.rmdir(chart_dir)
            except OSError:
                pass

        # Metrics table
        metrics_rows = ""
        for key, value in self._metrics.items():
            label = key.replace("_", " ").title()
            if isinstance(value, float):
                if "pct" in key or "return" in key or "rate" in key:
                    formatted = f"{value:.2%}"
                else:
                    formatted = f"{value:.4f}"
            else:
                formatted = str(value)
            metrics_rows += f"<tr><td>{label}</td><td>{formatted}</td></tr>\n"

        # Trades table
        trades_rows = ""
        for t in self._trades[:100]:  # Limit to 100 in HTML
            trades_rows += (
                f"<tr><td>{t.symbol}</td><td>{t.direction}</td>"
                f"<td>{t.entry_price:.2f}</td><td>{t.exit_price:.2f}</td>"
                f"<td>{t.size:.6f}</td><td>{t.pnl:.2f}</td>"
                f"<td>{t.exit_reason}</td></tr>\n"
            )

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Backtest Report</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }}
h1 {{ color: #333; }} h2 {{ color: #555; margin-top: 30px; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
tr:nth-child(even) {{ background: #fafafa; }}
</style></head><body>
<h1>Backtest Report</h1>
<h2>Performance Metrics</h2>
<table><tr><th>Metric</th><th>Value</th></tr>{metrics_rows}</table>
<h2>Charts</h2>
{chart_html}
<h2>Trade Log (first 100)</h2>
<table><tr><th>Symbol</th><th>Direction</th><th>Entry</th><th>Exit</th><th>Size</th><th>PnL</th><th>Reason</th></tr>
{trades_rows}</table>
</body></html>"""

        with open(path, "w") as f:
            f.write(html)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_report.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backtest/report.py tests/test_report.py
git commit -m "feat: add ReportGenerator with terminal, CSV, charts, and HTML output"
```

---

## Chunk 5: CLI + Integration (Tasks 9-10)

### Task 9: CLI Entry Point

**Files:**
- Create: `backtest/run.py`
- Modify: `pyproject.toml` (add new dependencies)
- Modify: `config.yaml` (add backtest section)

- [ ] **Step 1: Add backtest config to config.yaml**

Append to `config.yaml`:

```yaml
backtest:
  slippage: 0.001
  fee_rate: 0.00035
  initial_equity: 10000
```

- [ ] **Step 2: Update pyproject.toml**

Add `"backtest*"` to `tool.setuptools.packages.find.include` list.

Add new dependencies to `[project.dependencies]`:
```
"matplotlib>=3.7",
```

Add optional dependency:
```
[project.optional-dependencies]
parquet = ["pyarrow>=14.0"]
```

- [ ] **Step 3: Implement CLI**

Create `backtest/__main__.py`:

```python
from backtest.run import main

if __name__ == "__main__":
    main()
```

Create `backtest/run.py`:

```python
import argparse
import asyncio
import logging
import sys
from datetime import datetime, timezone

from backtest.data_loader import CsvLoader, ParquetLoader
from backtest.engine import BacktestEngine
from backtest.metrics import compute_metrics
from backtest.report import ReportGenerator
from strategy.signal_engine import SignalEngine
from utils.config import load_config
from utils.logger import setup_logging


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _resolve_strategy(name: str):
    if name == "default" or name == "signal_engine":
        return SignalEngine
    # Dynamic import: "module.ClassName"
    module_path, class_name = name.rsplit(".", 1)
    import importlib
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="HyperQuant Backtester")
    parser.add_argument("--config", default="config.yaml", help="Config file path")
    parser.add_argument("--symbols", nargs="+", required=True, help="Symbols to backtest")
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--strategy", default="default", help="Strategy class (default: SignalEngine)")
    parser.add_argument("--csv-dir", help="Directory with CSV candle data")
    parser.add_argument("--parquet-dir", help="Directory with Parquet candle data")
    parser.add_argument("--output", default="reports", help="Output directory for reports")
    parser.add_argument("--initial-equity", type=float, help="Override initial equity")
    parser.add_argument("--slippage", type=float, help="Override slippage")
    args = parser.parse_args()

    config = load_config(args.config)
    log_cfg = config.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("file", "logs/hyperquant.log"),
        max_size_mb=log_cfg.get("max_size_mb", 50),
        backup_count=log_cfg.get("backup_count", 5),
    )

    # Override config with CLI args
    bt_cfg = config.setdefault("backtest", {})
    if args.initial_equity:
        bt_cfg["initial_equity"] = args.initial_equity
    if args.slippage:
        bt_cfg["slippage"] = args.slippage

    # Resolve loader
    if args.csv_dir:
        loader = CsvLoader(data_dir=args.csv_dir)
    elif args.parquet_dir:
        loader = ParquetLoader(data_dir=args.parquet_dir)
    else:
        print("Error: Must specify --csv-dir or --parquet-dir", file=sys.stderr)
        sys.exit(1)

    strategy_cls = _resolve_strategy(args.strategy)

    engine = BacktestEngine(
        config=config,
        strategy_cls=strategy_cls,
        loader=loader,
        symbols=args.symbols,
        start=_parse_date(args.start),
        end=_parse_date(args.end),
    )

    result = asyncio.run(engine.run())

    # Generate reports
    trades = result.trade_log.get_trades()
    metrics = compute_metrics(
        trades=trades,
        equity_curve=result.equity_curve,
        initial_equity=bt_cfg.get("initial_equity", 10000),
    )

    gen = ReportGenerator(
        trades=trades, metrics=metrics,
        equity_curve=result.equity_curve,
        timestamps=result.timestamps,
    )

    gen.print_summary()

    import os
    os.makedirs(args.output, exist_ok=True)

    csv_path = os.path.join(args.output, "trades.csv")
    gen.export_csv(csv_path)
    print(f"Trade log saved to {csv_path}")

    gen.generate_charts(args.output)
    print(f"Charts saved to {args.output}/")

    html_path = os.path.join(args.output, "report.html")
    gen.generate_html(html_path)
    print(f"HTML report saved to {html_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add backtest/run.py backtest/__main__.py config.yaml pyproject.toml
git commit -m "feat: add backtest CLI entry point with CSV/Parquet loader selection"
```

---

### Task 10: Integration Test with SignalEngine

**Files:**
- Test: `tests/test_backtest_integration.py`

This test verifies the full pipeline: SignalEngine (real strategy) → RiskManager → PortfolioTracker → SimulatedExecutor → TradeLog → Metrics → Report.

- [ ] **Step 1: Write integration test**

Create `tests/test_backtest_integration.py`:

```python
import os
from datetime import datetime, timezone

import pytest

from backtest.data_loader import DataLoader
from backtest.engine import BacktestEngine
from backtest.metrics import compute_metrics
from backtest.report import ReportGenerator
from core.events import Candle
from strategy.signal_engine import SignalEngine


def _make_uptrend_candles(n=200, start_price=100.0, start_ts=1704067200000):
    return [
        Candle(
            open=start_price + i - 0.5, high=start_price + i + 2,
            low=start_price + i - 1, close=start_price + i,
            volume=1000, timestamp=start_ts + i * 3600000,
        )
        for i in range(n)
    ]


class MemoryLoader(DataLoader):
    def __init__(self, candles_by_key):
        self._data = candles_by_key

    async def load(self, symbol, timeframe, start, end):
        candles = self._data.get((symbol, timeframe), [])
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        return [c for c in candles if start_ms <= c.timestamp <= end_ms]


@pytest.fixture
def full_config():
    return {
        "strategy": {
            "primary_timeframe": "1h", "confirm_timeframe": "4h",
            "score_threshold": 65, "ema_fast": 20, "ema_slow": 60,
            "rsi_period": 14, "macd_fast": 12, "macd_slow": 26,
            "macd_signal": 9, "donchian_period": 20, "atr_period": 14,
            "exit_score_threshold": 30, "max_new_positions": 3,
        },
        "risk": {
            "risk_per_trade": 0.02, "max_open_positions": 5,
            "max_single_exposure": 0.20, "max_total_exposure": 0.80,
            "max_leverage": 3.0, "max_daily_loss": 0.05,
            "consecutive_loss_limit": 5, "cooldown_hours": 24,
        },
        "stop_loss": {
            "initial_atr_multiple": 2.0, "take_profit_atr_multiple": 3.0,
            "breakeven_trigger_atr": 1.0, "trailing_trigger_atr": 2.0,
            "trailing_distance_atr": 1.5,
        },
        "data": {"warmup_candles": 100},
        "backtest": {
            "slippage": 0.001, "fee_rate": 0.00035, "initial_equity": 10000,
        },
    }


async def test_full_pipeline_with_signal_engine(full_config):
    """Integration: real SignalEngine strategy through full backtest pipeline."""
    candles = _make_uptrend_candles(300)
    loader = MemoryLoader({
        ("BTC", "1h"): candles,
        ("BTC", "4h"): candles,  # Use same data for simplicity
    })

    engine = BacktestEngine(
        config=full_config, strategy_cls=SignalEngine,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 5, tzinfo=timezone.utc),  # After warmup
        end=datetime(2024, 1, 12, tzinfo=timezone.utc),
    )
    result = await engine.run()

    # Should have equity curve
    assert len(result.equity_curve) > 0

    # Compute metrics
    trades = result.trade_log.get_trades()
    metrics = compute_metrics(
        trades=trades,
        equity_curve=result.equity_curve,
        initial_equity=10000,
    )
    assert "total_return" in metrics
    assert "sharpe_ratio" in metrics
    assert metrics["total_trades"] >= 0


async def test_full_pipeline_generates_reports(full_config, tmp_path):
    """Integration: verify report generation from real backtest result."""
    candles = _make_uptrend_candles(300)
    loader = MemoryLoader({
        ("BTC", "1h"): candles,
        ("BTC", "4h"): candles,
    })

    engine = BacktestEngine(
        config=full_config, strategy_cls=SignalEngine,
        loader=loader, symbols=["BTC"],
        start=datetime(2024, 1, 5, tzinfo=timezone.utc),
        end=datetime(2024, 1, 12, tzinfo=timezone.utc),
    )
    result = await engine.run()

    trades = result.trade_log.get_trades()
    metrics = compute_metrics(
        trades=trades, equity_curve=result.equity_curve, initial_equity=10000,
    )
    gen = ReportGenerator(
        trades=trades, metrics=metrics,
        equity_curve=result.equity_curve, timestamps=result.timestamps,
    )

    # CSV
    csv_path = str(tmp_path / "trades.csv")
    gen.export_csv(csv_path)
    assert os.path.exists(csv_path)

    # HTML
    html_path = str(tmp_path / "report.html")
    gen.generate_html(html_path)
    assert os.path.exists(html_path)
```

- [ ] **Step 2: Run integration test**

Run: `pytest tests/test_backtest_integration.py -v`
Expected: All tests PASS

- [ ] **Step 3: Run full test suite for final regression check**

Run: `pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_backtest_integration.py
git commit -m "test: add integration tests for full backtest pipeline with SignalEngine"
```
