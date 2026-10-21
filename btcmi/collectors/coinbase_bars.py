"""Coinbase Exchange BTC-USD 1h candles.

Max 300 candles per request (301 intervals -> HTTP 400; `end` is inclusive), so the range is walked
forward in windows of 300 bars. Rows are newest first: [time (SECONDS), low, high, open, close, volume].
Hours without trades are absent in early history, so an empty window does not end the run.
"""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "coinbase_bars"
URL = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
VENUE = "coinbase_spot"
SYMBOL = "BTC-USD"
INTERVAL = "1h"
GRANULARITY = 3600
LIMIT = 300
EARLIEST = C.utc_ms(2015, 7, 20)


def parse(raw: list) -> list[dict]:
    return [{"venue": VENUE, "symbol": SYMBOL, "interval": INTERVAL, "ts": int(k[0]) * 1000,
             "open": float(k[3]), "high": float(k[2]), "low": float(k[1]), "close": float(k[4]),
             "volume": float(k[5])} for k in raw]


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    step = C.step_ms(INTERVAL)
    last = db.last_ts(conn, venue=VENUE, symbol=SYMBOL, interval=INTERVAL)
    cur = C.align_up(max(C.effective_start(start_ms, last, step), EARLIEST), step)
    total = 0
    while cur <= stop:
        w_end = min(cur + (LIMIT - 1) * step, stop)
        raw = http.get_json(URL, {"granularity": GRANULARITY, "start": C.iso(cur), "end": C.iso(w_end)})
        if not isinstance(raw, list):
            raise http.HttpError(f"unexpected Coinbase response: {str(raw)[:200]}")
        rows = [r for r in C.keep_closed(parse(raw), step, stop, min_ts=cur)]
        total += db.upsert_bars(conn, rows)
        cur = w_end + step
    return total
