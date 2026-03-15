import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from backtest.data_loader import CsvLoader, DataLoader, ParquetLoader
from backtest.engine import BacktestEngine
from backtest.metrics import compute_metrics
from backtest.report import ReportGenerator
from strategy.signal_engine import SignalEngine
from utils.config import load_config
from utils.logger import setup_logging


def _parse_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc)


def _resolve_strategy(name: str) -> type:
    if name == "default" or name == "signal_engine":
        return SignalEngine
    # Dynamic import: "module.ClassName"
    import importlib
    module_path, class_name = name.rsplit(".", 1)
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)  # type: ignore[no-any-return]


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

    config: dict[str, Any] = load_config(args.config)
    log_cfg = config.get("logging", {})
    setup_logging(
        level=log_cfg.get("level", "INFO"),
        log_file=log_cfg.get("file", "logs/hyperquant.log"),
        max_size_mb=log_cfg.get("max_size_mb", 50),
        backup_count=log_cfg.get("backup_count", 5),
    )

    # Override config with CLI args
    bt_cfg: dict[str, Any] = config.setdefault("backtest", {})
    if args.initial_equity:
        bt_cfg["initial_equity"] = args.initial_equity
    if args.slippage:
        bt_cfg["slippage"] = args.slippage

    # Resolve loader
    loader: DataLoader
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
