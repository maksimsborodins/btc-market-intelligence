"""Oligator variants: range traffic light, limit retest entry, 4h filter, wider stop, teeth exit.

python checks/oligator_variants.py --db PATH  ->  research/strategies/variants/report.md + trades_<variant>.csv
DEV = entries 2020-09..2023-12, HOLDOUT = 2024-01..now. Funding is the real Binance history.
"""

import argparse
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from btcmi import db  # noqa: E402
from btcmi.range_model import history, hourly  # noqa: E402
from btcmi.strategies import COST_STOP, load_15m, oligator, set_funding, to_frame  # noqa: E402
from checks.strategies_backtest import ERA_CUT, HEAD, SEP, START, line, ms, random_control  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "research" / "strategies" / "variants"
COLORS = ("green", "yellow", "red", "none")


def eras(t: pd.DataFrame, col: str = "entry_ts"):
    cut = ms(ERA_CUT)
    return {"DEV 2020-09..2023": t[(t[col] < cut) & (t[col] >= ms(START))], "HOLDOUT 2024..now": t[t[col] >= cut]}


def table(t: pd.DataFrame, extra: bool = True) -> list[str]:
    out = [HEAD, SEP] + [line(k, v) for k, v in eras(t).items()]
    return out


def add_color(rc: pd.DataFrame, fc: pd.DataFrame) -> pd.DataFrame:
    """Colour of the forecast made at the hourly close just before the random entry (entries are on the hour)."""
    rc = rc.copy()
    rc["range_color"] = fc["color"].reindex(rc["entry_ts"]).fillna("none").to_numpy()
    return rc


def by_color(t: pd.DataFrame, label: str) -> list[str]:
    out = [HEAD, SEP]
    for era, part in eras(t).items():
        for c in COLORS:
            out.append(line(f"{label} {era}, {c}", part[part["range_color"] == c]))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    args = ap.parse_args(argv)
    warnings.filterwarnings("ignore")
    conn = db.connect(args.db)
    b15 = load_15m(conn, start_ms=ms(START) - 30 * 86_400_000)
    set_funding(conn)
    fc = history(hourly(conn))[["color", "pred_24h_pct"]]
    OUT.mkdir(parents=True, exist_ok=True)
    log2a, log2b = [], []

    def run(**kw):
        return to_frame(oligator(b15, "trail", forecast=fc, **kw))

    variants = {
        "V0_base": run(),
        "V1_only_green": run(only_colors={"green"}),
        "V1b_only_red": run(only_colors={"red"}),
        "V2a_limit_retest_4h": run(entry="limit_retest", retest_h=4, log=log2a),
        "V2b_limit_retest_12h": run(entry="limit_retest", retest_h=12, log=log2b),
        "V3_min_stop_0.95pct": run(min_stop=COST_STOP),
        "V4_filter_4h": run(filter_4h=True),
    }
    variants["V5_exit_teeth"] = to_frame(oligator(b15, "teeth", forecast=fc))
    lines = ["# Oligator variants", "",
             "Binance BTCUSDT perp, 1h Alligator + fractals, entries from 2020-09-01, real funding, exit = fractal trail "
             "unless stated. R = result / $10 after costs. DEV = entries 2020-09..2023-12, HOLDOUT = 2024-01..now. "
             "Range colour = traffic light of the walk-forward 24h range forecast (btcmi/range_model.py) at the last "
             "hourly close before the entry; the forecast exists from 2021-02 (earlier trades are \"none\"). "
             "V1/V1b skip the signal when the colour differs (so the position slot is free for the next signal). "
             "V2: limit order at the fractal level after the breach, filled only on a strictly-through trade, maker fee, "
             "no slippage; the slot is busy while the order is pending. V4: 4h Alligator mouth open in the trade "
             "direction on the last completed 4h bar. V5: exit at the first 1h close beyond the 1h teeth (initial stop "
             "still applies).", ""]
    for name, t in variants.items():
        t = t[t["entry_ts"] >= ms(START)].reset_index(drop=True)
        variants[name] = t
        t.to_csv(OUT / f"trades_{name}.csv", index=False)
        lines += [f"## {name}", ""] + table(t) + [""]
        print(name, len(t), flush=True)
    v0 = variants["V0_base"]
    lines += ["## V0 by range colour", ""] + by_color(v0, "V0") + [""]
    rc = add_color(random_control(b15, v0, np.random.default_rng(11)), fc)
    lines += ["### Control: V0's side and stop distance, random entry hour, fractal trail (5 draws per trade), by colour at "
              "the random entry", ""] + [HEAD, SEP, line("random all", rc)] + by_color(rc, "random")[2:] + [""]
    # V2: fill rate and what the unfilled signals would have done as stop-market entries
    for name, lg in (("V2a_limit_retest_4h", log2a), ("V2b_limit_retest_12h", log2b)):
        lg = pd.DataFrame(lg)
        lg = lg[lg["trigger_ts"] >= ms(START)]
        m = lg.merge(v0[["entry_ts", "side", "r_net"]].rename(columns={"entry_ts": "trigger_ts"}), on=["trigger_ts", "side"],
                     how="left")
        lines += [f"## {name}: fill rate and the signals that did not fill", "",
                  "| sample | limit orders | filled | fill rate | unfilled with a V0 trade | their V0 avg R net | their V0 total R | "
                  "V0 win | filled with a V0 trade | their V0 avg R net |", "|---|---|---|---|---|---|---|---|---|---|"]
        cut = ms(ERA_CUT)
        for era, part in (("DEV", m[m["trigger_ts"] < cut]), ("HOLDOUT", m[m["trigger_ts"] >= cut])):
            un = part[~part["filled"] & part["r_net"].notna()]
            fi = part[part["filled"] & part["r_net"].notna()]
            lines.append(f"| {era} | {len(part)} | {int(part['filled'].sum())} | {part['filled'].mean():.0%} | {len(un)} | "
                         f"{un['r_net'].mean():+.3f} | {un['r_net'].sum():+.1f} | {(un['r_net'] > 0).mean():.0%} | {len(fi)} | "
                         f"{fi['r_net'].mean():+.3f} |")
        lines.append("")
    (OUT / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
