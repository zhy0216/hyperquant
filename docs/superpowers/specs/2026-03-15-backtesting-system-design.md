# Backtesting System Design

## Overview

Add a general-purpose backtesting system to HyperQuant that replays historical candle data through the existing event-driven architecture. Any strategy implementing the `Strategy` interface can be backtested with full risk management, position tracking, and simulated order execution — using the same components as live trading.

## Architecture

### Approach: Event-Driven Replay

The backtest engine reuses the existing `EventBus`, `RiskManager`, and `PortfolioTracker`. It replaces two components:

- **DataFeeder** → `DataLoader` (historical candle source)
- **OrderExecutor** → `SimulatedExecutor` (instant fill at close price + configurable slippage/fees)

This guarantees backtest-live consistency: the strategy, risk, and position logic are identical in both modes.

### Component Diagram

```
BacktestEngine
├── EventBus (existing)
├── Strategy (new ABC, existing SignalEngine refactored to implement it)
├── RiskManager (existing, with injectable time source)
├── PortfolioTracker (existing, with injectable time source)
├── SimulatedExecutor (new, replaces OrderExecutor)
├── DataLoader (new ABC with multiple implementations)
├── TradeLog (new, records all trades)
└── ReportGenerator (new, produces stats/charts/HTML)
```

### Data Flow Per Bar

```
DataLoader.load() → list[Candle]
    ↓
BacktestEngine iterates each bar:
    1. Publish MarketDataEvent → Strategy.on_market_data()
    2. Strategy may publish SignalEvent
    3. SignalEvent → RiskManager.on_signal() → OrderRequestEvent
    4. OrderRequestEvent → SimulatedExecutor → OrderFilledEvent
    5. OrderFilledEvent → PortfolioTracker.on_order_filled()
    6. PortfolioTracker.check_exits() → may publish CloseSignalEvent
    7. CloseSignalEvent → OrderRequestEvent (close) → SimulatedExecutor → fill
    8. TradeLog records entry/exit pairs
```

## New Components

### 1. Strategy Interface (`backtest/strategy.py`)

```python
class Strategy(ABC):
    @abstractmethod
    def __init__(self, bus: EventBus, config: dict) -> None: ...

    @abstractmethod
    async def on_market_data(self, event: MarketDataEvent) -> None:
        """Receive candle data. Publish SignalEvent or CloseSignalEvent as needed."""

    @abstractmethod
    async def on_order_filled(self, event: OrderFilledEvent) -> None:
        """Receive fill notifications to update internal state."""
```

The existing `SignalEngine` will be refactored to inherit from `Strategy` without changing its core logic.

### 2. DataLoader (`backtest/data_loader.py`)

Abstract base with three implementations:

- **`HyperliquidLoader`** — Fetches from Hyperliquid API, caches to local SQLite via existing `Store`. Subsequent runs read from cache.
- **`CsvLoader`** — Reads CSV files. Expected columns: `timestamp, open, high, low, close, volume`.
- **`ParquetLoader`** — Reads Parquet files for large datasets.

All loaders return `list[Candle]` sorted by timestamp ascending.

### 3. SimulatedExecutor (`backtest/simulated_executor.py`)

Subscribes to `OrderRequestEvent`. For each order:

1. Fill at the current bar's close price (from the engine's current bar context)
2. Apply slippage: `fill_price = close * (1 + slippage)` for long, `(1 - slippage)` for short
3. Deduct fee: `fee = fill_price * size * fee_rate`
4. Publish `OrderFilledEvent`
5. Append to `TradeLog`

Configuration:
```yaml
backtest:
  slippage: 0.001     # 0.1%
  fee_rate: 0.00035   # Hyperliquid taker fee
  initial_equity: 10000
```

### 4. BacktestEngine (`backtest/engine.py`)

The orchestrator:

```python
class BacktestEngine:
    def __init__(self, config: dict, strategy_cls: type[Strategy],
                 loader: DataLoader, symbols: list[str],
                 start: datetime, end: datetime) -> None: ...

    async def run(self) -> BacktestResult: ...
```

Run loop:
1. Load candles for all symbols via `DataLoader`
2. Merge all candle bars into a single timeline sorted by timestamp
3. For each bar:
   - Set the engine's current time to the bar's timestamp
   - Publish `MarketDataEvent`
   - After all events settle, update `PortfolioTracker` prices and check exits
4. At end, force-close all open positions at last known price
5. Return `BacktestResult` containing trade log and equity curve

### 5. TradeLog (`backtest/trade_log.py`)

```python
@dataclass
class TradeRecord:
    symbol: str
    direction: str           # "long" | "short"
    entry_price: float
    exit_price: float
    size: float
    entry_time: datetime
    exit_time: datetime
    pnl: float               # net P&L after fees
    fee: float
    exit_reason: str          # stop_loss, take_profit, trailing_stop, trend_reversal

class TradeLog:
    def record_entry(self, event: OrderFilledEvent) -> None: ...
    def record_exit(self, event: OrderFilledEvent, reason: str) -> None: ...
    def get_trades(self) -> list[TradeRecord]: ...
    def to_csv(self, path: str) -> None: ...
```

### 6. Performance Metrics (`backtest/metrics.py`)

Computes from trade log and equity curve:

| Metric | Description |
|--------|-------------|
| Total Return | Final equity / initial equity - 1 |
| Annualized Return | Geometric annualization |
| Sharpe Ratio | Risk-adjusted return (rf=0) |
| Sortino Ratio | Downside-only volatility |
| Max Drawdown | Largest peak-to-trough decline (% and $) |
| Win Rate | Winning trades / total trades |
| Profit Factor | Gross profits / gross losses |
| Avg Trade Duration | Mean holding period |
| Max Consecutive Losses | Longest losing streak |
| Total Trades | Count of round-trip trades |

### 7. ReportGenerator (`backtest/report.py`)

Produces four output formats:

1. **Terminal** — Print summary table to stdout
2. **CSV** — Export `TradeRecord` list to CSV
3. **Charts** (matplotlib) — Equity curve, drawdown curve, monthly returns heatmap. Saved as PNG.
4. **HTML** — Self-contained HTML file embedding charts (base64) and stats tables

## Changes to Existing Code

### Time Source Injection

`RiskManager` and `PortfolioTracker` currently use `time.time()`. For backtesting, timestamps must come from the historical data. Solution:

- Add an optional `time_fn: Callable[[], float]` parameter to `RiskManager.__init__()` and to `PortfolioTracker` methods that use `time.time()`. Default to `time.time` for live mode.
- In backtest mode, the engine injects a function returning the current bar's timestamp.

Affected locations:
- `risk_manager.py`: `on_signal()` (line 29), `record_loss()` (line 84)
- `tracker.py`: `check_exits()` (lines 93, 98)
- `signal_engine.py`: `_evaluate_symbol()` (lines 91-93, 96-98, 129)

### SignalEngine Refactor

- `SignalEngine` extends `Strategy` ABC
- No logic changes, just adds the inheritance and method signatures

## CLI Interface

```bash
# Backtest with default strategy (existing trend-following)
python -m backtest.run --symbols BTC-PERP ETH-PERP \
    --start 2025-01-01 --end 2025-12-31 \
    --timeframe 1h --output reports/

# Backtest with CSV data
python -m backtest.run --csv-dir data/candles/ \
    --start 2025-01-01 --end 2025-12-31 \
    --output reports/

# Custom strategy
python -m backtest.run --strategy my_strategies.MeanReversion \
    --symbols BTC-PERP --start 2025-06-01 --end 2025-12-31
```

## File Structure

```
backtest/
├── __init__.py
├── strategy.py           # Strategy ABC
├── engine.py             # BacktestEngine orchestrator
├── data_loader.py        # DataLoader ABC + HyperliquidLoader, CsvLoader, ParquetLoader
├── simulated_executor.py # SimulatedExecutor (mock fills)
├── trade_log.py          # TradeRecord + TradeLog
├── metrics.py            # Performance metric calculations
├── report.py             # ReportGenerator (terminal, CSV, charts, HTML)
├── run.py                # CLI entry point
└── templates/
    └── report.html       # HTML report template
tests/
└── test_backtest_*.py    # Tests for each backtest component
```

## Testing Strategy

- **Unit tests**: Each component in isolation (SimulatedExecutor, TradeLog, metrics calculations, data loaders)
- **Integration test**: Full backtest run with synthetic uptrend/downtrend candle data, verify expected trades and metrics
- **Regression test**: Run existing `SignalEngine` through backtest, compare signal output with existing unit tests

## Dependencies

New: `matplotlib` (charts), `jinja2` (HTML template), `pyarrow` (Parquet support — optional)

Existing: `numpy`, `aiosqlite` already in the project.
