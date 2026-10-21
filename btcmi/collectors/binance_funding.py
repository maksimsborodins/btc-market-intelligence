"""Binance funding rate history -> series binance.funding (ts = available_at = fundingTime).

startTime=0 is ignored by the endpoint (it returns the newest rows), so a real startTime is always passed.
Limit 1000 (1001 -> error JSON with HTTP 200).
"""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "binance_funding"
URL = "https://fapi.binance.com/fapi/v1/fundingRate"
SYMBOL = "BTCUSDT"
METRIC = "binance.funding"
LIMIT = 1000
EARLIEST = C.utc_ms(2019, 9, 10)


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    last = db.last_ts(conn, metric=METRIC)
    cur = max(C.effective_start(start_ms, last, 1), EARLIEST)
    total = 0
    while cur <= stop:
        raw = http.get_json(URL, {"symbol": SYMBOL, "startTime": cur, "endTime": stop, "limit": LIMIT})
        if not raw:
            break
        rows = [{"metric": METRIC, "ts": int(r["fundingTime"]), "value": float(r["fundingRate"]),
                 "available_at": int(r["fundingTime"])} for r in raw]
        total += db.upsert_series(conn, rows)
        nxt = max(r["ts"] for r in rows) + 1
        if nxt <= cur or len(raw) < LIMIT:
            break
        cur = nxt
    return total
