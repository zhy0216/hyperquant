import base64
import csv
import io
import os
from dataclasses import fields
from datetime import datetime, timezone
from typing import Any

from backtest.trade_log import TradeRecord


class ReportGenerator:
    def __init__(
        self,
        trades: list[TradeRecord],
        metrics: dict[str, Any],
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
                    print(f"  {key} ({label:.<35}) {value:>10.2%}")
                else:
                    print(f"  {key} ({label:.<35}) {value:>10.4f}")
            else:
                print(f"  {key} ({label:.<35}) {str(value):>10}")
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
            dd: list[float] = []
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
                if i < len(self._timestamps):
                    dt = datetime.fromtimestamp(self._timestamps[i] / 1000, tz=timezone.utc)
                    ret = (self._equity_curve[i] - self._equity_curve[i - 1]) / self._equity_curve[i - 1]
                    monthly[(dt.year, dt.month)] += ret

            if monthly:
                years = sorted(set(k[0] for k in monthly))
                months = list(range(1, 13))
                data: list[list[float]] = []
                for y in years:
                    data.append([monthly.get((y, m), 0) * 100 for m in months])

                fig, ax = plt.subplots(figsize=(12, max(3, len(years))))
                im = ax.imshow(data, cmap="RdYlGn", aspect="auto")
                ax.set_xticks(range(12))
                ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
                ax.set_yticks(range(len(years)))
                ax.set_yticklabels([str(y) for y in years])
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
        chart_dir = os.path.join(os.path.dirname(path) or ".", ".charts_tmp")
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
            metrics_rows += f"<tr><td>{key} ({label})</td><td>{formatted}</td></tr>\n"

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
