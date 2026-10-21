"""Binance futures/data REST (5m period, last 30 days only) -> same series as the bulk metrics.

startTime is ignored unless endTime is also given, so each request carries an explicit window of at
most LIMIT 5-minute points; windows are walked forward from the last stored point to now.
Data older than 30 days gives HTTP 400, so the start is clamped to RECENT_DAYS back.
"""
from __future__ import annotations

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "binance_metrics_recent"
BASE = "https://fapi.binance.com/futures/data/"
SYMBOL = "BTCUSDT"
PERIOD = "5m"
LIMIT = 500
RECENT_DAYS = 29
# (endpoint, [(response field, metric)])
ENDPOINTS = [
    ("openInterestHist", [("sumOpenInterest", "binance.oi"), ("sumOpenInterestValue", "binance.oi_usd")]),
    ("topLongShortPositionRatio", [("longShortRatio", "binance.top_ls_ratio")]),
    ("globalLongShortAccountRatio", [("longShortRatio", "binance.ls_ratio")]),
    ("takerlongshortRatio", [("buySellRatio", "binance.taker_ls_vol_ratio")]),
]


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    floor = stop - RECENT_DAYS * C.DAY
    total = 0
    for endpoint, fields in ENDPOINTS:
        last = db.last_ts(conn, metric=fields[0][1])
        cur = C.align_up(max(C.effective_start(start_ms, last, C.M5), floor), C.M5)
        while cur <= stop:
            w_end = min(cur + (LIMIT - 1) * C.M5, stop)
            raw = http.get_json(BASE + endpoint, {"symbol": SYMBOL, "period": PERIOD, "startTime": cur,
                                                  "endTime": w_end, "limit": LIMIT})
            rows = []
            for rec in raw or []:
                ts = int(rec["timestamp"])
                if ts > stop:
                    continue
                for field, metric in fields:
                    rows.append({"metric": metric, "ts": ts, "value": float(rec[field]), "available_at": ts})
            total += db.upsert_series(conn, rows)
            cur = w_end + C.M5
    return total
