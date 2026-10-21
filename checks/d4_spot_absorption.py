"""D4: is "price down 24h while spot takers net buy" better than a 24h drop of the same size without spot buying?

python checks/d4_spot_absorption.py --db PATH

Signal events: onsets of (24h drop AND spot takers net buying over the 24h). Control events: onsets of (24h drop AND
spot takers net selling). Separate onsets, so the start of a plain drop cannot block spot buying that appears later in
the same drop. Compared within drop-size quintiles (quintiles of each sample itself), CI by calendar-block bootstrap
(72 h blocks). Direction fixed in advance: signal > control (long). Reported per era, with and without Binance's
zero-fee BTCUSDT period.
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
from btcmi.events import onsets, stratified_diff  # noqa: E402
from btcmi.features import _direction, add_targets, build_picture  # noqa: E402
from btcmi.research import COST  # noqa: E402

H = 24
BLOCK_H = 72
ZERO_FEE = ("2022-07-08", "2023-03-22")   # Binance 0% taker fee on BTCUSDT spot: taker flow distorted
ERAS = {"2020-09..2023-12": ("2020-09-01", "2024-01-01"), "2024-01..now": ("2024-01-01", "2100-01-01")}


def ms(day: str) -> int:
    return int(dt.datetime.fromisoformat(day).replace(tzinfo=dt.timezone.utc).timestamp() * 1000)


def events(df: pd.DataFrame, drop: pd.Series) -> pd.DataFrame:
    buy = df[f"spot_delta_{H}h"] > 0
    known = df[f"spot_delta_{H}h"].notna()
    sig = onsets(drop & buy & known, H)
    ctrl = onsets(drop & ~buy & known, H)
    ev = df.loc[sig | ctrl, ["y", "size"]].copy()
    ev["signal"] = sig[sig | ctrl]
    return ev[ev["y"].notna()]


def row(ev: pd.DataFrame, label: str, rng) -> str:
    r = stratified_diff(ev, BLOCK_H, rng)
    s, c = ev[ev.signal].y, ev[~ev.signal].y
    if r["strata"] == 0:
        return f"| {label} | {r['n_signal']} | {r['n_control']} | too few events | | | |"
    return (f"| {label} | {r['n_signal']} | {r['n_control']} | {s.mean():+.2%} ({(s > 0).mean():.0%} up) | "
            f"{c.mean():+.2%} ({(c > 0).mean():.0%} up) | {r['diff']:+.2%} [{r['lo']:+.2%}, {r['hi']:+.2%}] t={r['t']:.1f} | "
            f"{s.mean() - COST:+.2%} |")


def table(ev: pd.DataFrame, rng) -> list[str]:
    zf = (ev.index >= ms(ZERO_FEE[0])) & (ev.index < ms(ZERO_FEE[1]))
    lines = ["| sample | signal events | control events | signal mean | control mean | same-size difference [95% CI] | signal long after cost |",
             "|---|---|---|---|---|---|---|"]
    for name, (a, b) in ERAS.items():
        era = (ev.index >= ms(a)) & (ev.index < ms(b))
        lines.append(row(ev[era], name, rng))
        if (era & zf).any():
            lines.append(row(ev[era & ~zf], name + " without zero-fee", rng))
    lines.append(row(ev, "all", rng))
    lines.append(row(ev[~zf], "all without zero-fee", rng))
    return lines


def main(argv=None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--db", required=True)
    args = p.parse_args(argv)
    warnings.filterwarnings("ignore")
    conn = db.connect(args.db)
    df = add_targets(build_picture(conn, start_ms=ms("2020-09-01")))
    df["y"] = df[f"fwd_{H}h"]
    df["size"] = df[f"ret_{H}h"] / df[f"ret_{H}h"].rolling(720, min_periods=360).std()
    rng = np.random.default_rng(7)
    lines = [f"# D4 spot absorption check ({dt.date.today()})", "",
             f"Signal: onset of (ret_{H}h below the drop threshold AND spot takers net buying over {H} h). Control: onset of "
             f"(same drop AND spot takers net selling). {H} h between events of each kind. Outcome: next {H} h log return "
             f"of the spot close. Difference within drop-size quintiles, 95% CI by {BLOCK_H} h calendar-block bootstrap. "
             f"Pre-registered direction: signal > control. Cost {COST:.2%} round trip.", "",
             "## Main test: drop = ret_24h below -0.25 rolling std (the state definition)", ""]
    lines += table(events(df, _direction(df[f"ret_{H}h"]) == -1), rng)
    lines += ["", "## Secondary: real drops only, ret_24h below -1.0 rolling std", ""]
    lines += table(events(df, df["size"] < -1.0), rng)
    text = "\n".join(lines)
    print(text)
    out = Path(__file__).resolve().parent.parent / "research" / "fixed" / "d4_spot_absorption.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
