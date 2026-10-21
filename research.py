"""Run the research on the stored history: python research.py [--db PATH] [--since YYYY-MM-DD] [--out DIR]"""

import argparse
import datetime
import sys
import time
import warnings
from pathlib import Path

from btcmi import db
from btcmi.features import add_targets, build_picture
from btcmi.research import run_research, save


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db", default=None)
    p.add_argument("--since", default="2020-09-01", help="first decision date (Binance OI archive starts 2020-09-01)")
    p.add_argument("--out", default=str(Path(__file__).resolve().parent / "research"))
    args = p.parse_args(argv)
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    start_ms = int(datetime.datetime.fromisoformat(args.since).replace(tzinfo=datetime.timezone.utc).timestamp() * 1000)
    conn = db.connect(args.db)
    t0 = time.time()
    df = add_targets(build_picture(conn, start_ms=start_ms))
    print(f"picture: {len(df)} hourly rows, {df.shape[1]} columns, {time.time() - t0:.1f}s")
    report = run_research(df)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    save(report, out / f"report_{stamp}.json", out / f"report_{stamp}.md")
    accepted_f = sum(r["accepted"] for r in report["features"])
    accepted_s = sum(r["accepted"] for r in report["states"])
    print(f"tests: {report['tests']}, accepted features: {accepted_f}, accepted states: {accepted_s}, "
          f"total {time.time() - t0:.0f}s -> {out / f'report_{stamp}.md'}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
