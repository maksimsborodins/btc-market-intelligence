"""data.binance.vision daily futures metrics (5-min rows, one zip per UTC day).

Series stored (ts = available_at = create_time):
  sum_open_interest -> binance.oi, sum_open_interest_value -> binance.oi_usd,
  sum_toptrader_long_short_ratio -> binance.top_ls_ratio, count_long_short_ratio -> binance.ls_ratio,
  sum_taker_long_short_vol_ratio -> binance.taker_ls_vol_ratio.
(count_toptrader_long_short_ratio is not stored.)

Only days not yet stored are downloaded (resume from last stored binance.oi), today is never
downloaded (not published yet), a 404 for a day is skipped.
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import datetime, timezone

from btcmi import db, http
from btcmi.collectors import _common as C

NAME = "binance_metrics"
URL = ("https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/"
       "BTCUSDT-metrics-{day}.zip")
SYMBOL = "BTCUSDT"
EARLIEST = C.utc_ms(2020, 9, 1)
RESUME_METRIC = "binance.oi"
COLUMNS = {
    "sum_open_interest": "binance.oi",
    "sum_open_interest_value": "binance.oi_usd",
    "sum_toptrader_long_short_ratio": "binance.top_ls_ratio",
    "count_long_short_ratio": "binance.ls_ratio",
    "sum_taker_long_short_vol_ratio": "binance.taker_ls_vol_ratio",
}


def _day_str(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def _parse_time(s: str) -> int:
    dt = datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def parse_zip(data: bytes) -> list[dict]:
    """One daily zip -> series rows, deduplicated on create_time."""
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        text = io.TextIOWrapper(zf.open(name), encoding="utf-8", newline="")
        seen: set[str] = set()
        rows: list[dict] = []
        for rec in csv.DictReader(text):
            ct = (rec.get("create_time") or "").strip()
            if not ct or ct in seen:
                continue
            seen.add(ct)
            ts = _parse_time(ct)
            for col, metric in COLUMNS.items():
                raw = (rec.get(col) or "").strip()
                if raw == "":
                    continue
                try:
                    val = float(raw)
                except ValueError:
                    continue
                rows.append({"metric": metric, "ts": ts, "value": val, "available_at": ts})
    return rows


def run(conn, start_ms: int, end_ms: int | None = None) -> int:
    stop = C.stop_ms(end_ms)
    last = db.last_ts(conn, metric=RESUME_METRIC)
    first_ms = max(int(start_ms), EARLIEST, 0 if last is None else last + C.M5)
    day = C.day_floor(first_ms)
    last_day = min(C.day_floor(C.now_ms()) - C.DAY, C.day_floor(stop))   # yesterday at the latest
    total = 0
    while day <= last_day:
        try:
            data = http.get_bytes(URL.format(day=_day_str(day)))
        except http.HttpError as e:
            if e.status != 404:
                raise
        else:
            total += db.upsert_series(conn, parse_zip(data))
        day += C.DAY
    return total
