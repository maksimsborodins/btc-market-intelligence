"""Shared helpers for collectors."""
from __future__ import annotations

import time
from datetime import datetime, timezone

from btcmi import http
from btcmi.db import INTERVAL_MS

SEC = 1000
M5 = 300_000
HOUR = 3_600_000
DAY = 86_400_000


def now_ms() -> int:
    return int(time.time() * 1000)


def utc_ms(year: int, month: int, day: int) -> int:
    return int(datetime(year, month, day, tzinfo=timezone.utc).timestamp() * 1000)


def iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def day_floor(ms: int) -> int:
    return ms - ms % DAY


def align_up(ms: int, step: int) -> int:
    return -(-ms // step) * step


def stop_ms(end_ms: int | None) -> int:
    n = now_ms()
    return n if end_ms is None else min(int(end_ms), n)


def effective_start(start_ms: int, last: int | None, step: int) -> int:
    """Resume rule: never re-fetch what is stored."""
    return int(start_ms) if last is None else max(int(start_ms), last + step)


def forward_pages(fetch, start: int, stop: int, step: int, limit: int):
    """Page forward through a kline-style endpoint (ascending, array rows with open time at idx 0).

    `fetch(cur)` must return the raw page whose first row is the first bar >= cur.
    Stops on an empty page, on a short page (fewer than `limit` rows) or when `stop` is passed.
    """
    cur = start
    while cur <= stop:
        raw = fetch(cur)
        if not raw:
            return
        yield raw
        nxt = max(int(r[0]) for r in raw) + step
        if nxt <= cur or len(raw) < limit:
            return
        cur = nxt


def backward_pages(fetch, start: int, stop: int, ts_of):
    """Page backwards through a newest-first endpoint.

    `fetch(end)` returns the newest-first page of items with ts <= end (and >= start).
    Continues until an empty page or until the oldest item reaches `start`. A short page is
    deliberately NOT treated as the end (silent caps), only an empty page or reaching `start` is.
    """
    end = stop
    while end >= start:
        items = fetch(end)
        if not items:
            return
        yield items
        oldest = min(ts_of(i) for i in items)
        if oldest <= start or oldest - 1 >= end:
            return
        end = oldest - 1


def klines_to_bars(venue: str, symbol: str, interval: str, raw: list) -> list[dict]:
    """Binance kline arrays -> bar rows. idx: 0 open time, 1-4 OHLC, 5 volume, 7 quote vol, 8 trades, 9 taker buy base."""
    return [{
        "venue": venue, "symbol": symbol, "interval": interval, "ts": int(k[0]),
        "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]),
        "volume": float(k[5]), "quote_volume": float(k[7]), "taker_buy_volume": float(k[9]),
        "trades": int(k[8]),
    } for k in raw]


def keep_closed(rows: list[dict], step: int, stop: int, now: int | None = None, min_ts: int | None = None) -> list[dict]:
    """Keep rows whose bar is closed (ts + step <= now), whose open ts <= stop and >= min_ts."""
    now = now_ms() if now is None else now
    return [r for r in rows
            if r["ts"] + step <= now and r["ts"] <= stop and (min_ts is None or r["ts"] >= min_ts)]


def bybit_list(resp) -> list:
    """Unwrap a Bybit v5 envelope; raise on retCode != 0."""
    if not isinstance(resp, dict) or resp.get("retCode") != 0:
        raise http.HttpError(f"Bybit error: {str(resp)[:300]}")
    return (resp.get("result") or {}).get("list") or []


def step_ms(interval: str) -> int:
    return INTERVAL_MS[interval]
