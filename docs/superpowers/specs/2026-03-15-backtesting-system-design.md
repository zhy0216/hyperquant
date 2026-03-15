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
├── Strategy (new ABC at strategy/base.py, SignalEngine refactored to implement it)
├── RiskManager (existing, with injectable time source)
├── PortfolioTracker (existing, with injectable time source)
├── SimulatedExecutor (new, replaces OrderExecutor)
├── DataLoader (new ABC with multiple implementations)
├── TradeLog (new, records all trades)
└── ReportGenerator (new, produces stats/charts/HTML)
```

### Data Flow Per Bar

The engine loads candles for all symbols and both timeframes (primary + confirm). For each timestamp step:

```
BacktestEngine per-bar loop:
    0. Call strategy.clear_cycle_cooldowns() (start of each evaluation cycle)
    1. Check if UTC date changed → call risk_manager.reset_daily_loss()
    2. For each symbol, for each timeframe (primary, confirm):
       - Build rolling candle window (all candles up to current timestamp)
       - Publish MarketDataEvent(symbol, timeframe, candles=rolling_window)
    3. MarketDataEvent → Strategy.on_market_data()
       - Strategy may publish SignalEvent
    4. SignalEvent → engine captures ATR for later use
       - SignalEvent → RiskManager.on_signal() → OrderRequestEvent
    5. OrderRequestEvent → SimulatedExecutor → OrderFilledEvent
    6. OrderFilledEvent → PortfolioTracker.on_order_filled()
       - If action=="open": engine calls tracker.set_atr(symbol, pending_atr)
       - Engine calls risk_manager.record_win()/record_loss() as appropriate
       - Engine updates equity: risk_manager.update_equity(new_equity)
    7. For each open position:
       - tracker.update_price(symbol, current_close)
       - tracker.check_exits(symbol, current_close)
    8. CloseSignalEvent → engine wires to OrderRequestEvent(action="close")
       → SimulatedExecutor → OrderFilledEvent(action="close")
    9. TradeLog records entry/exit pairs
   10. Record mark-to-market equity snapshot for equity curve
```

### Key Wiring (replicated from main.py)

The `BacktestEngine` must replicate all the ad-hoc wiring in `main.py`:

1. **CloseSignalEvent → OrderRequestEvent**: When a `CloseSignalEvent` is received, look up the position in `PortfolioTracker.positions` and publish an `OrderRequestEvent(action="close")`.
2. **ATR propagation**: On `SignalEvent`, capture `event.atr` in a `_pending_atrs` dict. On `OrderFilledEvent(action="open")`, call `tracker.set_atr(symbol, pending_atr)`.
3. **Daily loss reset**: Track the current UTC date from bar timestamps. When the date changes, call `risk_manager.reset_daily_loss()`.
4. **Cycle cooldown clear**: Call `strategy.clear_cycle_cooldowns()` at the start of each evaluation cycle (each time we iterate through all symbols).

## New Components

### 1. Strategy Interface (`strategy/base.py`)

Placed in `strategy/` (not `backtest/`) since it is used by both live and backtest modes.

```python
class Strategy(ABC):
    @abstractmethod
    def __init__(self, bus: EventBus, config: dict) -> None: ...

    @abstractmethod
    async def on_market_data(self, event: MarketDataEvent) -> None:
        """Receive candle data. Publish SignalEvent or CloseSignalEvent as needed."""

    async def on_order_filled(self, event: OrderFilledEvent) -> None:
        """Optional: receive fill notifications to update internal state.
        Default is a no-op. Override if the strategy tracks positions."""
        pass

    def clear_cycle_cooldowns(self) -> None:
        """Optional: called at the start of each evaluation cycle.
        Default is a no-op. Override if the strategy has cycle-level state."""
        pass
```

The existing `SignalEngine` will be refactored to inherit from `Strategy` without changing its core logic. `on_order_filled` and `clear_cycle_cooldowns` are optional with default no-ops so simple strategies do not need to implement them.

### 2. DataLoader (`backtest/data_loader.py`)

Abstract base with three implementations:

```python
class DataLoader(ABC):
    @abstractmethod
    async def load(self, symbol: str, timeframe: str,
                   start: datetime, end: datetime) -> list[Candle]:
        """Load candles for a specific symbol and timeframe.
        Returns list[Candle] sorted by timestamp ascending."""
```

Implementations:

- **`HyperliquidLoader`** — Fetches from Hyperliquid API, caches to local SQLite via existing `Store`. Subsequent runs read from cache.
- **`CsvLoader`** — Reads CSV files. Expected columns: `timestamp, open, high, low, close, volume`. File naming convention: `{symbol}_{timeframe}.csv` (e.g., `BTC-PERP_1h.csv`).
- **`ParquetLoader`** — Reads Parquet files for large datasets. Same column expectations and naming convention.

All loaders return `list[Candle]` sorted by timestamp ascending. The `timeframe` parameter is passed to the loader so it knows which data to fetch/load.

**Confirm timeframe handling**: The engine calls `loader.load()` separately for both primary (1h) and confirm (4h) timeframes per symbol. If only primary timeframe data is available, the engine can optionally aggregate it (e.g., 4 x 1h → 1 x 4h) via a utility function. If neither is available, the symbol is skipped.

**Lookback window**: The engine loads `data.warmup_candles` (default 200) extra candles before the `start` date to ensure indicators have sufficient history from bar 1 of the test period.

### 3. SimulatedExecutor (`backtest/simulated_executor.py`)

Subscribes to `OrderRequestEvent`. For each order:

1. Get the current bar's close price from the engine's shared `current_prices: dict[str, float]` (set by the engine before each bar's event processing)
2. Apply slippage based on buy/sell direction (not long/short):
   - **Buy** (open long or close short): `fill_price = close * (1 + slippage)`
   - **Sell** (open short or close long): `fill_price = close * (1 - slippage)`
3. Deduct fee: `fee = fill_price * size * fee_rate`
4. Publish `OrderFilledEvent`

The engine passes `current_prices` as a shared dict reference at construction time. The engine updates this dict before processing each bar.

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
1. Load candles for all symbols and both timeframes via `DataLoader` (with warmup period)
2. Build a unified timeline: collect all unique primary-timeframe timestamps, sorted ascending
3. For each timestamp in the timeline:
   - Update `current_prices` dict with each symbol's close price
   - Check UTC date change → `risk_manager.reset_daily_loss()`
   - Call `strategy.clear_cycle_cooldowns()`
   - For each symbol, for each timeframe:
     - Build rolling candle window (all candles with `ts <= current_ts`)
     - Publish `MarketDataEvent(symbol, timeframe, candles=window, timestamp=current_ts)`
   - After all events settle (EventBus.publish is synchronous-sequential, so events settle naturally after the top-level publish returns):
     - For each open position: `tracker.update_price()` then `tracker.check_exits()`
   - Record equity snapshot: `initial_equity + realized_pnl + unrealized_pnl_of_open_positions`
   - Update `risk_manager.update_equity(current_equity)`
4. At end, force-close all open positions at last known price (with slippage and fees applied)
5. Return `BacktestResult` containing trade log, equity curve, and config used

**Equity tracking**: At each bar, mark-to-market equity is computed as:
`equity = initial_equity + sum(closed_trade_pnls) + sum(open_position_unrealized_pnl)`

Unrealized PnL for each open position: `(current_price - entry_price) * size` for long, `(entry_price - current_price) * size` for short.

**Win/loss tracking**: When a position is closed (exit `OrderFilledEvent`), the engine computes PnL and calls `risk_manager.record_win()` or `risk_manager.record_loss(abs(loss))` accordingly.

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

`RiskManager`, `PortfolioTracker`, and `SignalEngine` currently use `time.time()`. For backtesting, timestamps must come from the historical data.

**Unified approach**: Add an optional `time_fn: Callable[[], float]` parameter to the constructor of each component. Store as `self._time_fn`. Default to `time.time`. Replace all `time.time()` calls with `self._time_fn()`.

Affected components:
- **`RiskManager.__init__()`**: Add `time_fn` param. Used in `on_signal()` for cooldown check, and `record_loss()` for cooldown timer.
- **`PortfolioTracker.__init__()`**: Add `time_fn` param. Used in `check_exits()` for CloseSignalEvent timestamps.
- **`SignalEngine.__init__()`**: Add `time_fn` param. Used in `_evaluate_symbol()` for CloseSignalEvent and SignalEvent timestamps.

In backtest mode, the engine injects a lambda returning `self._current_timestamp` (updated per bar). In live mode, no change needed (defaults to `time.time`).

### SignalEngine Refactor

- `SignalEngine` extends `Strategy` ABC
- No logic changes, just adds the inheritance and method signatures
- Existing `on_market_data` and `_on_order_filled` already match the ABC signatures

## Edge Cases

### Insufficient Data
If a symbol has fewer candles than `ema_slow` (60 by default) within the lookback + test window, `SignalEngine` will silently skip it (existing guard at line 48). The engine logs a warning.

### Historical Data Gaps
Missing candles (exchange downtime) are tolerated. The engine iterates by available timestamps, not by expected intervals. Indicators will compute on whatever data is present. A warning is logged if gaps exceed 3x the expected interval.

### Force-Close at End
All open positions at the end of the backtest are force-closed at the last bar's close price, with slippage and fees applied, consistent with normal trade handling.

## CLI Interface

```bash
# Backtest with default strategy (existing trend-following)
python -m backtest.run --symbols BTC-PERP ETH-PERP \
    --start 2025-01-01 --end 2025-12-31 \
    --output reports/

# Backtest with CSV data
python -m backtest.run --csv-dir data/candles/ \
    --start 2025-01-01 --end 2025-12-31 \
    --output reports/

# Custom strategy
python -m backtest.run --strategy my_strategies.MeanReversion \
    --symbols BTC-PERP --start 2025-06-01 --end 2025-12-31

# Override backtest config
python -m backtest.run --symbols BTC-PERP \
    --start 2025-01-01 --end 2025-12-31 \
    --initial-equity 50000 --slippage 0.002
```

## File Structure

```
strategy/
├── base.py               # Strategy ABC (new)
├── signal_engine.py      # Refactored to extend Strategy
├── scorer.py             # (unchanged)
└── indicators.py         # (unchanged)
backtest/
├── __init__.py
├── engine.py             # BacktestEngine orchestrator
├── data_loader.py        # DataLoader ABC + HyperliquidLoader, CsvLoader, ParquetLoader
├── simulated_executor.py # SimulatedExecutor (mock fills)
├── trade_log.py          # TradeRecord + TradeLog
├── metrics.py            # Performance metric calculations
├── report.py             # ReportGenerator (terminal, CSV, charts, HTML)
├── run.py                # CLI entry point (__main__)
└── templates/
    └── report.html       # HTML report template
tests/
├── test_backtest_engine.py
├── test_simulated_executor.py
├── test_data_loader.py
├── test_trade_log.py
├── test_metrics.py
└── test_report.py
```

## Testing Strategy

- **Unit tests**: Each component in isolation (SimulatedExecutor, TradeLog, metrics calculations, data loaders)
- **Integration test**: Full backtest run with synthetic uptrend/downtrend candle data, verify expected trades and metrics
- **Regression test**: Run existing `SignalEngine` through backtest, compare signal output with existing unit tests
- **Wiring test**: Verify all main.py wiring is replicated (ATR propagation, close signal → order, daily reset, cycle cooldown)

## Dependencies

New: `matplotlib` (charts), `jinja2` (HTML template), `pyarrow` (Parquet support — optional)

Existing: `numpy`, `aiosqlite` already in the project.
