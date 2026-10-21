import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from btcmi import collect, db


def fake_collector(name, rows=0, exc=None):
    def run(conn, start_ms, end_ms=None):
        if exc:
            raise exc
        db.upsert_series(conn, [{"metric": name, "ts": start_ms, "value": 1.0, "available_at": start_ms}])
        return rows
    return SimpleNamespace(NAME=name, run=run)


class RunnerTests(unittest.TestCase):
    def test_registry_has_all_phase1_collectors_in_order(self):
        self.assertEqual(list(collect.COLLECTORS), [
            "binance_spot_bars", "binance_perp_bars", "binance_premium", "binance_funding", "binance_metrics",
            "binance_metrics_recent", "bybit_bars", "bybit_oi", "bybit_funding", "bybit_ls_ratio", "coinbase_bars"])
        for name, mod in collect.COLLECTORS.items():
            self.assertEqual(mod.NAME, name)
            self.assertTrue(callable(mod.run))

    def test_failing_collector_is_logged_and_does_not_stop_the_rest(self):
        conn = db.connect(":memory:")
        self.addCleanup(conn.close)
        fakes = {"a": fake_collector("a", rows=3), "b": fake_collector("b", exc=RuntimeError("boom")),
                 "c": fake_collector("c", rows=5)}
        lines = []
        with mock.patch.dict(collect.COLLECTORS, fakes, clear=True):
            res = collect.run_collectors(conn, ["a", "b", "c"], 1000, out=lines.append)
        self.assertEqual(res["a"][0], 3)
        self.assertEqual(res["b"][0], 0)
        self.assertIn("RuntimeError: boom", res["b"][2])
        self.assertEqual(res["c"][0], 5)
        runs = conn.execute("SELECT collector, rows, error FROM collector_runs ORDER BY rowid").fetchall()
        self.assertEqual(runs, [("a", 3, None), ("b", 0, "RuntimeError: boom"), ("c", 5, None)])
        self.assertEqual(len(lines), 3)
        self.assertIn("rows=3", lines[0])
        self.assertIn("ERROR: RuntimeError: boom", lines[1])

    def test_main_list(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(collect.main(["--list"]), 0)
        self.assertEqual(buf.getvalue().split(), list(collect.COLLECTORS))

    def test_main_only_since_and_db(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "x" / "t.db"
            seen = {}

            def run(conn, start_ms, end_ms=None):
                seen["start"] = start_ms
                return 2

            fakes = {"a": SimpleNamespace(NAME="a", run=run), "b": fake_collector("b", rows=9)}
            buf = io.StringIO()
            with mock.patch.dict(collect.COLLECTORS, fakes, clear=True), redirect_stdout(buf):
                code = collect.main(["--db", str(path), "--since", "2021-01-01", "--only", "a"])
            self.assertEqual(code, 0)
            self.assertEqual(seen["start"], 1609459200000)
            out = buf.getvalue()
            self.assertIn("a ", out)
            self.assertNotIn("b ", out)
            self.assertTrue(path.exists())
            conn = db.connect(path)
            try:
                self.assertEqual(conn.execute("SELECT collector, rows FROM collector_runs").fetchall(), [("a", 2)])
            finally:
                conn.close()

    def test_main_exit_code_1_when_a_collector_fails(self):
        with tempfile.TemporaryDirectory() as td:
            fakes = {"a": fake_collector("a", exc=ValueError("x"))}
            with mock.patch.dict(collect.COLLECTORS, fakes, clear=True), redirect_stdout(io.StringIO()):
                self.assertEqual(collect.main(["--db", str(Path(td) / "t.db")]), 1)

    def test_unknown_collector_and_bad_date_are_usage_errors(self):
        for argv in (["--only", "nope"], ["--since", "2021/01/01"]):
            with redirect_stdout(io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    collect.main(argv)
            self.assertEqual(cm.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
