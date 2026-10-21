"""Collector runner. Usage: collect.py [--db PATH] [--since YYYY-MM-DD] [--only a,b] [--list]"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone

from btcmi import db
from btcmi.collectors import (binance_funding, binance_metrics, binance_metrics_recent, binance_perp_bars,
                              binance_premium, binance_spot_bars, bybit_bars, bybit_funding, bybit_ls_ratio,
                              bybit_oi, coinbase_bars)

# Order matters: bulk metrics first, then the REST fill for the days the bulk files do not have yet.
COLLECTORS = {m.NAME: m for m in (
    binance_spot_bars, binance_perp_bars, binance_premium, binance_funding,
    binance_metrics, binance_metrics_recent,
    bybit_bars, bybit_oi, bybit_funding, bybit_ls_ratio,
    coinbase_bars,
)}


def run_collectors(conn, names: list[str], start_ms: int, end_ms: int | None = None, out=print) -> dict:
    """Run collectors one after another; a failing collector is logged and does not stop the others."""
    results = {}
    for name in names:
        started = db.now_ms()
        t0 = time.monotonic()
        rows, error = 0, None
        try:
            rows = int(COLLECTORS[name].run(conn, start_ms, end_ms))
        except Exception as e:  # noqa: BLE001 - the runner must survive any single collector
            error = f"{type(e).__name__}: {e}"
        secs = time.monotonic() - t0
        db.log_run(conn, name, started, db.now_ms(), rows, error)
        results[name] = (rows, secs, error)
        out(f"{name:<24} rows={rows:<9} {secs:7.1f}s" + (f"  ERROR: {error}" if error else ""))
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="collect.py", description=__doc__)
    ap.add_argument("--db", default=None, help="SQLite path (default data/market.db)")
    ap.add_argument("--since", default="2020-01-01", help="UTC start date YYYY-MM-DD (default 2020-01-01)")
    ap.add_argument("--only", default=None, help="comma separated collector names")
    ap.add_argument("--list", action="store_true", help="list collector names and exit")
    args = ap.parse_args(argv)

    if args.list:
        for name in COLLECTORS:
            print(name)
        return 0

    names = list(COLLECTORS)
    if args.only:
        names = [n.strip() for n in args.only.split(",") if n.strip()]
        unknown = [n for n in names if n not in COLLECTORS]
        if unknown:
            ap.error(f"unknown collector(s): {', '.join(unknown)}; use --list")
    try:
        since = datetime.strptime(args.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        ap.error("--since must be YYYY-MM-DD")
    start_ms = int(since.timestamp() * 1000)

    conn = db.connect(args.db)
    try:
        results = run_collectors(conn, names, start_ms)
    finally:
        conn.close()
    return 1 if any(err for _, _, err in results.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
