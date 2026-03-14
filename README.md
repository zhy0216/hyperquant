# HyperQuant

[![CI](https://github.com/zhy0216/hyperquant/actions/workflows/ci.yaml/badge.svg)](https://github.com/zhy0216/hyperquant/actions/workflows/ci.yaml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
An event-driven quantitative trading system for [Hyperliquid](https://hyperliquid.xyz/) perpetual futures. Built for small retail traders (<$10K accounts) who want a fully automated, 24/7 trend-following strategy.

> **Status**: Early stage (v0.1.0). Dry-run mode is fully functional. Production mode awaits Hyperliquid SDK integration.

## Strategy Overview

HyperQuant runs a multi-symbol trend-following strategy with ATR-adaptive position sizing:

- **Trend scoring** (0–100) based on EMA crossovers, RSI + MACD momentum, and Donchian breakouts
- **Entry**: Score > 65 on 1h candles with 4h confirmation
- **Exit**: Hard stop-loss, take-profit at 3x ATR, trend reversal, or three-stage trailing stop
- **Risk**: 2% per trade, max 5 positions, 3x leverage cap, daily loss circuit breaker

All parameters are configurable via `config.yaml` — no code changes needed.

## Architecture

```
┌─ Event Bus (asyncio) ──────────────────────────────────┐
│                                                         │
│  Data Feeder ──→ Signal Engine ──→ Risk Manager         │
│       │               │                │                │
│       ▼               ▼                ▼                │
│  MarketDataEvent  SignalEvent    OrderRequestEvent       │
│                                        │                │
│  Portfolio Tracker ◄── Order Executor ◄┘                │
│       │                    │                            │
│       ▼                    ▼                            │
│  CloseSignalEvent    OrderFilledEvent                   │
│                                                         │
└──────────────────────┬─────────────────────────────────┘
                       ▼
                 SQLite Store
```

All components communicate through a lightweight async event bus with per-handler error isolation.

## Project Structure

```
hyperquant/
├── main.py                  # Entry point & orchestration
├── config.yaml              # All strategy/risk parameters
├── core/
│   ├── event_bus.py         # Async pub/sub event system
│   └── events.py            # Event dataclasses
├── data/
│   ├── feeder.py            # Market data acquisition
│   ├── store.py             # SQLite storage (WAL mode)
│   └── symbol_filter.py     # Volume/age-based filtering
├── strategy/
│   ├── indicators.py        # EMA, RSI, MACD, Donchian, ATR
│   ├── scorer.py            # Composite trend scoring
│   └── signal_engine.py     # Signal generation & reversal detection
├── execution/
│   ├── risk_manager.py      # Exposure limits, circuit breaker
│   ├── position_sizer.py    # ATR-adaptive sizing
│   └── order_executor.py    # Order placement & fill handling
├── portfolio/
│   └── tracker.py           # Position tracking & trailing stops
├── notify/
│   └── telegram.py          # Telegram alerts with retry queue
└── utils/
    ├── config.py            # YAML config loader
    └── logger.py            # Structured logging (structlog)
```

## Quick Start

### Prerequisites

- Python 3.11+
- A Hyperliquid account (testnet for development)
- Telegram bot token (optional, for notifications)

### Installation

```bash
git clone https://github.com/zhy0216/hyperquant.git
cd hyperquant
make install  # or: pip install -e ".[dev]"
```

### Configuration

1. Copy and edit the environment file:

```bash
cp .env.example .env
# Edit .env with your API keys
```

2. Adjust strategy parameters in `config.yaml` as needed.

### Running

```bash
# Dry-run mode (no real orders)
python main.py --dry-run

# Docker
make docker-up
```

## Development

```bash
make test        # Run tests with coverage
make lint        # Check code with ruff
make fmt         # Auto-format code
make typecheck   # Run mypy
```

The project enforces strict typing (`mypy --disallow-untyped-defs`) and linting (`ruff`). CI runs on every push via GitHub Actions.

## Risk Disclaimer

**This software is for educational and research purposes.** Trading cryptocurrencies involves substantial risk of loss. HyperQuant is not financial advice. Use at your own risk and never trade with money you cannot afford to lose. Always test thoroughly on testnet before any live trading.

## Contributing

Contributions are welcome. Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

