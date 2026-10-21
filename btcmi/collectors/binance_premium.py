"""Binance premium index klines (perp vs index) 1h -> series binance.premium (close), available_at = ts + 1h."""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "binance_premium"
URL = "https://fapi.binance.com/fapi/v1/premiumIndexKlines"
SYMBOL = "BTCUSDT"
INTERVAL = "1h"
METRIC = "binance.premium"
LIMIT = 1500


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    step = C.step_ms(INTERVAL)
    last = db.last_ts(conn, metric=METRIC)
    start = C.effective_start(start_ms, last, step)

    def fetch(cur):
        return http.get_json(URL, {"symbol": SYMBOL, "interval": INTERVAL, "startTime": cur,
                                   "endTime": stop, "limit": LIMIT})

    total = 0
    for raw in C.forward_pages(fetch, start, stop, step, LIMIT):
        now = C.now_ms()
        rows = [{"metric": METRIC, "ts": int(k[0]), "value": float(k[4]), "available_at": int(k[0]) + step}
                for k in raw
                if int(k[0]) + step <= now and int(k[0]) <= stop]   # an open bar's close is still moving
        total += db.upsert_series(conn, rows)
    return total
