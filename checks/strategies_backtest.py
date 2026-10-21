"""Backtest of the user's strategies (Oligator 1h, RSI30m) on Binance BTCUSDT perp, 2020-09 .. now.

python checks/strategies_backtest.py --db PATH  ->  research/strategies/report.md + trades_<variant>.csv
"""

import argparse
import datetime as dt
import re
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from btcmi import db  # noqa: E402
from btcmi.strategies import (  # noqa: E402
    COST_STOP, OLIGATOR_EXITS, load_15m, oligator, rsi30m, set_funding, to_frame,
)

OUT = Path(__file__).resolve().parent.parent / "research" / "strategies"
START = "2020-09-01"
ERA_CUT = "2024-01-01"


def ms(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def stats(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"n": 0}
    r = t["r_net"].to_numpy()
    eq = np.cumsum(r)
    dd = float(np.max(np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq)) if len(r) else 0.0
    months = max((t["entry_ts"].max() - t["entry_ts"].min()) / (30.44 * 86_400_000), 1)
    wins, losses = r[r > 0].sum(), -r[r < 0].sum()
    return {
        "n": len(r), "per_month": len(r) / months, "win": float((r > 0).mean()), "avg_r": float(r.mean()),
        "t": float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))) if len(r) > 2 else np.nan,
        "total_r": float(r.sum()), "pf": float(wins / losses) if losses > 0 else np.inf, "max_dd_r": dd,
        "avg_gross_r": float(t["r_gross"].mean()), "avg_fee_r": float(t["fee_r"].mean()),
        "median_stop": float(t["stop_pct"].median()), "fee_over_15": float((t["fee_r"] > 0.15).mean()),
    }


HEAD = ("| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs | "
        "costs R/trade | median stop | trades with costs > 15% of risk |")
SEP = "|---|---|---|---|---|---|---|---|---|---|---|---|"


def line(label: str, t: pd.DataFrame) -> str:
    s = stats(t)
    if s["n"] < 5:
        return f"| {label} | {s['n']} | too few | | | | | | | | | |"
    return (f"| {label} | {s['n']} | {s['per_month']:.1f} | {s['win']:.0%} | {s['avg_r']:+.3f} [{s['t']:.1f}] | "
            f"{s['total_r']:+.1f} | {s['pf']:.2f} | {s['max_dd_r']:.1f} | {s['avg_gross_r']:+.3f} | {s['avg_fee_r']:.3f} | "
            f"{s['median_stop']:.2%} | {s['fee_over_15']:.0%} |")


def breakdown(t: pd.DataFrame, splits: list[str]) -> list[str]:
    cut = ms(ERA_CUT)
    out = [HEAD, SEP, line("all", t), line("2020-09..2023", t[t.entry_ts < cut]), line("2024..now", t[t.entry_ts >= cut]),
           line("long", t[t.side > 0]), line("short", t[t.side < 0])]
    for col in splits:
        for val in sorted(t[col].dropna().unique(), key=str):
            out.append(line(f"{col} = {val}", t[t[col] == val]))
    return out


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    args = p.parse_args(argv)
    warnings.filterwarnings("ignore")
    conn = db.connect(args.db)
    b15 = load_15m(conn, start_ms=ms(START) - 30 * 86_400_000)
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [f"# Backtest of the user's strategies ({dt.date.today()})", "",
             "Binance BTCUSDT perp 15m bars, entries from 2020-09. Risk $10 per trade; R = result / $10 after costs "
             "(taker 0.05% + slippage 0.02% on stop/market fills, maker 0.02% on take-profits, funding 0.01% per 8 h). "
             "One position at a time, no pyramiding. Stop assumed first when stop and target fall in one 15m bar.", ""]
    set_funding(conn)
    # rules as described, then the improvements that follow from the user's own rules and from the cost arithmetic
    variants = {f"oligator_{e}": (lambda e=e: oligator(b15, e)) for e in OLIGATOR_EXITS}
    variants.update({
        "oligator_ladder + widening": lambda: oligator(b15, "ladder", widening_only=True),
        "oligator_ladder + widening + stop>=0.95%": lambda: oligator(b15, "ladder", True, COST_STOP),
        "oligator_trail + widening + stop>=0.95%": lambda: oligator(b15, "trail", True, COST_STOP),
        "oligator_tp_1pct + widening + stop>=0.95%": lambda: oligator(b15, "tp_1pct", True, COST_STOP),
    })
    variants.update({f"rsi30m_{s}": (lambda s=s: rsi30m(b15, s)) for s in ("pattern", "fib")})
    variants.update({
        "rsi30m_pattern + 4h trend": lambda: rsi30m(b15, "pattern", trend_only=True),
        "rsi30m_pattern + 4h trend + stop>=0.95%": lambda: rsi30m(b15, "pattern", True, COST_STOP),
        "rsi30m_fib + 4h trend": lambda: rsi30m(b15, "fib", trend_only=True),
    })
    for name, run in variants.items():
        t = to_frame(run())
        t.to_csv(OUT / f"trades_{re.sub(r'[^0-9A-Za-z.]+', '_', name)}.csv", index=False)
        splits = (["mouth_open", "widening", "against_prev_trend", "session", "exit_reason"] if name.startswith("oligator")
                  else ["with_trend", "near_level", "pattern", "session", "exit_reason"])
        lines += [f"## {name}", ""] + breakdown(t, splits) + [""]
        print(name, stats(t))
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
