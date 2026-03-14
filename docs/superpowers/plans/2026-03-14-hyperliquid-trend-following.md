# Hyperliquid Trend Following Strategy — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully automated, event-driven trading bot that runs multi-asset trend following on Hyperliquid perpetual futures, targeting small accounts (<$10K).

**Architecture:** Event-driven system built on Python asyncio. All components communicate through a central event bus via publish/subscribe — no direct dependencies between components. SQLite for persistence, Hyperliquid SDK for exchange connectivity, Telegram for alerts.

**Tech Stack:** Python 3.11+, asyncio, hyperliquid-python-sdk, pandas, numpy, ta (Technical Analysis), aiosqlite, python-telegram-bot, structlog, Docker

**Spec:** `docs/superpowers/specs/2026-03-14-hyperliquid-trend-following-design.md`

---

## File Structure

```
hyperquant/
├── pyproject.toml                # Project metadata & dependencies
├── config.yaml                   # Strategy parameters (all tunables)
├── .gitignore
├── .env.example                  # Template for secrets
├── main.py                       # Entry point — wires components, starts event loop
├── core/
│   ├── __init__.py
│   ├── event_bus.py              # Async pub/sub event bus
│   └── events.py                 # All event & data dataclasses
├── data/
│   ├── __init__.py
│   ├── feeder.py                 # Hyperliquid WS/REST data fetching
│   ├── store.py                  # SQLite persistence (candles, trades, positions, logs)
│   └── symbol_filter.py          # Symbol pool screening (volume, listing age)
├── strategy/
│   ├── __init__.py
│   ├── indicators.py             # Pure functions: EMA, RSI, MACD, Donchian, ATR
│   ├── scorer.py                 # Trend scoring (0-100) across 3 dimensions
│   └── signal_engine.py          # Subscribes MarketData, emits SignalEvent/CloseSignalEvent
├── execution/
│   ├── __init__.py
│   ├── position_sizer.py         # ATR-adaptive position sizing math
│   ├── risk_manager.py           # Validates signals against risk rules
│   └── order_executor.py         # Hyperliquid SDK order placement & fill handling
├── portfolio/
│   ├── __init__.py
│   └── tracker.py                # Position tracking, trailing stop, exit logic
├── notify/
│   ├── __init__.py
│   └── telegram.py               # Telegram bot notifications
├── utils/
│   ├── __init__.py
│   ├── logger.py                 # structlog setup
│   └── config.py                 # YAML config loading & validation
├── tests/
│   ├── __init__.py
│   ├── test_event_bus.py
│   ├── test_events.py
│   ├── test_store.py
│   ├── test_symbol_filter.py
│   ├── test_indicators.py
│   ├── test_scorer.py
│   ├── test_signal_engine.py
│   ├── test_position_sizer.py
│   ├── test_risk_manager.py
│   ├── test_order_executor.py
│   ├── test_tracker.py
│   └── test_config.py
├── Dockerfile
└── docker-compose.yaml
```

---

## Chunk 1: Project Foundation & Core Infrastructure

### Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config.yaml`
- Create: `utils/config.py`
- Create: `utils/__init__.py`
- Test: `tests/test_config.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
__pycache__/
*.pyc
*.pyo
.env
*.db
*.sqlite
.venv/
dist/
*.egg-info/
logs/
.pytest_cache/
.mypy_cache/
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "hyperquant"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "hyperliquid-python-sdk>=0.4",
    "pandas>=2.0",
    "numpy>=1.24",
    "ta>=0.11",
    "aiosqlite>=0.19",
    "python-telegram-bot>=21.0",
    "structlog>=24.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 3: Create `.env.example`**

```env
HYPERLIQUID_PRIVATE_KEY=your_private_key_here
TELEGRAM_BOT_TOKEN=your_bot_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

- [ ] **Step 4: Create `config.yaml`**

Copy the full config schema from the spec (Section 7 — `config.yaml` complete example). This is the single source of truth for all tunables.

```yaml
exchange:
  network: "testnet"
  slippage_tolerance: 0.001
  order_timeout_sec: 30

data:
  min_volume_24h: 1000000
  min_listing_days: 7
  warmup_candles: 200
  pool_refresh_interval: 300

strategy:
  primary_timeframe: "1h"
  confirm_timeframe: "4h"
  score_threshold: 65
  max_new_positions: 3
  ema_fast: 20
  ema_slow: 60
  rsi_period: 14
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  donchian_period: 20
  atr_period: 14
  exit_score_threshold: 30

risk:
  risk_per_trade: 0.02
  max_open_positions: 5
  max_single_exposure: 0.20
  max_total_exposure: 0.80
  max_leverage: 3.0
  max_daily_loss: 0.05
  consecutive_loss_limit: 5
  cooldown_hours: 24

stop_loss:
  initial_atr_multiple: 2.0
  take_profit_atr_multiple: 3.0
  breakeven_trigger_atr: 1.0
  trailing_trigger_atr: 2.0
  trailing_distance_atr: 1.5

notify:
  enabled: true
  daily_report_hour: 8

logging:
  level: "INFO"
  file: "logs/hyperquant.log"
  max_size_mb: 50
  backup_count: 5
```

- [ ] **Step 5: Create `utils/__init__.py` and `tests/__init__.py`**

Both empty files.

- [ ] **Step 6: Write the failing test for config loading**

Create `tests/test_config.py`:

```python
import pytest
from pathlib import Path
from utils.config import load_config


def test_load_config_returns_all_sections(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("""
exchange:
  network: "testnet"
  slippage_tolerance: 0.001
  order_timeout_sec: 30
data:
  min_volume_24h: 1000000
  min_listing_days: 7
  warmup_candles: 200
  pool_refresh_interval: 300
strategy:
  primary_timeframe: "1h"
  confirm_timeframe: "4h"
  score_threshold: 65
  max_new_positions: 3
  ema_fast: 20
  ema_slow: 60
  rsi_period: 14
  macd_fast: 12
  macd_slow: 26
  macd_signal: 9
  donchian_period: 20
  atr_period: 14
  exit_score_threshold: 30
risk:
  risk_per_trade: 0.02
  max_open_positions: 5
  max_single_exposure: 0.20
  max_total_exposure: 0.80
  max_leverage: 3.0
  max_daily_loss: 0.05
  consecutive_loss_limit: 5
  cooldown_hours: 24
stop_loss:
  initial_atr_multiple: 2.0
  take_profit_atr_multiple: 3.0
  breakeven_trigger_atr: 1.0
  trailing_trigger_atr: 2.0
  trailing_distance_atr: 1.5
notify:
  enabled: true
  daily_report_hour: 8
logging:
  level: "INFO"
  file: "logs/hyperquant.log"
  max_size_mb: 50
  backup_count: 5
""")
    config = load_config(str(cfg_file))
    assert config["exchange"]["network"] == "testnet"
    assert config["strategy"]["ema_fast"] == 20
    assert config["risk"]["max_open_positions"] == 5
    assert config["stop_loss"]["trailing_distance_atr"] == 1.5


def test_load_config_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_config("/nonexistent/config.yaml")


def test_load_config_missing_section_raises(tmp_path):
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text("exchange:\n  network: testnet\n")
    with pytest.raises(KeyError, match="strategy"):
        load_config(str(cfg_file))
```

- [ ] **Step 7: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'utils.config'`

- [ ] **Step 8: Implement `utils/config.py`**

```python
from pathlib import Path
import yaml

REQUIRED_SECTIONS = [
    "exchange", "data", "strategy", "risk", "stop_loss", "notify", "logging"
]


def load_config(path: str) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    for section in REQUIRED_SECTIONS:
        if section not in config:
            raise KeyError(f"Missing required config section: {section}")

    return config
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `python -m pytest tests/test_config.py -v`
Expected: 3 passed

- [ ] **Step 10: Commit**

```bash
git add .gitignore pyproject.toml .env.example config.yaml utils/ tests/
git commit -m "feat: project scaffolding with config loading"
```

---

### Task 2: Event Definitions

**Files:**
- Create: `core/__init__.py`
- Create: `core/events.py`
- Test: `tests/test_events.py`

- [ ] **Step 1: Create `core/__init__.py`**

Empty file.

- [ ] **Step 2: Write the failing test for events**

Create `tests/test_events.py`:

```python
from core.events import (
    Candle, MarketDataEvent, SignalEvent, OrderRequestEvent,
    OrderFilledEvent, PortfolioUpdateEvent, CloseSignalEvent,
)


def test_candle_creation():
    c = Candle(open=100.0, high=105.0, low=99.0, close=103.0, volume=1000.0, timestamp=1700000000000)
    assert c.close == 103.0
    assert c.timestamp == 1700000000000


def test_signal_event_fields():
    sig = SignalEvent(
        symbol="BTC", direction="long", score=78.5,
        entry_price=50000.0, atr=1500.0,
        stop_loss=47000.0, take_profit=54500.0,
        timestamp=1700000000000,
    )
    assert sig.direction == "long"
    assert sig.score == 78.5


def test_order_request_event_fields():
    ore = OrderRequestEvent(
        symbol="ETH", direction="short", action="open",
        size=1.5, order_type="limit", limit_price=3000.0,
        stop_loss=3300.0, take_profit=2550.0,
        reason="trend score 72", timestamp=1700000000000,
    )
    assert ore.action == "open"
    assert ore.limit_price == 3000.0


def test_market_data_event_with_candle_list():
    candles = [
        Candle(open=100, high=105, low=99, close=103, volume=1000, timestamp=1000),
        Candle(open=103, high=108, low=101, close=107, volume=1200, timestamp=2000),
    ]
    mde = MarketDataEvent(symbol="BTC", timeframe="1h", candles=candles, timestamp=3000)
    assert mde.symbol == "BTC"
    assert len(mde.candles) == 2
    assert mde.candles[0].close == 103


def test_order_filled_event_fields():
    ofe = OrderFilledEvent(
        symbol="ETH", direction="long", action="open",
        filled_size=1.5, filled_price=3000.0,
        order_id="ord_abc", fee=3.0, timestamp=1700000000000,
    )
    assert ofe.order_id == "ord_abc"
    assert ofe.fee == 3.0


def test_portfolio_update_event_fields():
    pue = PortfolioUpdateEvent(
        symbol="BTC", unrealized_pnl=500.0, current_price=50500.0,
        stop_loss=47000.0, take_profit=54500.0, timestamp=1700000000000,
    )
    assert pue.unrealized_pnl == 500.0


def test_order_request_with_none_limit_price():
    ore = OrderRequestEvent(
        symbol="ETH", direction="long", action="open",
        size=1.0, order_type="market", limit_price=None,
        stop_loss=2700.0, take_profit=3450.0,
        reason="market order", timestamp=1700000000000,
    )
    assert ore.limit_price is None


def test_close_signal_event_fields():
    cse = CloseSignalEvent(
        symbol="BTC", reason="trailing_stop",
        close_price=52000.0, timestamp=1700000000000,
    )
    assert cse.reason == "trailing_stop"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `python -m pytest tests/test_events.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.events'`

- [ ] **Step 4: Implement `core/events.py`**

```python
from dataclasses import dataclass


@dataclass
class Candle:
    open: float
    high: float
    low: float
    close: float
    volume: float
    timestamp: float  # Unix timestamp (ms)


@dataclass
class MarketDataEvent:
    symbol: str
    timeframe: str  # "1h" | "4h"
    candles: list[Candle]
    timestamp: float


@dataclass
class SignalEvent:
    symbol: str
    direction: str  # "long" | "short"
    score: float  # 0-100
    entry_price: float
    atr: float
    stop_loss: float
    take_profit: float
    timestamp: float


@dataclass
class OrderRequestEvent:
    symbol: str
    direction: str  # "long" | "short"
    action: str  # "open" | "close"
    size: float
    order_type: str  # "limit" | "market"
    limit_price: float | None
    stop_loss: float
    take_profit: float
    reason: str
    timestamp: float


@dataclass
class OrderFilledEvent:
    symbol: str
    direction: str
    action: str  # "open" | "close"
    filled_size: float
    filled_price: float
    order_id: str
    fee: float
    timestamp: float


@dataclass
class PortfolioUpdateEvent:
    symbol: str
    unrealized_pnl: float
    current_price: float
    stop_loss: float
    take_profit: float
    timestamp: float


@dataclass
class CloseSignalEvent:
    symbol: str
    reason: str  # "stop_loss" | "take_profit" | "trailing_stop" | "trend_reversal"
    close_price: float
    timestamp: float
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_events.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add core/ tests/test_events.py
git commit -m "feat: define event dataclasses for all system events"
```

---

### Task 3: Event Bus

**Files:**
- Create: `core/event_bus.py`
- Test: `tests/test_event_bus.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_event_bus.py`:

```python
import asyncio
import pytest
from core.event_bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


async def test_subscribe_and_publish(bus):
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("test_event", handler)
    await bus.publish("test_event", {"data": 42})

    assert len(received) == 1
    assert received[0] == {"data": 42}


async def test_multiple_subscribers(bus):
    results_a = []
    results_b = []

    async def handler_a(event):
        results_a.append(event)

    async def handler_b(event):
        results_b.append(event)

    bus.subscribe("evt", handler_a)
    bus.subscribe("evt", handler_b)
    await bus.publish("evt", "hello")

    assert results_a == ["hello"]
    assert results_b == ["hello"]


async def test_publish_no_subscribers_is_noop(bus):
    await bus.publish("nobody_listening", {"x": 1})  # Should not raise


async def test_handler_exception_does_not_block_others(bus):
    results = []

    async def bad_handler(event):
        raise ValueError("boom")

    async def good_handler(event):
        results.append(event)

    bus.subscribe("evt", bad_handler)
    bus.subscribe("evt", good_handler)
    await bus.publish("evt", "data")

    assert results == ["data"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_event_bus.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'core.event_bus'`

- [ ] **Step 3: Implement `core/event_bus.py`**

```python
import asyncio
import logging
from collections import defaultdict
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)

Handler = Callable[[Any], Coroutine[Any, Any, None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_type: str, handler: Handler) -> None:
        self._subscribers[event_type].append(handler)

    async def publish(self, event_type: str, event: Any) -> None:
        for handler in self._subscribers[event_type]:
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "Handler %s failed for event %s", handler.__name__, event_type
                )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_event_bus.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add core/event_bus.py tests/test_event_bus.py
git commit -m "feat: async event bus with error-isolated handlers"
```

---

### Task 4: Logger Setup

**Files:**
- Create: `utils/logger.py`

- [ ] **Step 1: Implement `utils/logger.py`**

No tests needed — thin wrapper around structlog configuration.

```python
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog


def setup_logging(config: dict) -> None:
    log_cfg = config["logging"]
    level = getattr(logging, log_cfg["level"].upper(), logging.INFO)

    # Ensure log directory exists
    log_file = Path(log_cfg["file"])
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Standard library logging
    root = logging.getLogger()
    root.setLevel(level)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    root.addHandler(console)

    # Rotating file handler
    file_handler = RotatingFileHandler(
        log_cfg["file"],
        maxBytes=log_cfg["max_size_mb"] * 1024 * 1024,
        backupCount=log_cfg["backup_count"],
    )
    file_handler.setLevel(level)
    root.addHandler(file_handler)

    # structlog configuration
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
    )
```

- [ ] **Step 2: Verify module imports cleanly**

Run: `python -c "from utils.logger import setup_logging; print('OK')"`
Expected: Prints `OK` without errors.

- [ ] **Step 3: Commit**

---

## Chunk 2: Data Layer

### Task 5: SQLite Store

**Files:**
- Create: `data/__init__.py`
- Create: `data/store.py`
- Test: `tests/test_store.py`

- [ ] **Step 1: Create `data/__init__.py`**

Empty file.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_store.py`:

```python
import pytest
from core.events import Candle, OrderFilledEvent
from data.store import Store


@pytest.fixture
async def store(tmp_path):
    db_path = str(tmp_path / "test.db")
    s = Store(db_path)
    await s.initialize()
    yield s
    await s.close()


async def test_save_and_load_candles(store):
    candles = [
        Candle(open=100, high=105, low=99, close=103, volume=1000, timestamp=1000),
        Candle(open=103, high=108, low=101, close=107, volume=1200, timestamp=2000),
    ]
    await store.save_candles("BTC", "1h", candles)
    loaded = await store.load_candles("BTC", "1h", limit=10)
    assert len(loaded) == 2
    assert loaded[0].open == 100
    assert loaded[1].close == 107


async def test_load_candles_respects_limit(store):
    candles = [
        Candle(open=i, high=i+1, low=i-1, close=i, volume=100, timestamp=i * 1000)
        for i in range(10)
    ]
    await store.save_candles("ETH", "1h", candles)
    loaded = await store.load_candles("ETH", "1h", limit=3)
    assert len(loaded) == 3
    # Should return the latest 3
    assert loaded[-1].timestamp == 9000


async def test_save_candles_upserts_on_duplicate(store):
    c1 = Candle(open=100, high=105, low=99, close=103, volume=1000, timestamp=1000)
    await store.save_candles("BTC", "1h", [c1])
    c1_updated = Candle(open=100, high=106, low=99, close=104, volume=1100, timestamp=1000)
    await store.save_candles("BTC", "1h", [c1_updated])
    loaded = await store.load_candles("BTC", "1h", limit=10)
    assert len(loaded) == 1
    assert loaded[0].close == 104


async def test_record_and_list_trades(store):
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000, order_id="abc123",
        fee=5.0, timestamp=1000,
    )
    await store.record_trade(fill)
    trades = await store.list_trades(symbol="BTC", limit=10)
    assert len(trades) == 1
    assert trades[0]["order_id"] == "abc123"


async def test_save_and_load_position(store):
    pos = {
        "symbol": "ETH", "direction": "long", "size": 1.5,
        "entry_price": 3000, "stop_loss": 2700, "take_profit": 3450,
        "timestamp": 1000,
    }
    await store.save_position(pos)
    loaded = await store.load_positions()
    assert len(loaded) == 1
    assert loaded[0]["symbol"] == "ETH"


async def test_remove_position(store):
    pos = {
        "symbol": "ETH", "direction": "long", "size": 1.5,
        "entry_price": 3000, "stop_loss": 2700, "take_profit": 3450,
        "timestamp": 1000,
    }
    await store.save_position(pos)
    await store.remove_position("ETH")
    loaded = await store.load_positions()
    assert len(loaded) == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data.store'`

- [ ] **Step 4: Implement `data/store.py`**

```python
import aiosqlite
from core.events import Candle, OrderFilledEvent

SCHEMA = """
CREATE TABLE IF NOT EXISTS candles (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    timestamp REAL NOT NULL,
    open REAL, high REAL, low REAL, close REAL, volume REAL,
    PRIMARY KEY (symbol, timeframe, timestamp)
);

CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    direction TEXT NOT NULL,
    action TEXT NOT NULL,
    filled_size REAL,
    filled_price REAL,
    order_id TEXT,
    fee REAL,
    timestamp REAL
);

CREATE TABLE IF NOT EXISTS positions (
    symbol TEXT PRIMARY KEY,
    direction TEXT NOT NULL,
    size REAL,
    entry_price REAL,
    stop_loss REAL,
    take_profit REAL,
    timestamp REAL
);

CREATE TABLE IF NOT EXISTS events_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    payload TEXT,
    timestamp REAL
);
"""


class Store:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self._db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    # --- Candles ---

    async def save_candles(self, symbol: str, timeframe: str, candles: list[Candle]) -> None:
        await self._db.executemany(
            """INSERT OR REPLACE INTO candles
               (symbol, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                (symbol, timeframe, c.timestamp, c.open, c.high, c.low, c.close, c.volume)
                for c in candles
            ],
        )
        await self._db.commit()

    async def load_candles(self, symbol: str, timeframe: str, limit: int = 200) -> list[Candle]:
        cursor = await self._db.execute(
            """SELECT open, high, low, close, volume, timestamp FROM (
                 SELECT open, high, low, close, volume, timestamp
                 FROM candles WHERE symbol = ? AND timeframe = ?
                 ORDER BY timestamp DESC LIMIT ?
               ) ORDER BY timestamp ASC""",
            (symbol, timeframe, limit),
        )
        rows = await cursor.fetchall()
        return [
            Candle(open=r[0], high=r[1], low=r[2], close=r[3], volume=r[4], timestamp=r[5])
            for r in rows
        ]

    # --- Trades ---

    async def record_trade(self, fill: OrderFilledEvent) -> None:
        await self._db.execute(
            """INSERT INTO trades (symbol, direction, action, filled_size,
               filled_price, order_id, fee, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (fill.symbol, fill.direction, fill.action, fill.filled_size,
             fill.filled_price, fill.order_id, fill.fee, fill.timestamp),
        )
        await self._db.commit()

    async def list_trades(self, symbol: str | None = None, limit: int = 50) -> list[dict]:
        if symbol:
            cursor = await self._db.execute(
                "SELECT * FROM trades WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
                (symbol, limit),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # --- Positions ---

    async def save_position(self, pos: dict) -> None:
        await self._db.execute(
            """INSERT OR REPLACE INTO positions
               (symbol, direction, size, entry_price, stop_loss, take_profit, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (pos["symbol"], pos["direction"], pos["size"], pos["entry_price"],
             pos["stop_loss"], pos["take_profit"], pos["timestamp"]),
        )
        await self._db.commit()

    async def remove_position(self, symbol: str) -> None:
        await self._db.execute("DELETE FROM positions WHERE symbol = ?", (symbol,))
        await self._db.commit()

    async def load_positions(self) -> list[dict]:
        cursor = await self._db.execute("SELECT * FROM positions")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # Note: events_log table methods (log_event, list_events) deferred to
    # integration phase. The schema is defined above for future use.
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_store.py -v`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add data/ tests/test_store.py
git commit -m "feat: SQLite store for candles, trades, and positions"
```

---

### Task 6: Symbol Filter

**Files:**
- Create: `data/symbol_filter.py`
- Test: `tests/test_symbol_filter.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_symbol_filter.py`:

```python
import time
from data.symbol_filter import filter_symbols


def test_filters_by_volume():
    tickers = [
        {"symbol": "BTC", "volume_24h": 5_000_000, "listing_time": 0},
        {"symbol": "SHIB", "volume_24h": 500_000, "listing_time": 0},
        {"symbol": "ETH", "volume_24h": 3_000_000, "listing_time": 0},
    ]
    result = filter_symbols(tickers, min_volume=1_000_000, min_listing_days=0)
    symbols = [t["symbol"] for t in result]
    assert "BTC" in symbols
    assert "ETH" in symbols
    assert "SHIB" not in symbols


def test_filters_by_listing_age():
    now = time.time()
    tickers = [
        {"symbol": "BTC", "volume_24h": 5_000_000, "listing_time": now - 30 * 86400},
        {"symbol": "NEW", "volume_24h": 5_000_000, "listing_time": now - 3 * 86400},
    ]
    result = filter_symbols(tickers, min_volume=1_000_000, min_listing_days=7)
    symbols = [t["symbol"] for t in result]
    assert "BTC" in symbols
    assert "NEW" not in symbols


def test_empty_input_returns_empty():
    assert filter_symbols([], min_volume=1_000_000, min_listing_days=7) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_symbol_filter.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data.symbol_filter'`

- [ ] **Step 3: Implement `data/symbol_filter.py`**

```python
import time


def filter_symbols(
    tickers: list[dict],
    min_volume: float,
    min_listing_days: int,
) -> list[dict]:
    now = time.time()
    min_listing_seconds = min_listing_days * 86400
    return [
        t for t in tickers
        if t["volume_24h"] >= min_volume
        and (now - t["listing_time"]) >= min_listing_seconds
    ]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_symbol_filter.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add data/symbol_filter.py tests/test_symbol_filter.py
git commit -m "feat: symbol pool filter by volume and listing age"
```

---

### Task 7: Data Feeder

**Files:**
- Create: `data/feeder.py`
- Test: `tests/test_feeder.py`

The feeder wraps Hyperliquid SDK calls. Tests use a mock client to avoid real API calls.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_feeder.py`:

```python
import time
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.event_bus import EventBus
from core.events import Candle
from data.feeder import DataFeeder


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def mock_client():
    client = AsyncMock()
    # Simulate candle response: list of dicts with OHLCV
    client.fetch_candles.return_value = [
        {"o": 100, "h": 105, "l": 99, "c": 103, "v": 1000, "t": 1000},
        {"o": 103, "h": 108, "l": 101, "c": 107, "v": 1200, "t": 2000},
    ]
    client.fetch_tickers.return_value = [
        {"symbol": "BTC", "volume_24h": 5_000_000, "listing_time": 0},
        {"symbol": "ETH", "volume_24h": 3_000_000, "listing_time": 0},
        {"symbol": "NEW", "volume_24h": 5_000_000, "listing_time": time.time() - 3 * 86400},  # 3 days old
    ]
    return client


async def test_fetch_candles_publishes_market_data_event(bus, mock_client):
    received = []

    async def handler(event):
        received.append(event)

    bus.subscribe("MarketDataEvent", handler)

    feeder = DataFeeder(bus=bus, client=mock_client, config={
        "data": {"warmup_candles": 200, "pool_refresh_interval": 300,
                 "min_volume_24h": 1_000_000, "min_listing_days": 7},
        "strategy": {"primary_timeframe": "1h", "confirm_timeframe": "4h"},
    })
    await feeder.fetch_and_publish_candles("BTC", "1h")

    assert len(received) == 1
    assert received[0].symbol == "BTC"
    assert received[0].timeframe == "1h"
    assert len(received[0].candles) == 2
    assert isinstance(received[0].candles[0], Candle)


async def test_fetch_tickers_returns_filtered_symbols(bus, mock_client):
    feeder = DataFeeder(bus=bus, client=mock_client, config={
        "data": {"warmup_candles": 200, "pool_refresh_interval": 300,
                 "min_volume_24h": 1_000_000, "min_listing_days": 7},
        "strategy": {"primary_timeframe": "1h", "confirm_timeframe": "4h"},
    })
    symbols = await feeder.refresh_symbol_pool()
    assert "BTC" in symbols
    assert "ETH" in symbols
    assert "NEW" not in symbols  # Filtered out: listed < 7 days ago
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_feeder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data.feeder'`

- [ ] **Step 3: Implement `data/feeder.py`**

```python
import logging
import time
from core.event_bus import EventBus
from core.events import Candle, MarketDataEvent
from data.symbol_filter import filter_symbols

logger = logging.getLogger(__name__)


class DataFeeder:
    def __init__(self, bus: EventBus, client, config: dict) -> None:
        self._bus = bus
        self._client = client
        self._config = config
        self._symbol_pool: list[str] = []

    async def fetch_and_publish_candles(self, symbol: str, timeframe: str) -> None:
        raw = await self._client.fetch_candles(symbol, timeframe)
        candles = [
            Candle(
                open=c["o"], high=c["h"], low=c["l"],
                close=c["c"], volume=c["v"], timestamp=c["t"],
            )
            for c in raw
        ]
        event = MarketDataEvent(
            symbol=symbol,
            timeframe=timeframe,
            candles=candles,
            timestamp=time.time() * 1000,
        )
        await self._bus.publish("MarketDataEvent", event)

    async def refresh_symbol_pool(self) -> list[str]:
        data_cfg = self._config["data"]
        tickers = await self._client.fetch_tickers()
        filtered = filter_symbols(
            tickers,
            min_volume=data_cfg["min_volume_24h"],
            min_listing_days=data_cfg["min_listing_days"],
        )
        self._symbol_pool = [t["symbol"] for t in filtered]
        logger.info("Symbol pool refreshed: %d symbols", len(self._symbol_pool))
        return self._symbol_pool

    @property
    def symbol_pool(self) -> list[str]:
        return self._symbol_pool
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_feeder.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add data/feeder.py tests/test_feeder.py
git commit -m "feat: data feeder with candle publishing and symbol pool refresh"
```

---

## Chunk 3: Strategy Engine

### Task 8: Technical Indicators

**Files:**
- Create: `strategy/__init__.py`
- Create: `strategy/indicators.py`
- Test: `tests/test_indicators.py`

All indicator functions are pure: they take a pandas Series (or list of floats) and return computed values. No side effects, no event bus dependency.

- [ ] **Step 1: Create `strategy/__init__.py`**

Empty file.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_indicators.py`:

```python
import numpy as np
import pytest
from strategy.indicators import compute_ema, compute_rsi, compute_macd, compute_donchian, compute_atr


def _make_prices(n=100, start=100.0, trend=0.5, noise=2.0):
    """Generate synthetic price series with upward trend + noise."""
    np.random.seed(42)
    return [start + i * trend + np.random.randn() * noise for i in range(n)]


def _make_ohlcv(closes, spread=2.0):
    """Generate OHLCV lists from close prices."""
    highs = [c + abs(spread * np.random.randn()) for c in closes]
    lows = [c - abs(spread * np.random.randn()) for c in closes]
    opens = [closes[0]] + closes[:-1]
    volumes = [1000.0] * len(closes)
    return opens, highs, lows, closes, volumes


class TestEMA:
    def test_ema_length_matches_input(self):
        prices = _make_prices(50)
        result = compute_ema(prices, period=20)
        assert len(result) == len(prices)

    def test_ema_first_values_are_nan(self):
        prices = _make_prices(50)
        result = compute_ema(prices, period=20)
        assert np.isnan(result[0])

    def test_ema_tracks_uptrend(self):
        prices = _make_prices(100, trend=1.0, noise=0.1)
        result = compute_ema(prices, period=20)
        # EMA should be below price in uptrend (lagging)
        assert result[-1] < prices[-1]


class TestRSI:
    def test_rsi_range(self):
        prices = _make_prices(100)
        result = compute_rsi(prices, period=14)
        valid = [v for v in result if not np.isnan(v)]
        assert all(0 <= v <= 100 for v in valid)

    def test_rsi_uptrend_above_50(self):
        prices = _make_prices(100, trend=2.0, noise=0.1)
        result = compute_rsi(prices, period=14)
        assert result[-1] > 50


class TestMACD:
    def test_macd_returns_three_series(self):
        prices = _make_prices(100)
        macd_line, signal_line, histogram = compute_macd(prices, fast=12, slow=26, signal=9)
        assert len(macd_line) == len(prices)
        assert len(signal_line) == len(prices)
        assert len(histogram) == len(prices)

    def test_histogram_is_macd_minus_signal(self):
        prices = _make_prices(100)
        macd_line, signal_line, histogram = compute_macd(prices, fast=12, slow=26, signal=9)
        # Check last value where both are valid
        idx = -1
        if not np.isnan(macd_line[idx]) and not np.isnan(signal_line[idx]):
            assert abs(histogram[idx] - (macd_line[idx] - signal_line[idx])) < 1e-10


class TestDonchian:
    def test_donchian_channel(self):
        np.random.seed(42)
        highs = [100 + i + abs(np.random.randn()) for i in range(30)]
        lows = [100 + i - abs(np.random.randn()) for i in range(30)]
        upper, lower = compute_donchian(highs, lows, period=20)
        assert len(upper) == 30
        # Upper channel should be >= last high in the window
        assert upper[-1] >= max(highs[-20:]) - 1e-10


class TestATR:
    def test_atr_positive(self):
        np.random.seed(42)
        closes = _make_prices(50)
        opens, highs, lows, closes, _ = _make_ohlcv(closes)
        result = compute_atr(highs, lows, closes, period=14)
        valid = [v for v in result if not np.isnan(v)]
        assert all(v > 0 for v in valid)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.indicators'`

- [ ] **Step 4: Implement `strategy/indicators.py`**

```python
import numpy as np


def compute_ema(prices: list[float], period: int) -> list[float]:
    result = [float("nan")] * len(prices)
    if len(prices) < period:
        return result
    # SMA for initial value
    result[period - 1] = sum(prices[:period]) / period
    multiplier = 2.0 / (period + 1)
    for i in range(period, len(prices)):
        result[i] = (prices[i] - result[i - 1]) * multiplier + result[i - 1]
    return result


def compute_rsi(prices: list[float], period: int = 14) -> list[float]:
    result = [float("nan")] * len(prices)
    if len(prices) < period + 1:
        return result
    deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
    gains = [max(d, 0) for d in deltas]
    losses = [max(-d, 0) for d in deltas]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    if avg_loss == 0:
        result[period] = 100.0
    else:
        rs = avg_gain / avg_loss
        result[period] = 100 - (100 / (1 + rs))

    for i in range(period + 1, len(prices)):
        idx = i - 1  # delta index
        avg_gain = (avg_gain * (period - 1) + gains[idx]) / period
        avg_loss = (avg_loss * (period - 1) + losses[idx]) / period
        if avg_loss == 0:
            result[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            result[i] = 100 - (100 / (1 + rs))
    return result


def compute_macd(
    prices: list[float], fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[list[float], list[float], list[float]]:
    ema_fast = compute_ema(prices, fast)
    ema_slow = compute_ema(prices, slow)
    macd_line = [
        f - s if not (np.isnan(f) or np.isnan(s)) else float("nan")
        for f, s in zip(ema_fast, ema_slow)
    ]
    # Compute signal line from valid MACD values only
    valid_start = slow - 1  # first valid MACD index
    macd_valid = [macd_line[i] for i in range(valid_start, len(macd_line))]
    signal_computed = compute_ema(macd_valid, signal)
    signal_line = [float("nan")] * valid_start + signal_computed

    histogram = [
        m - s if not (np.isnan(m) or np.isnan(s)) else float("nan")
        for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, histogram


def compute_donchian(
    highs: list[float], lows: list[float], period: int = 20
) -> tuple[list[float], list[float]]:
    upper = [float("nan")] * len(highs)
    lower = [float("nan")] * len(lows)
    for i in range(period - 1, len(highs)):
        upper[i] = max(highs[i - period + 1 : i + 1])
        lower[i] = min(lows[i - period + 1 : i + 1])
    return upper, lower


def compute_atr(
    highs: list[float], lows: list[float], closes: list[float], period: int = 14
) -> list[float]:
    result = [float("nan")] * len(closes)
    if len(closes) < 2:
        return result
    true_ranges = [highs[0] - lows[0]]
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        true_ranges.append(tr)

    if len(true_ranges) < period:
        return result
    result[period - 1] = sum(true_ranges[:period]) / period
    for i in range(period, len(true_ranges)):
        result[i] = (result[i - 1] * (period - 1) + true_ranges[i]) / period
    return result
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_indicators.py -v`
Expected: 8 passed

- [ ] **Step 6: Commit**

```bash
git add strategy/ tests/test_indicators.py
git commit -m "feat: pure indicator functions (EMA, RSI, MACD, Donchian, ATR)"
```

---

### Task 9: Trend Scorer

**Files:**
- Create: `strategy/scorer.py`
- Test: `tests/test_scorer.py`

Scores each symbol 0-100 across three dimensions: trend direction (40%), momentum (35%), breakout confirmation (25%). Per spec Section 3.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scorer.py`:

```python
import numpy as np
import pytest
from strategy.scorer import compute_trend_score


def _uptrend_candles(n=100, start=100.0, step=1.0):
    """Generate strongly trending-up OHLCV data."""
    closes = [start + i * step for i in range(n)]
    highs = [c + 2 for c in closes]
    lows = [c - 1 for c in closes]
    opens = [closes[0]] + closes[:-1]
    volumes = [1000.0] * n
    return opens, highs, lows, closes, volumes


def _downtrend_candles(n=100, start=200.0, step=1.0):
    closes = [start - i * step for i in range(n)]
    highs = [c + 1 for c in closes]
    lows = [c - 2 for c in closes]
    opens = [closes[0]] + closes[:-1]
    volumes = [1000.0] * n
    return opens, highs, lows, closes, volumes


def _flat_candles(n=100, price=100.0):
    np.random.seed(42)
    closes = [price + np.random.randn() * 0.1 for _ in range(n)]
    highs = [c + 0.5 for c in closes]
    lows = [c - 0.5 for c in closes]
    opens = closes[:]
    volumes = [1000.0] * n
    return opens, highs, lows, closes, volumes


class TestTrendScore:
    def test_strong_uptrend_high_score(self):
        opens, highs, lows, closes, volumes = _uptrend_candles()
        score, direction = compute_trend_score(
            opens, highs, lows, closes,
            ema_fast=20, ema_slow=60, rsi_period=14,
            macd_fast=12, macd_slow=26, macd_signal=9,
            donchian_period=20,
        )
        assert score > 60
        assert direction == "long"

    def test_strong_downtrend_high_score_short(self):
        opens, highs, lows, closes, volumes = _downtrend_candles()
        score, direction = compute_trend_score(
            opens, highs, lows, closes,
            ema_fast=20, ema_slow=60, rsi_period=14,
            macd_fast=12, macd_slow=26, macd_signal=9,
            donchian_period=20,
        )
        assert score > 60
        assert direction == "short"

    def test_flat_market_low_score(self):
        opens, highs, lows, closes, volumes = _flat_candles()
        score, direction = compute_trend_score(
            opens, highs, lows, closes,
            ema_fast=20, ema_slow=60, rsi_period=14,
            macd_fast=12, macd_slow=26, macd_signal=9,
            donchian_period=20,
        )
        assert score < 50

    def test_score_bounded_0_100(self):
        for factory in [_uptrend_candles, _downtrend_candles, _flat_candles]:
            opens, highs, lows, closes, volumes = factory()
            score, _ = compute_trend_score(
                opens, highs, lows, closes,
                ema_fast=20, ema_slow=60, rsi_period=14,
                macd_fast=12, macd_slow=26, macd_signal=9,
                donchian_period=20,
            )
            assert 0 <= score <= 100
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_scorer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.scorer'`

- [ ] **Step 3: Implement `strategy/scorer.py`**

```python
import numpy as np
from strategy.indicators import compute_ema, compute_rsi, compute_macd, compute_donchian

# Weights per spec Section 3
WEIGHT_TREND = 0.40
WEIGHT_MOMENTUM = 0.35
WEIGHT_BREAKOUT = 0.25


def compute_trend_score(
    opens: list[float],
    highs: list[float],
    lows: list[float],
    closes: list[float],
    ema_fast: int = 20,
    ema_slow: int = 60,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    donchian_period: int = 20,
) -> tuple[float, str]:
    """Return (score 0-100, direction 'long'|'short')."""
    ema_f = compute_ema(closes, ema_fast)
    ema_s = compute_ema(closes, ema_slow)
    rsi = compute_rsi(closes, rsi_period)
    macd_line, signal_line, histogram = compute_macd(closes, macd_fast, macd_slow, macd_signal)
    don_upper, don_lower = compute_donchian(highs, lows, donchian_period)

    # Use last valid values
    ef = ema_f[-1]
    es = ema_s[-1]
    if np.isnan(ef) or np.isnan(es):
        return 0.0, "long"

    # Determine direction from EMA cross
    is_long = ef > es

    # --- Trend direction score (0-100) ---
    ema_gap = abs(ef - es) / es * 100  # gap as percentage
    # Check if gap is expanding (compare to 5 bars ago)
    prev_gap = abs(ema_f[-5] - ema_s[-5]) / ema_s[-5] * 100 if not np.isnan(ema_f[-5]) else 0
    expanding = ema_gap > prev_gap
    trend_score = min(ema_gap * 20, 100)  # Scale: 5% gap = 100
    if expanding:
        trend_score = min(trend_score * 1.2, 100)

    # --- Momentum score (0-100) ---
    rsi_val = rsi[-1] if not np.isnan(rsi[-1]) else 50
    hist_val = histogram[-1] if not np.isnan(histogram[-1]) else 0

    if is_long:
        # RSI 50-70 is ideal for long momentum
        if 50 <= rsi_val <= 70:
            rsi_score = 100 - abs(rsi_val - 60) * 5
        elif rsi_val > 70:
            rsi_score = max(100 - (rsi_val - 70) * 5, 20)
        else:
            rsi_score = max(rsi_val * 2 - 20, 0)
        hist_score = min(max(hist_val / (abs(closes[-1]) * 0.001 + 1e-10) * 10, 0), 100)
    else:
        # RSI 30-50 is ideal for short momentum
        if 30 <= rsi_val <= 50:
            rsi_score = 100 - abs(rsi_val - 40) * 5
        elif rsi_val < 30:
            rsi_score = max(100 - (30 - rsi_val) * 5, 20)
        else:
            rsi_score = max((100 - rsi_val) * 2 - 20, 0)
        hist_score = min(max(-hist_val / (abs(closes[-1]) * 0.001 + 1e-10) * 10, 0), 100)

    momentum_score = (rsi_score + hist_score) / 2

    # --- Breakout score (0-100) ---
    du = don_upper[-1] if not np.isnan(don_upper[-1]) else closes[-1]
    dl = don_lower[-1] if not np.isnan(don_lower[-1]) else closes[-1]
    if is_long:
        breakout_score = 100 if closes[-1] >= du else max((1 - (du - closes[-1]) / (du - dl + 1e-10)) * 100, 0)
    else:
        breakout_score = 100 if closes[-1] <= dl else max((1 - (closes[-1] - dl) / (du - dl + 1e-10)) * 100, 0)

    # Weighted total
    total = (
        trend_score * WEIGHT_TREND
        + momentum_score * WEIGHT_MOMENTUM
        + breakout_score * WEIGHT_BREAKOUT
    )
    total = max(0, min(100, total))
    direction = "long" if is_long else "short"
    return round(total, 2), direction
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_scorer.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add strategy/scorer.py tests/test_scorer.py
git commit -m "feat: trend scoring engine with 3-dimension weighted scoring"
```

---

### Task 10: Signal Engine

**Files:**
- Create: `strategy/signal_engine.py`
- Test: `tests/test_signal_engine.py`

The signal engine subscribes to `MarketDataEvent`, computes scores for each symbol, and emits `SignalEvent` or `CloseSignalEvent`. It is the bridge between raw market data and trading decisions.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_signal_engine.py`:

```python
import pytest
from core.event_bus import EventBus
from core.events import Candle, MarketDataEvent, SignalEvent, CloseSignalEvent
from strategy.signal_engine import SignalEngine


def _make_uptrend_candles(n=100, start=100.0):
    return [
        Candle(
            open=start + i - 0.5, high=start + i + 2,
            low=start + i - 1, close=start + i,
            volume=1000, timestamp=i * 3600000,
        )
        for i in range(n)
    ]


def _make_downtrend_candles(n=100, start=200.0):
    return [
        Candle(
            open=start - i + 0.5, high=start - i + 1,
            low=start - i - 2, close=start - i,
            volume=1000, timestamp=i * 3600000,
        )
        for i in range(n)
    ]


@pytest.fixture
def config():
    return {
        "strategy": {
            "primary_timeframe": "1h", "confirm_timeframe": "4h",
            "score_threshold": 65, "max_new_positions": 3,
            "ema_fast": 20, "ema_slow": 60, "rsi_period": 14,
            "macd_fast": 12, "macd_slow": 26, "macd_signal": 9,
            "donchian_period": 20, "atr_period": 14,
            "exit_score_threshold": 30,
        },
        "risk": {"max_open_positions": 5},
        "stop_loss": {
            "initial_atr_multiple": 2.0,
            "take_profit_atr_multiple": 3.0,
        },
    }


@pytest.fixture
def bus():
    return EventBus()


async def test_uptrend_emits_signal(bus, config):
    signals = []

    async def handler(event):
        signals.append(event)

    bus.subscribe("SignalEvent", handler)
    engine = SignalEngine(bus=bus, config=config)

    candles_1h = _make_uptrend_candles(100)
    candles_4h = _make_uptrend_candles(100)

    # Feed 4h data first for confirmation
    event_4h = MarketDataEvent(symbol="BTC", timeframe="4h", candles=candles_4h, timestamp=1000)
    await engine.on_market_data(event_4h)

    # Feed 1h data to trigger signal evaluation
    event_1h = MarketDataEvent(symbol="BTC", timeframe="1h", candles=candles_1h, timestamp=1000)
    await engine.on_market_data(event_1h)

    # With strong uptrend, should emit a long signal
    long_signals = [s for s in signals if s.direction == "long"]
    assert len(long_signals) >= 1
    assert long_signals[0].symbol == "BTC"
    assert long_signals[0].score > 0


async def test_no_signal_when_below_threshold(bus, config):
    config["strategy"]["score_threshold"] = 99  # Nearly impossible to reach
    signals = []

    async def handler(event):
        signals.append(event)

    bus.subscribe("SignalEvent", handler)
    engine = SignalEngine(bus=bus, config=config)

    candles = _make_uptrend_candles(100)
    event_4h = MarketDataEvent(symbol="BTC", timeframe="4h", candles=candles, timestamp=1000)
    await engine.on_market_data(event_4h)
    event_1h = MarketDataEvent(symbol="BTC", timeframe="1h", candles=candles, timestamp=1000)
    await engine.on_market_data(event_1h)

    assert len(signals) == 0


async def test_close_signal_on_trend_reversal(bus, config):
    close_signals = []

    async def handler(event):
        close_signals.append(event)

    bus.subscribe("CloseSignalEvent", handler)
    engine = SignalEngine(bus=bus, config=config)

    # Simulate existing position
    engine._open_positions.add("BTC")
    engine._position_directions["BTC"] = "long"

    # Feed downtrend data (reversal from long position)
    candles_down = _make_downtrend_candles(100)
    event_4h = MarketDataEvent(symbol="BTC", timeframe="4h", candles=candles_down, timestamp=1000)
    await engine.on_market_data(event_4h)
    event_1h = MarketDataEvent(symbol="BTC", timeframe="1h", candles=candles_down, timestamp=1000)
    await engine.on_market_data(event_1h)

    assert len(close_signals) >= 1
    assert close_signals[0].reason == "trend_reversal"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'strategy.signal_engine'`

- [ ] **Step 3: Implement `strategy/signal_engine.py`**

```python
import logging
import time
from core.event_bus import EventBus
from core.events import Candle, MarketDataEvent, SignalEvent, CloseSignalEvent
from strategy.scorer import compute_trend_score
from strategy.indicators import compute_atr

logger = logging.getLogger(__name__)


class SignalEngine:
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

        bus.subscribe("MarketDataEvent", self.on_market_data)
        bus.subscribe("OrderFilledEvent", self._on_order_filled)
        bus.subscribe("CloseSignalEvent", self._on_close_signal)

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
                await self._bus.publish("CloseSignalEvent", CloseSignalEvent(
                    symbol=symbol, reason="trend_reversal",
                    close_price=closes[-1], timestamp=time.time() * 1000,
                ))
                return
            if score < self._strat["exit_score_threshold"]:
                await self._bus.publish("CloseSignalEvent", CloseSignalEvent(
                    symbol=symbol, reason="trend_reversal",
                    close_price=closes[-1], timestamp=time.time() * 1000,
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
        if atr is None or atr <= 0:
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
            timestamp=time.time() * 1000,
        )
        logger.info("Signal: %s %s score=%.1f", symbol, direction, score)
        await self._bus.publish("SignalEvent", signal)

    async def _on_order_filled(self, event) -> None:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_signal_engine.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add strategy/signal_engine.py tests/test_signal_engine.py
git commit -m "feat: signal engine with multi-timeframe trend evaluation"
```

---

## Chunk 4: Risk Management & Order Execution

### Task 11: Position Sizer

**Files:**
- Create: `execution/__init__.py`
- Create: `execution/position_sizer.py`
- Test: `tests/test_position_sizer.py`

Pure math: given account equity, ATR, and risk config, compute position size. Per spec Section 4.

- [ ] **Step 1: Create `execution/__init__.py`**

Empty file.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_position_sizer.py`:

```python
import pytest
from execution.position_sizer import calculate_position_size


class TestPositionSizer:
    def test_basic_calculation(self):
        # $10K account, 2% risk ($200), ATR=$1500, stop=2*ATR
        result = calculate_position_size(
            equity=10_000, atr=1500, entry_price=50_000,
            risk_per_trade=0.02, sl_atr_multiple=2.0,
            max_single_exposure=0.20, max_leverage=3.0,
        )
        # risk_amount = 200, size = 200 / (2 * 1500) = 0.0667 BTC
        assert abs(result["size"] - 0.0667) < 0.001
        assert result["notional"] == pytest.approx(result["size"] * 50_000, rel=0.01)

    def test_capped_by_max_single_exposure(self):
        # Very low ATR would give huge position; should be capped by 20% exposure
        result = calculate_position_size(
            equity=10_000, atr=1.0, entry_price=100,
            risk_per_trade=0.02, sl_atr_multiple=2.0,
            max_single_exposure=0.20, max_leverage=3.0,
        )
        assert result["notional"] <= 10_000 * 0.20

    def test_capped_by_max_leverage(self):
        result = calculate_position_size(
            equity=1_000, atr=0.5, entry_price=10,
            risk_per_trade=0.02, sl_atr_multiple=2.0,
            max_single_exposure=1.0, max_leverage=3.0,
        )
        assert result["notional"] <= 1_000 * 3.0

    def test_zero_atr_returns_zero(self):
        result = calculate_position_size(
            equity=10_000, atr=0, entry_price=50_000,
            risk_per_trade=0.02, sl_atr_multiple=2.0,
            max_single_exposure=0.20, max_leverage=3.0,
        )
        assert result["size"] == 0
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_position_sizer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'execution.position_sizer'`

- [ ] **Step 4: Implement `execution/position_sizer.py`**

```python
def calculate_position_size(
    equity: float,
    atr: float,
    entry_price: float,
    risk_per_trade: float = 0.02,
    sl_atr_multiple: float = 2.0,
    max_single_exposure: float = 0.20,
    max_leverage: float = 3.0,
) -> dict:
    if atr <= 0 or entry_price <= 0 or equity <= 0:
        return {"size": 0, "notional": 0, "leverage": 0}

    risk_amount = equity * risk_per_trade
    size = risk_amount / (sl_atr_multiple * atr)
    notional = size * entry_price

    # Cap by max single exposure
    max_notional_exposure = equity * max_single_exposure
    if notional > max_notional_exposure:
        notional = max_notional_exposure
        size = notional / entry_price

    # Cap by max leverage
    max_notional_leverage = equity * max_leverage
    if notional > max_notional_leverage:
        notional = max_notional_leverage
        size = notional / entry_price

    leverage = notional / equity
    return {"size": round(size, 6), "notional": round(notional, 2), "leverage": round(leverage, 4)}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_position_sizer.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add execution/ tests/test_position_sizer.py
git commit -m "feat: ATR-adaptive position sizer with exposure and leverage caps"
```

---

### Task 12: Risk Manager

**Files:**
- Create: `execution/risk_manager.py`
- Test: `tests/test_risk_manager.py`

Subscribes to `SignalEvent`, validates against all risk rules (per spec Section 4), and emits `OrderRequestEvent` if approved.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_risk_manager.py`:

```python
import pytest
from core.event_bus import EventBus
from core.events import SignalEvent, OrderRequestEvent
from execution.risk_manager import RiskManager


@pytest.fixture
def config():
    return {
        "risk": {
            "risk_per_trade": 0.02,
            "max_open_positions": 5,
            "max_single_exposure": 0.20,
            "max_total_exposure": 0.80,
            "max_leverage": 3.0,
            "max_daily_loss": 0.05,
            "consecutive_loss_limit": 5,
            "cooldown_hours": 24,
        },
        "stop_loss": {
            "initial_atr_multiple": 2.0,
            "take_profit_atr_multiple": 3.0,
        },
    }


@pytest.fixture
def bus():
    return EventBus()


def _make_signal(symbol="BTC", direction="long", score=75, entry=50000, atr=1500):
    return SignalEvent(
        symbol=symbol, direction=direction, score=score,
        entry_price=entry, atr=atr,
        stop_loss=entry - 2 * atr if direction == "long" else entry + 2 * atr,
        take_profit=entry + 3 * atr if direction == "long" else entry - 3 * atr,
        timestamp=1000,
    )


async def test_valid_signal_emits_order_request(bus, config):
    orders = []

    async def handler(event):
        orders.append(event)

    bus.subscribe("OrderRequestEvent", handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    await rm.on_signal(_make_signal())

    assert len(orders) == 1
    assert orders[0].symbol == "BTC"
    assert orders[0].direction == "long"
    assert orders[0].size > 0


async def test_rejects_when_max_positions_reached(bus, config):
    orders = []

    async def handler(event):
        orders.append(event)

    bus.subscribe("OrderRequestEvent", handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    # Fill up positions
    for sym in ["A", "B", "C", "D", "E"]:
        rm._open_positions[sym] = {"notional": 1000, "direction": "long"}

    await rm.on_signal(_make_signal())
    assert len(orders) == 0  # Rejected


async def test_rejects_when_total_exposure_exceeded(bus, config):
    orders = []

    async def handler(event):
        orders.append(event)

    bus.subscribe("OrderRequestEvent", handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    # Near max total exposure (80% of 10K = 8K already used)
    rm._open_positions["ETH"] = {"notional": 8000, "direction": "long"}

    await rm.on_signal(_make_signal(entry=100, atr=1))
    # Should be rejected because adding any position exceeds 80% total exposure
    assert len(orders) == 0


async def test_rejects_during_daily_loss_breaker(bus, config):
    orders = []

    async def handler(event):
        orders.append(event)

    bus.subscribe("OrderRequestEvent", handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    rm._daily_loss = 600  # > 5% of 10K

    await rm.on_signal(_make_signal())
    assert len(orders) == 0


async def test_rejects_during_consecutive_loss_cooldown(bus, config):
    orders = []

    async def handler(event):
        orders.append(event)

    bus.subscribe("OrderRequestEvent", handler)
    rm = RiskManager(bus=bus, config=config, equity=10_000)
    rm._consecutive_losses = 5

    await rm.on_signal(_make_signal())
    assert len(orders) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_risk_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'execution.risk_manager'`

- [ ] **Step 3: Implement `execution/risk_manager.py`**

```python
import logging
import time
from core.event_bus import EventBus
from core.events import SignalEvent, OrderRequestEvent, OrderFilledEvent
from execution.position_sizer import calculate_position_size

logger = logging.getLogger(__name__)


class RiskManager:
    def __init__(self, bus: EventBus, config: dict, equity: float) -> None:
        self._bus = bus
        self._risk = config["risk"]
        self._sl_cfg = config["stop_loss"]
        self._equity = equity
        self._open_positions: dict[str, dict] = {}  # symbol -> {notional, direction}
        self._daily_loss: float = 0.0
        self._daily_reset_ts: float = 0.0
        self._consecutive_losses: int = 0
        self._cooldown_until: float = 0.0

        bus.subscribe("SignalEvent", self.on_signal)
        bus.subscribe("OrderFilledEvent", self._on_fill)

    def update_equity(self, equity: float) -> None:
        self._equity = equity

    async def on_signal(self, signal: SignalEvent) -> None:
        now = time.time()

        # Check cooldown from consecutive losses
        if self._consecutive_losses >= self._risk["consecutive_loss_limit"]:
            if now < self._cooldown_until:
                logger.warning("Risk: in cooldown, rejecting %s", signal.symbol)
                return
            else:
                self._consecutive_losses = 0  # Reset after cooldown

        # Check daily loss limit
        if self._daily_loss >= self._equity * self._risk["max_daily_loss"]:
            logger.warning("Risk: daily loss limit hit, rejecting %s", signal.symbol)
            return

        # Check max positions
        if len(self._open_positions) >= self._risk["max_open_positions"]:
            logger.warning("Risk: max positions reached, rejecting %s", signal.symbol)
            return

        # Check duplicate symbol
        if signal.symbol in self._open_positions:
            logger.warning("Risk: already have position in %s", signal.symbol)
            return

        # Calculate position size
        pos = calculate_position_size(
            equity=self._equity,
            atr=signal.atr,
            entry_price=signal.entry_price,
            risk_per_trade=self._risk["risk_per_trade"],
            sl_atr_multiple=self._sl_cfg["initial_atr_multiple"],
            max_single_exposure=self._risk["max_single_exposure"],
            max_leverage=self._risk["max_leverage"],
        )
        if pos["size"] <= 0:
            return

        # Check total exposure
        current_exposure = sum(p["notional"] for p in self._open_positions.values())
        max_total = self._equity * self._risk["max_total_exposure"]
        if current_exposure + pos["notional"] > max_total:
            # Reduce position to fit
            available = max_total - current_exposure
            if available <= 0:
                logger.warning("Risk: total exposure limit, rejecting %s", signal.symbol)
                return
            pos["notional"] = available
            pos["size"] = available / signal.entry_price

        order = OrderRequestEvent(
            symbol=signal.symbol,
            direction=signal.direction,
            action="open",
            size=pos["size"],
            order_type="limit",
            limit_price=signal.entry_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            reason=f"trend score {signal.score:.1f}",
            timestamp=time.time() * 1000,
        )
        logger.info("Risk approved: %s %s size=%.6f", signal.symbol, signal.direction, pos["size"])
        await self._bus.publish("OrderRequestEvent", order)

    async def _on_fill(self, event: OrderFilledEvent) -> None:
        if event.action == "open":
            self._open_positions[event.symbol] = {
                "notional": event.filled_size * event.filled_price,
                "direction": event.direction,
            }
        elif event.action == "close":
            self._open_positions.pop(event.symbol, None)

    def record_loss(self, amount: float) -> None:
        self._daily_loss += amount
        self._consecutive_losses += 1
        if self._consecutive_losses >= self._risk["consecutive_loss_limit"]:
            self._cooldown_until = time.time() + self._risk["cooldown_hours"] * 3600
            logger.warning("Risk: consecutive loss limit hit, cooldown until %s", self._cooldown_until)

    def record_win(self) -> None:
        self._consecutive_losses = 0

    def reset_daily_loss(self) -> None:
        self._daily_loss = 0.0

    # Note: record_loss() and record_win() are called by PortfolioTracker
    # when a position is closed (wired in main.py orchestrator).
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_risk_manager.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add execution/risk_manager.py tests/test_risk_manager.py
git commit -m "feat: risk manager with position limits, exposure caps, and circuit breakers"
```

---

### Task 13: Order Executor

**Files:**
- Create: `execution/order_executor.py`
- Test: `tests/test_order_executor.py`

Handles order placement via Hyperliquid SDK. Tests use mocked SDK client. Per spec Section 5: limit order with timeout fallback to market, partial fill handling, TP/SL native orders.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_order_executor.py`:

```python
import pytest
from unittest.mock import AsyncMock
from core.event_bus import EventBus
from core.events import OrderRequestEvent, OrderFilledEvent
from execution.order_executor import OrderExecutor


@pytest.fixture
def bus():
    return EventBus()


@pytest.fixture
def mock_client():
    client = AsyncMock()
    client.place_limit_order.return_value = {
        "order_id": "ord_123",
        "filled_size": 0.1,
        "filled_price": 50000,
        "status": "filled",
        "fee": 5.0,
    }
    client.place_market_order.return_value = {
        "order_id": "ord_124",
        "filled_size": 0.1,
        "filled_price": 50050,
        "status": "filled",
        "fee": 5.0,
    }
    client.cancel_order.return_value = True
    client.set_tp_sl.return_value = True
    return client


@pytest.fixture
def config():
    return {
        "exchange": {
            "slippage_tolerance": 0.001,
            "order_timeout_sec": 30,
        }
    }


async def test_limit_order_filled_emits_event(bus, mock_client, config):
    fills = []

    async def handler(event):
        fills.append(event)

    bus.subscribe("OrderFilledEvent", handler)
    executor = OrderExecutor(bus=bus, client=mock_client, config=config)

    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="open",
        size=0.1, order_type="limit", limit_price=50000,
        stop_loss=47000, take_profit=54500,
        reason="trend score 75", timestamp=1000,
    )
    await executor.on_order_request(req)

    assert len(fills) == 1
    assert fills[0].symbol == "BTC"
    assert fills[0].filled_size == 0.1
    assert fills[0].order_id == "ord_123"


async def test_partial_fill_triggers_market_order(bus, mock_client, config):
    mock_client.place_limit_order.return_value = {
        "order_id": "ord_125",
        "filled_size": 0.05,  # Partial fill
        "filled_price": 50000,
        "status": "partial",
        "fee": 2.5,
    }
    fills = []

    async def handler(event):
        fills.append(event)

    bus.subscribe("OrderFilledEvent", handler)
    executor = OrderExecutor(bus=bus, client=mock_client, config=config)

    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="open",
        size=0.1, order_type="limit", limit_price=50000,
        stop_loss=47000, take_profit=54500,
        reason="trend score 75", timestamp=1000,
    )
    await executor.on_order_request(req)

    # Should have cancelled remaining and placed market order for rest
    mock_client.cancel_order.assert_called_once()
    mock_client.place_market_order.assert_called_once()
    assert len(fills) == 2  # One for partial limit, one for market


async def test_tp_sl_set_after_open_fill(bus, mock_client, config):
    fills = []

    async def handler(event):
        fills.append(event)

    bus.subscribe("OrderFilledEvent", handler)
    executor = OrderExecutor(bus=bus, client=mock_client, config=config)

    req = OrderRequestEvent(
        symbol="BTC", direction="long", action="open",
        size=0.1, order_type="limit", limit_price=50000,
        stop_loss=47000, take_profit=54500,
        reason="trend score 75", timestamp=1000,
    )
    await executor.on_order_request(req)
    mock_client.set_tp_sl.assert_called_once_with("BTC", 47000, 54500)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_order_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'execution.order_executor'`

- [ ] **Step 3: Implement `execution/order_executor.py`**

```python
import logging
from core.event_bus import EventBus
from core.events import OrderRequestEvent, OrderFilledEvent

logger = logging.getLogger(__name__)


class OrderExecutor:
    def __init__(self, bus: EventBus, client, config: dict) -> None:
        self._bus = bus
        self._client = client
        self._config = config["exchange"]

        bus.subscribe("OrderRequestEvent", self.on_order_request)

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
        if req.direction == "long":
            limit_price = req.limit_price * (1 + slippage)
        else:
            limit_price = req.limit_price * (1 - slippage)

        result = await self._client.place_limit_order(
            req.symbol, req.direction, req.size, limit_price
        )

        filled_size = result["filled_size"]
        if filled_size > 0:
            fill = OrderFilledEvent(
                symbol=req.symbol, direction=req.direction, action=req.action,
                filled_size=filled_size, filled_price=result["filled_price"],
                order_id=result["order_id"], fee=result["fee"],
                timestamp=req.timestamp,
            )
            await self._bus.publish("OrderFilledEvent", fill)

        # Handle partial fill: cancel remaining, market order the rest
        if result["status"] == "partial":
            remaining = req.size - filled_size
            await self._client.cancel_order(result["order_id"])
            if remaining > 0:
                market_result = await self._client.place_market_order(
                    req.symbol, req.direction, remaining
                )
                fill2 = OrderFilledEvent(
                    symbol=req.symbol, direction=req.direction, action=req.action,
                    filled_size=market_result["filled_size"],
                    filled_price=market_result["filled_price"],
                    order_id=market_result["order_id"], fee=market_result["fee"],
                    timestamp=req.timestamp,
                )
                await self._bus.publish("OrderFilledEvent", fill2)

        # Set TP/SL via exchange native orders (for open positions)
        if req.action == "open" and filled_size > 0:
            await self._client.set_tp_sl(req.symbol, req.stop_loss, req.take_profit)

    async def _execute_market(self, req: OrderRequestEvent) -> None:
        result = await self._client.place_market_order(
            req.symbol, req.direction, req.size
        )
        fill = OrderFilledEvent(
            symbol=req.symbol, direction=req.direction, action=req.action,
            filled_size=result["filled_size"], filled_price=result["filled_price"],
            order_id=result["order_id"], fee=result["fee"],
            timestamp=req.timestamp,
        )
        await self._bus.publish("OrderFilledEvent", fill)

        if req.action == "open":
            await self._client.set_tp_sl(req.symbol, req.stop_loss, req.take_profit)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_order_executor.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add execution/order_executor.py tests/test_order_executor.py
git commit -m "feat: order executor with limit/market orders and TP/SL placement"
```

---

## Chunk 5: Portfolio, Notifications & Main Orchestrator

### Task 14: Portfolio Tracker

**Files:**
- Create: `portfolio/__init__.py`
- Create: `portfolio/tracker.py`
- Test: `tests/test_tracker.py`

Tracks open positions, updates trailing stops per the 3-stage logic in spec Section 3, publishes `CloseSignalEvent` when stop/TP is hit.

- [ ] **Step 1: Create `portfolio/__init__.py`**

Empty file.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_tracker.py`:

```python
import pytest
from core.event_bus import EventBus
from core.events import OrderFilledEvent, PortfolioUpdateEvent, CloseSignalEvent
from portfolio.tracker import PortfolioTracker


@pytest.fixture
def config():
    return {
        "stop_loss": {
            "initial_atr_multiple": 2.0,
            "take_profit_atr_multiple": 3.0,
            "breakeven_trigger_atr": 1.0,
            "trailing_trigger_atr": 2.0,
            "trailing_distance_atr": 1.5,
        }
    }


@pytest.fixture
def bus():
    return EventBus()


async def test_open_fill_creates_position(bus, config):
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000,
        order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    assert "BTC" in tracker.positions
    assert tracker.positions["BTC"]["entry_price"] == 50000


async def test_close_fill_removes_position(bus, config):
    tracker = PortfolioTracker(bus=bus, config=config)
    # Open
    fill_open = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000,
        order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill_open)
    # Close
    fill_close = OrderFilledEvent(
        symbol="BTC", direction="long", action="close",
        filled_size=0.1, filled_price=52000,
        order_id="o2", fee=5.0, timestamp=2000,
    )
    await tracker.on_order_filled(fill_close)
    assert "BTC" not in tracker.positions


async def test_trailing_stop_stage1_no_move(bus, config):
    """Profit < 1*ATR: stop stays at initial position."""
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000,
        order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.positions["BTC"]["atr"] = 1500

    # Price moved up 500 (< 1*ATR=1500)
    tracker.update_price("BTC", 50500)
    pos = tracker.positions["BTC"]
    assert pos["stop_loss"] == 50000 - 2 * 1500  # Unchanged


async def test_trailing_stop_stage2_breakeven(bus, config):
    """Profit 1-2 * ATR: stop moves to entry (breakeven)."""
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000,
        order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.positions["BTC"]["atr"] = 1500

    # Price moved up 1800 (> 1*ATR, < 2*ATR)
    tracker.update_price("BTC", 51800)
    pos = tracker.positions["BTC"]
    assert pos["stop_loss"] == 50000  # Breakeven


async def test_trailing_stop_stage3_trailing(bus, config):
    """Profit > 2*ATR: trailing stop at highest - 1.5*ATR."""
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000,
        order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.positions["BTC"]["atr"] = 1500

    # Price at 53500 (profit = 3500 > 2*1500=3000)
    tracker.update_price("BTC", 53500)
    pos = tracker.positions["BTC"]
    expected_sl = 53500 - 1.5 * 1500  # 51250
    assert pos["stop_loss"] == expected_sl


async def test_stop_loss_emits_close_signal(bus, config):
    close_signals = []

    async def handler(event):
        close_signals.append(event)

    bus.subscribe("CloseSignalEvent", handler)
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000,
        order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.positions["BTC"]["atr"] = 1500
    tracker.positions["BTC"]["stop_loss"] = 47000

    # Price drops below stop
    await tracker.check_exits("BTC", 46500)
    assert len(close_signals) == 1
    assert close_signals[0].reason == "stop_loss"


async def test_take_profit_emits_close_signal(bus, config):
    close_signals = []

    async def handler(event):
        close_signals.append(event)

    bus.subscribe("CloseSignalEvent", handler)
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="BTC", direction="long", action="open",
        filled_size=0.1, filled_price=50000,
        order_id="o1", fee=5.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.positions["BTC"]["atr"] = 1500
    tracker.positions["BTC"]["take_profit"] = 54500

    await tracker.check_exits("BTC", 55000)
    assert len(close_signals) == 1
    assert close_signals[0].reason == "take_profit"


async def test_trailing_stop_short_direction(bus, config):
    """Short position: profit > 2*ATR triggers trailing stop."""
    tracker = PortfolioTracker(bus=bus, config=config)
    fill = OrderFilledEvent(
        symbol="ETH", direction="short", action="open",
        filled_size=1.0, filled_price=3000,
        order_id="o1", fee=3.0, timestamp=1000,
    )
    await tracker.on_order_filled(fill)
    tracker.positions["ETH"]["atr"] = 100

    # Price drops to 2750 (profit=250 > 2*100=200, stage 3)
    tracker.update_price("ETH", 2750)
    pos = tracker.positions["ETH"]
    expected_sl = 2750 + 1.5 * 100  # 2900
    assert pos["stop_loss"] == expected_sl
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_tracker.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'portfolio.tracker'`

- [ ] **Step 4: Implement `portfolio/tracker.py`**

```python
import logging
import time
from core.event_bus import EventBus
from core.events import OrderFilledEvent, CloseSignalEvent

logger = logging.getLogger(__name__)


class PortfolioTracker:
    def __init__(self, bus: EventBus, config: dict) -> None:
        self._bus = bus
        self._sl_cfg = config["stop_loss"]
        self.positions: dict[str, dict] = {}

        bus.subscribe("OrderFilledEvent", self.on_order_filled)

    async def on_order_filled(self, event: OrderFilledEvent) -> None:
        if event.action == "open":
            atr_sl = self._sl_cfg["initial_atr_multiple"]
            atr_tp = self._sl_cfg["take_profit_atr_multiple"]
            self.positions[event.symbol] = {
                "direction": event.direction,
                "size": event.filled_size,
                "entry_price": event.filled_price,
                "atr": 0,  # Set externally after signal context
                "stop_loss": (
                    event.filled_price - atr_sl * 0
                    if event.direction == "long"
                    else event.filled_price + atr_sl * 0
                ),
                "take_profit": (
                    event.filled_price + atr_tp * 0
                    if event.direction == "long"
                    else event.filled_price - atr_tp * 0
                ),
                "highest_price": event.filled_price,
                "lowest_price": event.filled_price,
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
            highest = pos["highest_price"]
        else:
            pos["lowest_price"] = min(pos["lowest_price"], current_price)
            profit = entry - current_price
            highest = entry - pos["lowest_price"]

        be_trigger = self._sl_cfg["breakeven_trigger_atr"] * atr
        trail_trigger = self._sl_cfg["trailing_trigger_atr"] * atr
        trail_dist = self._sl_cfg["trailing_distance_atr"] * atr

        if profit >= trail_trigger:
            # Stage 3: trailing stop
            if direction == "long":
                new_sl = pos["highest_price"] - trail_dist
            else:
                new_sl = pos["lowest_price"] + trail_dist
            # Never move stop backwards
            if direction == "long":
                pos["stop_loss"] = max(pos["stop_loss"], new_sl)
            else:
                pos["stop_loss"] = min(pos["stop_loss"], new_sl)
        elif profit >= be_trigger:
            # Stage 2: breakeven
            if direction == "long":
                pos["stop_loss"] = max(pos["stop_loss"], entry)
            else:
                pos["stop_loss"] = min(pos["stop_loss"], entry)
        # Stage 1: no change

    async def check_exits(self, symbol: str, current_price: float) -> None:
        if symbol not in self.positions:
            return
        pos = self.positions[symbol]
        direction = pos["direction"]

        hit_sl = (
            (direction == "long" and current_price <= pos["stop_loss"])
            or (direction == "short" and current_price >= pos["stop_loss"])
        )
        hit_tp = (
            (direction == "long" and current_price >= pos["take_profit"])
            or (direction == "short" and current_price <= pos["take_profit"])
        )

        if hit_sl:
            reason = "trailing_stop" if pos["stop_loss"] != (
                pos["entry_price"] - self._sl_cfg["initial_atr_multiple"] * pos["atr"]
                if direction == "long"
                else pos["entry_price"] + self._sl_cfg["initial_atr_multiple"] * pos["atr"]
            ) else "stop_loss"
            await self._bus.publish("CloseSignalEvent", CloseSignalEvent(
                symbol=symbol, reason=reason,
                close_price=current_price, timestamp=time.time() * 1000,
            ))
        elif hit_tp:
            await self._bus.publish("CloseSignalEvent", CloseSignalEvent(
                symbol=symbol, reason="take_profit",
                close_price=current_price, timestamp=time.time() * 1000,
            ))
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_tracker.py -v`
Expected: 7 passed

- [ ] **Step 6: Commit**

```bash
git add portfolio/ tests/test_tracker.py
git commit -m "feat: portfolio tracker with 3-stage trailing stop logic"
```

---

### Task 15: Telegram Notifications

**Files:**
- Create: `notify/__init__.py`
- Create: `notify/telegram.py`
- Test: `tests/test_telegram.py`

Best-effort notifications — failures don't block trading logic. Per spec Section 6: notification queue with cap, graceful degradation.

- [ ] **Step 1: Create `notify/__init__.py`**

Empty file.

- [ ] **Step 2: Write the failing tests**

Create `tests/test_telegram.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from notify.telegram import TelegramNotifier


async def test_send_message_calls_bot():
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", enabled=True)
    notifier._bot = AsyncMock()
    await notifier.send("Test message")
    notifier._bot.send_message.assert_called_once_with(chat_id="12345", text="Test message")


async def test_send_failure_does_not_raise():
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", enabled=True)
    notifier._bot = AsyncMock()
    notifier._bot.send_message.side_effect = Exception("Network error")
    # Should not raise
    await notifier.send("Test message")


async def test_disabled_notifier_is_noop():
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", enabled=False)
    notifier._bot = AsyncMock()
    await notifier.send("Test message")
    notifier._bot.send_message.assert_not_called()


async def test_queue_cap_drops_oldest():
    notifier = TelegramNotifier(token="fake_token", chat_id="12345", enabled=True, max_queue=3)
    notifier._bot = AsyncMock()
    notifier._bot.send_message.side_effect = Exception("fail")

    for i in range(5):
        await notifier.send(f"msg {i}")

    # Queue should have at most 3 items (the latest 3)
    assert len(notifier._failed_queue) <= 3
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `python -m pytest tests/test_telegram.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'notify.telegram'`

- [ ] **Step 4: Implement `notify/telegram.py`**

```python
import logging
from collections import deque

logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(
        self, token: str, chat_id: str, enabled: bool = True, max_queue: int = 100
    ) -> None:
        self._chat_id = chat_id
        self._enabled = enabled
        self._max_queue = max_queue
        self._failed_queue: deque[str] = deque(maxlen=max_queue)
        self._bot = None
        if enabled and token:
            try:
                from telegram import Bot
                self._bot = Bot(token=token)
            except ImportError:
                logger.warning("python-telegram-bot not installed, notifications disabled")
                self._enabled = False

    async def send(self, message: str) -> None:
        if not self._enabled or not self._bot:
            return
        try:
            await self._bot.send_message(chat_id=self._chat_id, text=message)
        except Exception:
            logger.warning("Telegram send failed, queued message")
            self._failed_queue.append(message)

    async def retry_failed(self) -> None:
        if not self._enabled or not self._bot:
            return
        retries = list(self._failed_queue)
        self._failed_queue.clear()
        for msg in retries:
            await self.send(msg)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_telegram.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add notify/ tests/test_telegram.py
git commit -m "feat: telegram notifier with graceful degradation and queue cap"
```

---

### Task 16: Main Orchestrator

**Files:**
- Create: `main.py`

The entry point wires all components together, starts the asyncio event loop, and manages the runtime schedule. Per spec Section 7: startup sequence, runtime loops, `--dry-run` support.

- [ ] **Step 1: Implement `main.py`**

```python
import argparse
import asyncio
import logging
import os
import signal
import sys
import time

from dotenv import load_dotenv

from core.event_bus import EventBus
from core.events import OrderRequestEvent, CloseSignalEvent
from data.feeder import DataFeeder
from data.store import Store
from execution.risk_manager import RiskManager
from execution.order_executor import OrderExecutor
from portfolio.tracker import PortfolioTracker
from strategy.signal_engine import SignalEngine
from notify.telegram import TelegramNotifier
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

        # 1. Initialize store
        self._store = Store("hyperquant.db")
        await self._store.initialize()

        # 2. Initialize notifier
        notify_cfg = self._config["notify"]
        self._notifier = TelegramNotifier(
            token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            enabled=notify_cfg["enabled"],
        )

        # 3. Create exchange client
        if self._dry_run:
            from unittest.mock import AsyncMock
            client = AsyncMock()
            client.fetch_candles.return_value = []
            client.fetch_tickers.return_value = []
            client.get_account_equity.return_value = 10_000
        else:
            # Real Hyperliquid client - to be implemented with SDK integration
            raise NotImplementedError(
                "Production Hyperliquid client not yet implemented. Use --dry-run."
            )

        equity = await client.get_account_equity()

        # 4. Wire components
        feeder = DataFeeder(bus=self._bus, client=client, config=self._config)
        signal_engine = SignalEngine(bus=self._bus, config=self._config)
        risk_manager = RiskManager(bus=self._bus, config=self._config, equity=equity)
        tracker = PortfolioTracker(bus=self._bus, config=self._config)

        if not self._dry_run:
            executor = OrderExecutor(bus=self._bus, client=client, config=self._config)

        # Wire CloseSignalEvent → OrderRequestEvent for position closing
        async def on_close_signal(event):
            if event.symbol in tracker.positions:
                pos = tracker.positions[event.symbol]
                order = OrderRequestEvent(
                    symbol=event.symbol,
                    direction=pos["direction"],
                    action="close",
                    size=pos["size"],
                    order_type="market",
                    limit_price=None,
                    stop_loss=0,
                    take_profit=0,
                    reason=event.reason,
                    timestamp=event.timestamp,
                )
                await self._bus.publish("OrderRequestEvent", order)

        self._bus.subscribe("CloseSignalEvent", on_close_signal)

        # Wire ATR from SignalEvent to PortfolioTracker after fills
        async def on_signal_for_atr(event):
            self._pending_atrs[event.symbol] = event.atr

        async def on_fill_set_atr(event):
            if event.action == "open" and event.symbol in self._pending_atrs:
                tracker.set_atr(event.symbol, self._pending_atrs.pop(event.symbol))

        self._pending_atrs = {}
        self._bus.subscribe("SignalEvent", on_signal_for_atr)
        self._bus.subscribe("OrderFilledEvent", on_fill_set_atr)

        # 5. Initial data load
        await feeder.refresh_symbol_pool()

        # 6. Run loop
        self._running = True
        await self._run_loop(feeder, risk_manager)

    async def _run_loop(self, feeder: DataFeeder, risk_manager: RiskManager) -> None:
        pool_refresh_interval = self._config["data"]["pool_refresh_interval"]
        last_pool_refresh = time.time()

        while self._running:
            now = time.time()

            # Refresh symbol pool every N seconds
            if now - last_pool_refresh >= pool_refresh_interval:
                try:
                    await feeder.refresh_symbol_pool()
                    last_pool_refresh = now
                except Exception:
                    logger.exception("Symbol pool refresh failed")

            # Fetch candles for all symbols
            for symbol in feeder.symbol_pool:
                for tf in [
                    self._config["strategy"]["primary_timeframe"],
                    self._config["strategy"]["confirm_timeframe"],
                ]:
                    try:
                        await feeder.fetch_and_publish_candles(symbol, tf)
                    except Exception:
                        logger.exception("Candle fetch failed: %s %s", symbol, tf)

            # Reset daily loss at UTC midnight
            risk_manager.reset_daily_loss()

            # Wait for next cycle (1 minute health check interval)
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
    setup_logging(config)

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
```

- [ ] **Step 2: Verify dry-run starts without errors**

Run: `python main.py --dry-run`
Expected: Logs startup messages, runs without crash for a few seconds. Ctrl+C to stop.

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: main orchestrator with component wiring and dry-run mode"
```

> **Deferred to production hardening phase (not in scope for this plan):**
> - Production Hyperliquid SDK client wrapper (currently uses `--dry-run` mock)
> - Crash recovery: position reconciliation with exchange on startup (spec Section 6)
> - WebSocket reconnection with exponential backoff (spec Section 6)
> - API error retry logic: rate limit (429), server error (5xx), timeout handling (spec Section 6)
> - Order timeout: 30-second limit order wait then fallback to market (spec Section 5)
> - Balance-insufficient position recalculation (spec Section 5)
> - Health check and periodic position sync against exchange (spec Section 7)

---

### Task 17: Docker Deployment

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yaml`

- [ ] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
COPY . .
RUN pip install --no-cache-dir .

CMD ["python", "main.py"]
```

- [ ] **Step 2: Create `docker-compose.yaml`**

```yaml
services:
  hyperquant:
    build: .
    env_file: .env
    volumes:
      - ./config.yaml:/app/config.yaml:ro
      - ./data:/app/data
      - ./logs:/app/logs
    restart: unless-stopped
    command: ["python", "main.py"]
```

- [ ] **Step 3: Verify Docker build**

Run: `docker build -t hyperquant .`
Expected: Build completes successfully.

- [ ] **Step 4: Commit**

```bash
git add Dockerfile docker-compose.yaml
git commit -m "feat: docker containerization for production deployment"
```

---

### Task 18: Full Test Suite Verification

- [ ] **Step 1: Run all tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All tests pass (approximately 35+ tests across all modules).

- [ ] **Step 2: Run with coverage**

Run: `python -m pytest tests/ --cov=. --cov-report=term-missing`
Expected: Coverage report showing high coverage for core logic modules.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore: verify full test suite passes"
```

---
