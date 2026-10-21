import os
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from btcmi import db

H = 3_600_000


def bar(ts, **kw):
    row = {"venue": "v", "symbol": "S", "interval": "1h", "ts": ts, "open": 1.0, "high": 2.0, "low": 0.5,
           "close": 1.5, "volume": 10.0, "quote_volume": 15.0, "taker_buy_volume": 4.0, "trades": 7}
    row.update(kw)
    return row


class DbTests(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        self.addCleanup(self.conn.close)

    def test_schema(self):
        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"bars", "series", "collector_runs"} <= tables)
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(bars)")]
        self.assertEqual(cols, ["venue", "symbol", "interval", "ts", "open", "high", "low", "close",
                                "volume", "quote_volume", "taker_buy_volume", "trades"])
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(series)")]
        self.assertEqual(cols, ["metric", "ts", "value", "available_at"])
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(collector_runs)")]
        self.assertEqual(cols, ["collector", "started", "finished", "rows", "error"])
        idx = {r[1]: [c[2] for c in self.conn.execute(f"PRAGMA index_info({r[1]})")]
               for r in self.conn.execute("PRAGMA index_list(series)")}
        self.assertIn(["metric", "available_at"], idx.values())

    def test_connect_creates_parent_dir_and_wal(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sub" / "dir" / "m.db"
            conn = db.connect(path)
            try:
                self.assertTrue(path.exists())
                self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0].lower(), "wal")
            finally:
                conn.close()

    def test_default_db_under_repo_data(self):
        self.assertEqual(db.DEFAULT_DB.name, "market.db")
        self.assertEqual(db.DEFAULT_DB.parent.name, "data")

    def test_upsert_bars_idempotent(self):
        rows = [bar(0), bar(H), bar(2 * H)]
        self.assertEqual(db.upsert_bars(self.conn, rows), 3)
        self.assertEqual(db.upsert_bars(self.conn, rows), 0)          # identical: nothing new or changed
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM bars").fetchone()[0], 3)
        self.assertEqual(db.upsert_bars(self.conn, [bar(H, close=9.0)]), 1)   # changed value
        self.assertEqual(self.conn.execute("SELECT close FROM bars WHERE ts=?", (H,)).fetchone()[0], 9.0)
        self.assertEqual(db.upsert_bars(self.conn, []), 0)

    def test_upsert_bars_missing_optional_columns_are_null(self):
        db.upsert_bars(self.conn, [{"venue": "v", "symbol": "S", "interval": "1h", "ts": 0, "open": 1,
                                    "high": 1, "low": 1, "close": 1, "volume": 1}])
        row = self.conn.execute("SELECT quote_volume, taker_buy_volume, trades FROM bars").fetchone()
        self.assertEqual(row, (None, None, None))
        # a NULL replaced by NULL is not a change
        self.assertEqual(db.upsert_bars(self.conn, [{"venue": "v", "symbol": "S", "interval": "1h", "ts": 0,
                                                     "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]), 0)

    def test_upsert_series_idempotent(self):
        rows = [{"metric": "m", "ts": t, "value": float(t), "available_at": t + H} for t in (0, H)]
        self.assertEqual(db.upsert_series(self.conn, rows), 2)
        self.assertEqual(db.upsert_series(self.conn, rows), 0)
        rows[0]["value"] = 5.0
        self.assertEqual(db.upsert_series(self.conn, rows), 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM series").fetchone()[0], 2)

    def test_first_last_ts(self):
        self.assertIsNone(db.last_ts(self.conn, venue="v", symbol="S", interval="1h"))
        self.assertIsNone(db.first_ts(self.conn, metric="m"))
        db.upsert_bars(self.conn, [bar(0), bar(5 * H), bar(H, interval="15m"), bar(9 * H, venue="other")])
        self.assertEqual(db.last_ts(self.conn, venue="v", symbol="S", interval="1h"), 5 * H)
        self.assertEqual(db.first_ts(self.conn, venue="v", symbol="S", interval="1h"), 0)
        self.assertEqual(db.last_ts(self.conn, venue="v"), 5 * H)
        self.assertEqual(db.last_ts(self.conn, interval="1h"), 9 * H)
        db.upsert_series(self.conn, [{"metric": "m", "ts": 7, "value": 1.0, "available_at": 7},
                                     {"metric": "m", "ts": 3, "value": 1.0, "available_at": 3},
                                     {"metric": "n", "ts": 99, "value": 1.0, "available_at": 99}])
        self.assertEqual(db.last_ts(self.conn, metric="m"), 7)
        self.assertEqual(db.first_ts(self.conn, metric="m"), 3)

    def test_read_bars_shape_sort_and_bounds(self):
        db.upsert_bars(self.conn, [bar(3 * H), bar(0), bar(H, trades=None), bar(2 * H), bar(0, symbol="X")])
        df = db.read_bars(self.conn, "v", "S", "1h")
        self.assertEqual(list(df.columns), ["ts", "open", "high", "low", "close", "volume", "quote_volume",
                                            "taker_buy_volume", "trades"])
        self.assertEqual(df["ts"].tolist(), [0, H, 2 * H, 3 * H])
        self.assertEqual(str(df["ts"].dtype), "int64")
        self.assertTrue(pd.isna(df.loc[1, "trades"]))
        part = db.read_bars(self.conn, "v", "S", "1h", start_ms=H, end_ms=2 * H)
        self.assertEqual(part["ts"].tolist(), [H, 2 * H])
        empty = db.read_bars(self.conn, "v", "S", "15m")
        self.assertEqual(len(empty), 0)
        self.assertEqual(str(empty["ts"].dtype), "int64")
        self.assertEqual(list(empty.columns), list(df.columns))

    def test_read_series_shape(self):
        db.upsert_series(self.conn, [{"metric": "m", "ts": t, "value": t / 2, "available_at": t + 10}
                                     for t in (30, 10, 20)])
        df = db.read_series(self.conn, "m")
        self.assertEqual(list(df.columns), ["ts", "value", "available_at"])
        self.assertEqual(df["ts"].tolist(), [10, 20, 30])
        self.assertEqual(df["available_at"].tolist(), [20, 30, 40])
        self.assertEqual(str(df["ts"].dtype), "int64")
        self.assertEqual(str(df["available_at"].dtype), "int64")
        self.assertEqual(str(df["value"].dtype), "float64")
        self.assertEqual(db.read_series(self.conn, "m", start_ms=15, end_ms=25)["ts"].tolist(), [20])
        self.assertEqual(len(db.read_series(self.conn, "nope")), 0)

    def test_gaps(self):
        db.upsert_bars(self.conn, [bar(t * H) for t in (0, 1, 2, 5, 6, 10)])
        self.assertEqual(db.gaps(self.conn, venue="v", symbol="S", interval="1h"),
                         [(3 * H, 4 * H), (7 * H, 9 * H)])
        self.assertEqual(db.gaps(self.conn, venue="v", symbol="S", interval="15m"), [])
        db.upsert_bars(self.conn, [bar(t * 900_000, interval="15m") for t in (0, 1, 3)])
        self.assertEqual(db.gaps(self.conn, venue="v", symbol="S", interval="15m"), [(2 * 900_000, 2 * 900_000)])

    def test_log_run(self):
        db.log_run(self.conn, "c1", 1, 2, 3, None)
        db.log_run(self.conn, "c2", 4, 5, 0, "boom")
        rows = self.conn.execute("SELECT * FROM collector_runs ORDER BY started").fetchall()
        self.assertEqual(rows, [("c1", 1, 2, 3, None), ("c2", 4, 5, 0, "boom")])


if __name__ == "__main__":
    unittest.main()
