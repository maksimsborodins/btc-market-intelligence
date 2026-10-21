"""Binance USD-M perpetual klines BTCUSDT 15m and 1h. Forward paging, 1500 per page (1501 -> HTTP 400).

The first bars (before 2019-09-09) are flat 10000 placeholders and are dropped.
"""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "binance_perp_bars"
URL = "https://fapi.binance.com/fapi/v1/klines"
VENUE = "binance_perp"
SYMBOL = "BTCUSDT"
INTERVALS = ("15m", "1h")
LIMIT = 1500
MIN_TS = C.utc_ms(2019, 9, 9)


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    total = 0
    for interval in INTERVALS:
        step = C.step_ms(interval)
        last = db.last_ts(conn, venue=VENUE, symbol=SYMBOL, interval=interval)
        start = max(C.effective_start(start_ms, last, step), MIN_TS)

        def fetch(cur, interval=interval):
            return http.get_json(URL, {"symbol": SYMBOL, "interval": interval, "startTime": cur,
                                       "endTime": stop, "limit": LIMIT})

        for raw in C.forward_pages(fetch, start, stop, step, LIMIT):
            rows = C.keep_closed(C.klines_to_bars(VENUE, SYMBOL, interval, raw), step, stop, min_ts=MIN_TS)
            total += db.upsert_bars(conn, rows)
    return total
