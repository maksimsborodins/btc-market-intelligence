"""Out-of-sample evaluation of the range forecast (btcmi/range_model.py).

python checks/range_report.py --db PATH  ->  research/range/report.md (+ range_forecast.csv used by the variants check)
"""

import argparse
import datetime as dt
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from btcmi import db  # noqa: E402
from btcmi.range_model import history, hourly, pct, walk_forward  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "research" / "range"
ERAS = {"2022-01..2023-12": ("2022-01-01", "2024-01-01"), "2024-01..now": ("2024-01-01", "2100-01-01")}
MODELS = {"model": None, "b1: ln d only": ("d",), "b2: ln m only (30d)": ("m",)}


def ms(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def r2(y, p):
    return 1 - np.sum((y - p) ** 2) / np.sum((y - y.mean()) ** 2)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    conn = db.connect(args.db)
    b = hourly(conn)
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [f"# Range forecast, out-of-sample ({dt.date.today()})", "",
             "Target: ln(max high / min low) over the next H hours, Binance BTCUSDT perp 1h. OLS refit at every calendar "
             "month start on rows whose target had ended (>= 12 months of training); features: ln of the last-6h range, "
             "last-24h range, mean of 7 and of 30 daily ranges, and a seasonal term (hour-of-week mean ranges from "
             "training data). R2 is on the log scale against the mean of the evaluated era; MAE is on the log scale. "
             "Baselines are fitted the same walk-forward way. Targets overlap (H hours), so there are no t-stats; "
             "numbers are descriptive.", ""]
    first = None
    for H in (6, 24):
        preds = {name: walk_forward(b, H, **({"cols": c} if c else {}))[0] for name, c in MODELS.items()}
        first = preds["model"].index[0]
        common = preds["model"].index
        for p in preds.values():
            common = common.intersection(p.index)
        lines += [f"## Horizon {H} h", ""]
        for era, (a, z) in ERAS.items():
            idx = [t for t in common if ms(a) <= t < ms(z)]
            m = preds["model"].loc[idx]
            m = m[np.isfinite(m["target"])]
            y = m["target"].to_numpy()
            lines += [f"### {era} (n = {len(m)})", "", "| model | R2 (log) | MAE (log) |", "|---|---|---|"]
            for name, p in preds.items():
                q = p.loc[m.index, "pred"].to_numpy()
                lines.append(f"| {name} | {r2(y, q):.3f} | {np.mean(np.abs(y - q)):.3f} |")
            cov = float(((y >= m["lo"]) & (y <= m["hi"])).mean())
            lines += ["", f"80% interval coverage: {cov:.1%} (target 80%). Mean width (log): "
                          f"{float((m['hi'] - m['lo']).mean()):.3f}.", "",
                      "Calibration (5 bins of the predicted value): | bin | n | mean predicted % | mean actual % | median actual % |",
                      "|---|---|---|---|---|"]
            bins = pd.qcut(m["pred"], 5, labels=False, duplicates="drop")
            for k in sorted(bins.unique()):
                s = m[bins == k]
                lines.append(f"| {k + 1} | {len(s)} | {pct(s['pred']).mean():.2f} | {pct(s['target']).mean():.2f} | "
                             f"{pct(s['target']).median():.2f} |")
            lines.append("")
    h = history(b)
    h.to_csv(OUT / "range_forecast.csv")
    lines += ["## Traffic light on the 24h forecast", "", "Share of hours by colour and mean actual next-24h range:", "",
              "| colour | hours | mean pred 24h % |", "|---|---|---|"]
    for c in ("red", "yellow", "green", "none"):
        s = h[h["color"] == c]
        lines.append(f"| {c} | {len(s)} | {s['pred_24h_pct'].mean():.2f} |")
    lines += ["", f"First walk-forward prediction: {pd.Timestamp(first, unit='ms')}."]
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
