"""Dashboard data: upcoming macro / expiry events with how much BTC usually moved around them, the Deribit DVOL
and the range forecast, as one JSON-able dict. Each block fails on its own (null + an error line).

Event window = 4 hourly bars from the hour of the event. Its range is compared with the same clock hours on the
previous 20 calm weekdays (Mon-Thu, no macro event in that window).
"""

from __future__ import annotations

import csv
import math
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from btcmi import db, http, range_model
from btcmi.strategies import HOUR_MS, load_15m

DAY_MS = 24 * HOUR_MS
WINDOW_BARS = 4
BASELINE_DAYS = 20
SINCE_MS = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)
MACRO = ("FOMC", "CPI", "NFP", "PCE")
NAMES_RU = {
    "FOMC": "Решение ФРС (FOMC)", "CPI": "Инфляция США (CPI)", "NFP": "Занятость США (NFP)",
    "PCE": "Инфляция PCE", "EXPIRY_WEEKLY": "Недельная экспирация Deribit",
    "EXPIRY_MONTHLY": "Месячная экспирация Deribit", "EXPIRY_QUARTERLY": "Квартальная экспирация Deribit",
}
ET = ZoneInfo("America/New_York")
DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"


def _hour(ts: int) -> int:
    return ts // HOUR_MS * HOUR_MS


# ---------------------------------------------------------------- events
def load_macro_events(path) -> list[tuple[str, int]]:
    """(type, utc ms) from the CSV (type,date_et,time_et,source); times are US Eastern."""
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            dt = datetime.strptime(f"{r['date_et'].strip()} {r['time_et'].strip()}", "%Y-%m-%d %H:%M").replace(tzinfo=ET)
            out.append((r["type"].strip().upper(), int(dt.timestamp() * 1000)))
    return sorted(out, key=lambda e: e[1])


def expiry_type(d: date) -> str:
    """Deribit expiry on Friday d: quarterly = last Friday of Mar/Jun/Sep/Dec, monthly = last Friday, else weekly."""
    if (d + timedelta(days=7)).month == d.month:
        return "EXPIRY_WEEKLY"
    return "EXPIRY_QUARTERLY" if d.month in (3, 6, 9, 12) else "EXPIRY_MONTHLY"


def expiry_events(start_ms: int, end_ms: int) -> list[tuple[str, int]]:
    """Every Friday 08:00 UTC in [start_ms, end_ms)."""
    d = datetime.fromtimestamp(start_ms / 1000, timezone.utc).date()
    d += timedelta(days=(4 - d.weekday()) % 7)
    out = []
    while True:
        t = int(datetime(d.year, d.month, d.day, 8, tzinfo=timezone.utc).timestamp() * 1000)
        if t >= end_ms:
            return out
        if t >= start_ms:
            out.append((expiry_type(d), t))
        d += timedelta(days=7)


# ---------------------------------------------------------------- statistics
def window_range(b: pd.DataFrame, start_ms: int) -> float:
    """max(high) / min(low) - 1 in percent over the 4 hourly bars from start_ms; NaN if any bar is missing."""
    idx = start_ms + np.arange(WINDOW_BARS, dtype="int64") * HOUR_MS
    w = b.reindex(idx)
    if w["high"].isna().any() or w["low"].isna().any():
        return float("nan")
    return float((w["high"].max() / w["low"].min() - 1) * 100)


def baseline_starts(start_ms: int, macro_ms: list[int], days: int = BASELINE_DAYS) -> list[int]:
    """Same clock hour on the previous `days` Mon-Thu days whose 4h window does not touch a macro event window."""
    macro = [_hour(t) for t in macro_ms]
    out, s, back = [], start_ms, 0
    while len(out) < days and back < 400:
        s -= DAY_MS
        back += 1
        if datetime.fromtimestamp(s / 1000, timezone.utc).weekday() > 3:
            continue
        if any(abs(s - m) < WINDOW_BARS * HOUR_MS for m in macro):
            continue
        out.append(s)
    return out


def event_stats(b: pd.DataFrame, events: list[tuple[str, int]], since_ms: int = SINCE_MS) -> dict[str, dict]:
    """Per type: n, median range, median baseline, median ratio and share of events above their baseline."""
    macro = [t for ty, t in events if ty in MACRO]
    rows: dict[str, list[tuple[float, float]]] = {}
    for ty, t in events:
        if t < since_ms:
            continue
        s = _hour(t)
        rng = window_range(b, s)
        if not math.isfinite(rng):
            continue
        vals = [window_range(b, x) for x in baseline_starts(s, macro)]
        vals = [v for v in vals if math.isfinite(v)]
        if not vals:
            continue
        base = float(np.median(vals))
        if base > 0:
            rows.setdefault(ty, []).append((rng, base))
    out = {}
    for ty, r in rows.items():
        rng, base = np.array(r).T
        out[ty] = {"n": len(r), "median_range_pct": float(np.median(rng)), "median_base_pct": float(np.median(base)),
                   "ratio": float(np.median(rng / base)), "share_above": float(np.mean(rng > base))}
    return out


def upcoming(events: list[tuple[str, int]], now_ms: int, days: int, stats: dict | None) -> list[dict]:
    """Events with now <= time < now + days, sorted, with the statistics of their type attached."""
    end = now_ms + days * DAY_MS
    sel = sorted((e for e in events if now_ms <= e[1] < end), key=lambda e: e[1])
    return [{"time": t, "type": ty, "name_ru": NAMES_RU[ty], "stats": (stats or {}).get(ty)} for ty, t in sel]


# ---------------------------------------------------------------- DVOL
def _dvol_rows(fetch, now_ms: int, start_ms: int, resolution: str) -> list[list[float]]:
    res = fetch(DVOL_URL, {"currency": "BTC", "start_timestamp": start_ms, "end_timestamp": now_ms,
                           "resolution": resolution})
    rows = res["result"]["data"]
    if not rows:
        raise ValueError("empty DVOL data")
    return rows


def dvol_stats(fetch, now_ms: int) -> dict:
    """Last hourly DVOL close, change vs 24 h earlier, percentile among 365 daily closes, implied daily move."""
    hourly = _dvol_rows(fetch, now_ms, now_ms - 3 * DAY_MS, "3600")
    daily = _dvol_rows(fetch, now_ms, now_ms - 370 * DAY_MS, "1D")
    closes = {int(r[0]): float(r[4]) for r in hourly}
    last_ts = max(closes)
    value = closes[last_ts]
    prev = closes.get(last_ts - DAY_MS)
    d = np.array([float(r[4]) for r in daily][-365:])
    return {"value": value, "change_24h": None if prev is None else value - prev,
            "pct_rank_365d": float((d < value).mean() * 100), "daily_move_pct": value / math.sqrt(365)}


# ---------------------------------------------------------------- dashboard
def _block(errors: list[str], name: str, fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - one broken block must not take the rest down
        errors.append(f"{name}: {type(e).__name__}: {e}"[:200])
        return None


def build_dashboard(conn, now_ms: int, events_path, days: int = 7, fetch=http.get_json) -> dict:
    """Everything the dashboard shows, as a dict (see module docstring); failed blocks are null + an errors entry."""
    errors: list[str] = []
    last = _block(errors, "price", lambda: load_15m(conn).dropna(subset=["close"]).iloc[-1:])
    price = price_time = None
    if last is not None and len(last):
        price, price_time = float(last["close"].iloc[0]), int(last.index[0])
    rng = _block(errors, "range", lambda: range_model.forecast_now(conn))

    macro = _block(errors, "events", lambda: load_macro_events(events_path))
    events = (macro or []) + expiry_events(SINCE_MS, now_ms + days * DAY_MS)
    stats = _block(errors, "stats", lambda: event_stats(range_model.hourly(conn), [e for e in events if e[1] < now_ms]))
    dv = _block(errors, "dvol", lambda: dvol_stats(fetch, now_ms))
    return {"generated_at": now_ms, "price": price, "price_time": price_time, "range": rng, "dvol": dv,
            "events": upcoming(events, now_ms, days, stats), "errors": errors}


def main(argv=None) -> int:
    import argparse
    import json
    import sys
    from pathlib import Path

    from btcmi.collect import run_collectors

    ap = argparse.ArgumentParser(prog="dashboard.py", description="BTC dashboard data as JSON on stdout")
    ap.add_argument("--db", default=None, help="SQLite path (default data/market.db)")
    ap.add_argument("--events", default=str(Path(__file__).resolve().parent.parent / "events" / "macro_events.csv"))
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--no-refresh", action="store_true", help="skip the incremental refresh of the perp bars")
    args = ap.parse_args(argv)

    conn = db.connect(args.db)
    try:
        now = db.now_ms()
        if not args.no_refresh:
            try:
                run_collectors(conn, ["binance_perp_bars"], now - 3 * DAY_MS, out=lambda s: print(s, file=sys.stderr))
            except Exception as e:  # noqa: BLE001 - stale bars still make a dashboard
                print(f"refresh failed: {e}", file=sys.stderr)
        data = build_dashboard(conn, now, args.events, args.days)
    finally:
        conn.close()
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False))
    return 0
