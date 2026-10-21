"""Bybit open interest (hourly, BTC) -> series bybit.oi, ts = available_at = timestamp.

Newest first, silent cap 200 per page: paged backwards with endTime = oldest - 1.
"""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "bybit_oi"
URL = "https://api.bybit.com/v5/market/open-interest"
SYMBOL = "BTCUSDT"
METRIC = "bybit.oi"
LIMIT = 200
STEP = C.HOUR


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    last = db.last_ts(conn, metric=METRIC)
    start = C.effective_start(start_ms, last, STEP)

    def fetch(end):
        resp = http.get_json(URL, {"category": "linear", "symbol": SYMBOL, "intervalTime": "1h",
                                   "startTime": start, "endTime": end, "limit": LIMIT})
        return C.bybit_list(resp)

    total = 0
    for page in C.backward_pages(fetch, start, stop, lambda r: int(r["timestamp"])):
        rows = [{"metric": METRIC, "ts": int(r["timestamp"]), "value": float(r["openInterest"]),
                 "available_at": int(r["timestamp"])} for r in page
                if start <= int(r["timestamp"]) <= stop]
        total += db.upsert_series(conn, rows)
    return total
