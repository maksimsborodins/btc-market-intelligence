"""Bybit linear BTCUSDT 1h klines. Newest first, silent cap 1000: paged backwards with end = oldest - 1.

Row: [start, open, high, low, close, volume, turnover] (strings); no taker split.
"""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "bybit_bars"
URL = "https://api.bybit.com/v5/market/kline"
VENUE = "bybit_perp"
SYMBOL = "BTCUSDT"
INTERVAL = "1h"
BYBIT_INTERVAL = "60"
LIMIT = 1000


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    step = C.step_ms(INTERVAL)
    last = db.last_ts(conn, venue=VENUE, symbol=SYMBOL, interval=INTERVAL)
    start = C.effective_start(start_ms, last, step)

    def fetch(end):
        resp = http.get_json(URL, {"category": "linear", "symbol": SYMBOL, "interval": BYBIT_INTERVAL,
                                   "start": start, "end": end, "limit": LIMIT})
        return C.bybit_list(resp)

    total = 0
    for page in C.backward_pages(fetch, start, stop, lambda k: int(k[0])):
        rows = [{"venue": VENUE, "symbol": SYMBOL, "interval": INTERVAL, "ts": int(k[0]),
                 "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]),
                 "volume": float(k[5]), "quote_volume": float(k[6])} for k in page]
        total += db.upsert_bars(conn, C.keep_closed(rows, step, stop, min_ts=start))
    return total
