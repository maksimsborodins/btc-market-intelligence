"""SQLite storage for the research core (schema: docs/REBUILD.md).

All timestamps are UTC epoch milliseconds at bar start.
"""
from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = ROOT / "data" / "market.db"

INTERVAL_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
  venue TEXT, symbol TEXT, interval TEXT,
  ts INTEGER, open REAL, high REAL, low REAL, close REAL,
  volume REAL, quote_volume REAL, taker_buy_volume REAL, trades INTEGER,
  PRIMARY KEY (venue, symbol, interval, ts)
);
CREATE TABLE IF NOT EXISTS series (
  metric TEXT,
  ts INTEGER, value REAL,
  available_at INTEGER,
  PRIMARY KEY (metric, ts)
);
CREATE TABLE IF NOT EXISTS collector_runs (collector TEXT, started INTEGER, finished INTEGER, rows INTEGER, error TEXT);
CREATE INDEX IF NOT EXISTS idx_series_metric_available ON series(metric, available_at);
"""

BAR_COLS = ["venue", "symbol", "interval", "ts", "open", "high", "low", "close",
            "volume", "quote_volume", "taker_buy_volume", "trades"]
_BAR_VALUE_COLS = BAR_COLS[4:]
READ_BAR_COLS = ["ts", "open", "high", "low", "close", "volume", "quote_volume", "taker_buy_volume", "trades"]
SERIES_COLS = ["metric", "ts", "value", "available_at"]

_BARS_SQL = (
    "INSERT INTO bars (" + ",".join(BAR_COLS) + ") VALUES (" + ",".join(":" + c for c in BAR_COLS) + ") "
    "ON CONFLICT(venue, symbol, interval, ts) DO UPDATE SET "
    + ", ".join(f"{c}=excluded.{c}" for c in _BAR_VALUE_COLS)
    + " WHERE " + " OR ".join(f"bars.{c} IS NOT excluded.{c}" for c in _BAR_VALUE_COLS)
)
_SERIES_SQL = (
    "INSERT INTO series (metric, ts, value, available_at) VALUES (:metric, :ts, :value, :available_at) "
    "ON CONFLICT(metric, ts) DO UPDATE SET value=excluded.value, available_at=excluded.available_at "
    "WHERE series.value IS NOT excluded.value OR series.available_at IS NOT excluded.available_at"
)


def connect(path=None) -> sqlite3.Connection:
    """Open (and create if needed) the database; WAL mode; schema ensured."""
    target = str(path) if path else str(DEFAULT_DB)
    if target != ":memory:":
        Path(target).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=60)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def _norm(row: dict, cols: list[str]) -> dict:
    return {c: row.get(c) for c in cols}


def upsert_bars(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """INSERT OR UPDATE bars. Returns the number of new or changed rows."""
    if not rows:
        return 0
    before = conn.total_changes
    conn.executemany(_BARS_SQL, [_norm(r, BAR_COLS) for r in rows])
    conn.commit()
    return conn.total_changes - before


def upsert_series(conn: sqlite3.Connection, rows: list[dict]) -> int:
    """INSERT OR UPDATE series points. Returns the number of new or changed rows."""
    if not rows:
        return 0
    before = conn.total_changes
    conn.executemany(_SERIES_SQL, [_norm(r, SERIES_COLS) for r in rows])
    conn.commit()
    return conn.total_changes - before


def _edge(conn, agg: str, venue, symbol, interval, metric):
    if metric is not None:
        sql, where, params = "SELECT {}(ts) FROM series", ["metric = ?"], [metric]
    else:
        sql, where, params = "SELECT {}(ts) FROM bars", [], []
        for col, val in (("venue", venue), ("symbol", symbol), ("interval", interval)):
            if val is not None:
                where.append(f"{col} = ?")
                params.append(val)
    sql = sql.format(agg) + (" WHERE " + " AND ".join(where) if where else "")
    val = conn.execute(sql, params).fetchone()[0]
    return None if val is None else int(val)


def last_ts(conn, *, venue=None, symbol=None, interval=None, metric=None) -> int | None:
    """Latest stored ts. With `metric` reads series, otherwise bars (filtered by the given keys)."""
    return _edge(conn, "MAX", venue, symbol, interval, metric)


def first_ts(conn, *, venue=None, symbol=None, interval=None, metric=None) -> int | None:
    return _edge(conn, "MIN", venue, symbol, interval, metric)


def read_bars(conn, venue: str, symbol: str, interval: str,
              start_ms: int | None = None, end_ms: int | None = None) -> pd.DataFrame:
    """Bars sorted by ts (inclusive bounds). ts is int64 ms, other columns float64."""
    sql = "SELECT " + ",".join(READ_BAR_COLS) + " FROM bars WHERE venue=? AND symbol=? AND interval=?"
    params: list = [venue, symbol, interval]
    if start_ms is not None:
        sql += " AND ts >= ?"
        params.append(int(start_ms))
    if end_ms is not None:
        sql += " AND ts <= ?"
        params.append(int(end_ms))
    sql += " ORDER BY ts"
    df = pd.read_sql_query(sql, conn, params=params)
    df = df.astype({c: "float64" for c in READ_BAR_COLS[1:]})
    df["ts"] = df["ts"].astype("int64")
    return df[READ_BAR_COLS]


def read_series(conn, metric: str, start_ms: int | None = None, end_ms: int | None = None) -> pd.DataFrame:
    """Series points sorted by ts (inclusive bounds on ts). Columns ts, value, available_at."""
    sql = "SELECT ts, value, available_at FROM series WHERE metric=?"
    params: list = [metric]
    if start_ms is not None:
        sql += " AND ts >= ?"
        params.append(int(start_ms))
    if end_ms is not None:
        sql += " AND ts <= ?"
        params.append(int(end_ms))
    sql += " ORDER BY ts"
    df = pd.read_sql_query(sql, conn, params=params)
    df = df.astype({"ts": "int64", "value": "float64", "available_at": "int64"})
    return df[["ts", "value", "available_at"]]


def gaps(conn, *, venue: str, symbol: str, interval: str) -> list[tuple[int, int]]:
    """Missing bar ranges between the first and last stored bar.

    Each tuple is (first_missing_bar_ts, last_missing_bar_ts), both inclusive bar start times.
    """
    step = INTERVAL_MS[interval]
    out: list[tuple[int, int]] = []
    cur = conn.execute(
        "SELECT ts FROM bars WHERE venue=? AND symbol=? AND interval=? ORDER BY ts", (venue, symbol, interval))
    prev = None
    for (ts,) in cur:
        if prev is not None and ts - prev > step:
            out.append((prev + step, ts - step))
        prev = ts
    return out


def log_run(conn, collector: str, started: int, finished: int, rows: int, error: str | None) -> None:
    conn.execute(
        "INSERT INTO collector_runs (collector, started, finished, rows, error) VALUES (?,?,?,?,?)",
        (collector, int(started), int(finished), int(rows), error))
    conn.commit()


def now_ms() -> int:
    return int(time.time() * 1000)
