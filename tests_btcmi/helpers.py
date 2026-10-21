"""Offline test helpers: fake exchanges that honour the paging parameters of the real endpoints."""
from __future__ import annotations

import unittest
from unittest import mock

from btcmi import db, http
from btcmi.collectors import _common as C

HOUR = 3_600_000
M15 = 900_000
M5 = 300_000
DAY = 86_400_000
T0 = C.utc_ms(2021, 1, 1)
NOW = C.utc_ms(2021, 1, 10)          # "current time" in every collector test


class CollectorCase(unittest.TestCase):
    """In-memory DB, frozen clock, patched network calls (tests set .get_json.side_effect)."""

    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.now = NOW
        p = mock.patch("btcmi.collectors._common.now_ms", side_effect=lambda: self.now)
        p.start()
        self.addCleanup(p.stop)
        pj = mock.patch("btcmi.http.get_json")
        self.get_json = pj.start()
        self.addCleanup(pj.stop)
        pb = mock.patch("btcmi.http.get_bytes")
        self.get_bytes = pb.start()
        self.addCleanup(pb.stop)

    def count(self, table, where="1=1", args=()):
        return self.conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}", args).fetchone()[0]


def kline(ts: int, i: int = 0, step: int = HOUR) -> list:
    """A Binance kline in the real wire shape (spot and futures): numbers as strings except times/trades."""
    base = 29000.0 + i
    return [ts, f"{base:.2f}", f"{base + 50:.2f}", f"{base - 50:.2f}", f"{base + 10:.2f}", f"{100 + i:.5f}",
            ts + step - 1, f"{(100 + i) * base:.4f}", 1000 + i, f"{40 + i:.5f}", f"{(40 + i) * base:.4f}", "0"]


def make_klines(start: int, n: int, step: int) -> list[list]:
    return [kline(start + k * step, k, step) for k in range(n)]


class BinanceKlineServer:
    """Fake of the klines / premiumIndexKlines endpoints: ascending from startTime, honours endTime and limit.

    A limit above `max_limit` answers like the real API (HTTP 400)."""

    def __init__(self, bars_by_interval: dict[str, list[list]], max_limit: int = 1000):
        self.bars = bars_by_interval
        self.max_limit = max_limit
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, url, params=None, **kw):
        self.calls.append((url, dict(params)))
        if params["limit"] > self.max_limit:
            raise http.HttpError("HTTP 400", 400, url)
        out = [b for b in self.bars[params["interval"]]
               if b[0] >= params["startTime"] and ("endTime" not in params or b[0] <= params["endTime"])]
        return out[:params["limit"]]


class BybitServer:
    """Fake of the Bybit v5 list endpoints: newest first, optional silent cap below the requested limit.

    `items` are dicts or lists; `ts_of` extracts the ms timestamp. nextPageCursor is always non-empty
    (as the real account-ratio endpoint does on its last page)."""

    def __init__(self, items: list, ts_of, cap: int | None = None, max_limit: int = 1000, now: int | None = None):
        self.items = sorted(items, key=ts_of, reverse=True)
        self.ts_of = ts_of
        self.cap = cap
        self.max_limit = max_limit
        self.now = now
        self.calls: list[dict] = []

    def __call__(self, url, params=None, **kw):
        self.calls.append(dict(params))
        start = params.get("start", params.get("startTime"))
        end = params.get("end", params.get("endTime"))
        assert params["limit"] <= self.max_limit, "limit above the endpoint maximum"
        if self.now is not None and end is not None and end > self.now:
            return {"retCode": 0, "retMsg": "OK", "result": {"list": [], "nextPageCursor": ""}}
        out = [i for i in self.items
               if (start is None or self.ts_of(i) >= start) and (end is None or self.ts_of(i) <= end)]
        n = params["limit"] if self.cap is None else min(params["limit"], self.cap)
        return {"retCode": 0, "retMsg": "OK", "result": {"list": out[:n], "nextPageCursor": "abc"}}
