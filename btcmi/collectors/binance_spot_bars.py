"""Binance spot klines BTCUSDT 15m and 1h (with taker buy volume). Forward paging, 1000 per page."""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "binance_spot_bars"
HOSTS = ["https://api.binance.com", "https://data-api.binance.vision"]
PATH = "/api/v3/klines"
VENUE = "binance_spot"
SYMBOL = "BTCUSDT"
INTERVALS = ("15m", "1h")
LIMIT = 1000


def _fetch(params: dict):
    last = None
    for host in HOSTS:
        try:
            return http.get_json(host + PATH, params)
        except http.HttpError as e:
            last = e
    raise last


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    total = 0
    for interval in INTERVALS:
        step = C.step_ms(interval)
        last = db.last_ts(conn, venue=VENUE, symbol=SYMBOL, interval=interval)
        start = C.effective_start(start_ms, last, step)

        def fetch(cur, interval=interval):
            return _fetch({"symbol": SYMBOL, "interval": interval, "startTime": cur,
                           "endTime": stop, "limit": LIMIT})

        for raw in C.forward_pages(fetch, start, stop, step, LIMIT):
            rows = C.keep_closed(C.klines_to_bars(VENUE, SYMBOL, interval, raw), step, stop)
            total += db.upsert_bars(conn, rows)
    return total
