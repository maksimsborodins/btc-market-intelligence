"""D4: is "price down 24h while spot takers net buy" better than any 24h drop of the same size?

python checks/d4_spot_absorption.py --db PATH

Events are onsets (first hour the condition holds, then 24 h blocked), so outcomes do not overlap and every event is
one trade. Signal events are compared with all drop onsets (the control), overall and within drop-size quintiles
(a stronger drop is a different trade). Reported per era, with and without Binance's zero-fee BTCUSDT period.
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
from btcmi.features import _direction, add_targets, build_picture  # noqa: E402
from btcmi.research import COST  # noqa: E402

H = 24
ZERO_FEE = ("2022-07-08", "2023-03-22")   # Binance 0% taker fee on BTCUSDT spot: taker flow distorted
ERAS = {"2020-09..2023-12": ("2020-09-01", "2024-01-01"), "2024-01..now": ("2024-01-01", "2100-01-01")}


def ms(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def onsets(cond: pd.Series, block_h: int) -> np.ndarray:
    """First hour of each episode, with at least block_h hours between events."""
    c = cond.fillna(False).to_numpy()
    out = np.zeros(len(c), dtype=bool)
    next_free = -1
    for i in np.flatnonzero(c):
        if i >= next_free and (i == 0 or not c[i - 1]):
            out[i] = True
            next_free = i + block_h
    return out


def boot_diff(a: np.ndarray, b: np.ndarray, rng, n=5000) -> tuple[float, float, float]:
    d = a.mean() - b.mean()
    ra = rng.choice(a, size=(n, len(a))).mean(axis=1)
    rb = rng.choice(b, size=(n, len(b))).mean(axis=1)
    lo, hi = np.percentile(ra - rb, [2.5, 97.5])
    return d, lo, hi


def welch_t(a, b) -> float:
    return (a.mean() - b.mean()) / np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))


def stratified_diff(df: pd.DataFrame) -> float:
    """Signal minus control within drop-size quintiles, weighted by the signal's events per quintile."""
    diffs, weights = [], []
    for _, g in df.groupby("size_q"):
        s, c = g[g.signal], g[~g.signal]
        if len(s) >= 3 and len(c) >= 3:
            diffs.append(s.y.mean() - c.y.mean())
            weights.append(len(s))
    return float(np.average(diffs, weights=weights)) if diffs else np.nan


def report(ev: pd.DataFrame, label: str, rng) -> str:
    s, c = ev[ev.signal].y.to_numpy(), ev[~ev.signal].y.to_numpy()
    if len(s) < 10 or len(c) < 10:
        return f"| {label} | {len(s)} | {len(c)} | too few events | | | | |"
    d, lo, hi = boot_diff(s, c, rng)
    return (f"| {label} | {len(s)} | {len(c)} | {s.mean():+.2%} ({(s > 0).mean():.0%} up) | {c.mean():+.2%} ({(c > 0).mean():.0%} up) | "
            f"{d:+.2%} [{lo:+.2%}, {hi:+.2%}] t={welch_t(s, c):.1f} | {stratified_diff(ev):+.2%} | {s.mean() - COST:+.2%} |")


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    args = p.parse_args(argv)
    warnings.filterwarnings("ignore")
    conn = db.connect(args.db)
    df = add_targets(build_picture(conn, start_ms=ms("2020-09-01")))
    down = _direction(df[f"ret_{H}h"]) == -1
    df["y"] = df[f"fwd_{H}h"]
    df["size"] = df[f"ret_{H}h"] / df[f"ret_{H}h"].rolling(720, min_periods=360).std()
    ev = df[onsets(down, H)].copy()
    ev = ev[ev.y.notna() & ev[f"spot_delta_{H}h"].notna()]
    ev["signal"] = ev[f"spot_delta_{H}h"] > 0
    ev["oi_down"] = ev[f"oi_chg_{H}h"] < 0
    ev["size_q"] = pd.qcut(ev["size"], 5, labels=False)
    zf = (ev.index >= ms(ZERO_FEE[0])) & (ev.index < ms(ZERO_FEE[1]))

    rng = np.random.default_rng(7)
    lines = [f"# D4 spot absorption check ({dt.date.today()})", "",
             f"Drop onsets: ret_{H}h below -0.25 rolling std, first hour of the episode, {H} h between events. "
             f"Signal: spot takers net buying over the same {H} h. Outcome: next {H} h log return of the spot close. "
             f"Cost {COST:.2%} round trip.", "",
             "| sample | signal events | control events | signal mean | control mean | difference [95% CI] | same-size difference | signal long after cost |",
             "|---|---|---|---|---|---|---|---|"]
    for name, (a, b) in ERAS.items():
        era = (ev.index >= ms(a)) & (ev.index < ms(b))
        lines.append(report(ev[era], name, rng))
        if (era & zf).any():
            lines.append(report(ev[era & ~zf], name + " without zero-fee", rng))
    lines.append(report(ev, "all", rng))
    lines.append(report(ev[~zf], "all without zero-fee", rng))
    lines += ["", "Exploratory add-on (not a pre-registered test): signal events split by OI over the same 24 h", "",
              "| OI over 24 h | events | mean next 24 h | up |", "|---|---|---|---|"]
    sig = ev[ev.signal]
    for flag, name in ((True, "OI down"), (False, "OI up/flat")):
        g = sig[sig.oi_down == flag].y
        lines.append(f"| {name} | {len(g)} | {g.mean():+.2%} | {(g > 0).mean():.0%} |")
    text = "\n".join(lines)
    print(text)
    out = Path(__file__).resolve().parent.parent / "research" / "fixed" / "d4_spot_absorption.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
