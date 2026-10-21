"""Bybit long/short account ratio (1h) -> series bybit.ls_buy_ratio (buyRatio), available_at = ts + 1h.

Newest first, cap 500 per page. nextPageCursor is non-empty even on the last page, so it is not used:
paging is by endTime = oldest - 1. The still-open hour is not stored (its ratio is still moving).
"""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "bybit_ls_ratio"
URL = "https://api.bybit.com/v5/market/account-ratio"
SYMBOL = "BTCUSDT"
METRIC = "bybit.ls_buy_ratio"
LIMIT = 500
STEP = C.HOUR


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    last = db.last_ts(conn, metric=METRIC)
    start = C.effective_start(start_ms, last, STEP)

    def fetch(end):
        resp = http.get_json(URL, {"category": "linear", "symbol": SYMBOL, "period": "1h",
                                   "startTime": start, "endTime": end, "limit": LIMIT})
        return C.bybit_list(resp)

    total = 0
    for page in C.backward_pages(fetch, start, stop, lambda r: int(r["timestamp"])):
        now = C.now_ms()
        rows = [{"metric": METRIC, "ts": int(r["timestamp"]), "value": float(r["buyRatio"]),
                 "available_at": int(r["timestamp"]) + STEP} for r in page
                if start <= int(r["timestamp"]) <= stop and int(r["timestamp"]) + STEP <= now]
        total += db.upsert_series(conn, rows)
    return total
