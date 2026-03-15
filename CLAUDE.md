# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make install          # pip install -e ".[dev]"
make test             # pytest --cov --cov-report=term-missing -q
make lint             # ruff check .
make fmt              # ruff format . && ruff check --fix .
make typecheck        # mypy on all source packages
pytest tests/test_foo.py           # run a single test file
pytest tests/test_foo.py::test_bar # run a single test
python -m backtest --config config.yaml --symbols BTC ETH --start 2024-01-01 --end 2024-12-31 --csv-dir ./data --output ./reports
```

## Architecture

Event-driven quantitative trading system for Hyperliquid perpetual futures. All components communicate through an async EventBus (pub/sub in `core/event_bus.py`).

**Event flow (live & backtest):**
```
DataFeeder/DataLoader → MarketDataEvent → SignalEngine → SignalEvent → RiskManager → OrderRequestEvent → OrderExecutor/SimulatedExecutor → OrderFilledEvent → PortfolioTracker
```

**Key packages:**
- `core/` — EventBus and event dataclasses (MarketDataEvent, SignalEvent, OrderRequestEvent, OrderFilledEvent, CloseSignalEvent, PortfolioUpdateEvent)
- `strategy/` — Strategy ABC (`base.py`), technical indicators, trend scorer (0-100 composite score), SignalEngine implementation
- `execution/` — RiskManager (exposure limits, circuit breaker, daily loss), PositionSizer (ATR-adaptive), OrderExecutor (live)
- `portfolio/` — PortfolioTracker (position tracking, 3-stage trailing stops, SL/TP detection)
- `data/` — DataFeeder (live candle fetching), Store (async SQLite with WAL mode), SymbolFilter
- `backtest/` — BacktestEngine (per-bar event replay), DataLoader ABC + CSV/Parquet loaders, SimulatedExecutor (slippage/fees), TradeLog, metrics, ReportGenerator
- `notify/` — Telegram alerts with retry queue
- `utils/` — YAML config loader, structured logging (structlog)

**Backtest reuses the same Strategy, RiskManager, and PortfolioTracker as live trading.** Only DataFeeder→DataLoader and OrderExecutor→SimulatedExecutor are swapped.

## Code Standards

- Python 3.11+, strict mypy (`disallow_untyped_defs`), all functions need type annotations
- Ruff linting with 100 char line length; security checks (bandit) enabled except in tests
- Async tests use `pytest-asyncio` in auto mode — just use `async def test_*`, no decorator needed
- Time injection via `time_fn` parameter enables deterministic testing
- All config in `config.yaml` — no magic numbers in code
