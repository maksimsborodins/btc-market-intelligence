"""Bybit funding history -> series bybit.funding, ts = available_at = fundingRateTimestamp.

Newest first, cap 200 per page; endTime in the future returns empty, so it is capped at now.
"""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "bybit_funding"
URL = "https://api.bybit.com/v5/market/funding/history"
SYMBOL = "BTCUSDT"
METRIC = "bybit.funding"
LIMIT = 200


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)          # never in the future
    last = db.last_ts(conn, metric=METRIC)
    start = C.effective_start(start_ms, last, 1)

    def fetch(end):
        resp = http.get_json(URL, {"category": "linear", "symbol": SYMBOL,
                                   "startTime": start, "endTime": end, "limit": LIMIT})
        return C.bybit_list(resp)

    total = 0
    for page in C.backward_pages(fetch, start, stop, lambda r: int(r["fundingRateTimestamp"])):
        rows = [{"metric": METRIC, "ts": int(r["fundingRateTimestamp"]), "value": float(r["fundingRate"]),
                 "available_at": int(r["fundingRateTimestamp"])} for r in page
                if start <= int(r["fundingRateTimestamp"]) <= stop]
        total += db.upsert_series(conn, rows)
    return total
