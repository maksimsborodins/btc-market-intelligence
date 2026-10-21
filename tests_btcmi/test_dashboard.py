"""Dashboard data: events (ET->UTC, expiries), event statistics vs a calm baseline, DVOL, block isolation (offline)."""

import csv
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest import mock

import numpy as np
import pandas as pd

from btcmi import dashboard

HOUR = 3_600_000
DAY = 24 * HOUR


def ms(y, m, d, hh=0, mm=0):
    return int(datetime(y, m, d, hh, mm, tzinfo=timezone.utc).timestamp() * 1000)


def bars(start, n, high=101.0, low=100.0):
    idx = start + np.arange(n, dtype="int64") * HOUR
    return pd.DataFrame({"open": low, "high": high, "low": low, "close": low, "volume": 1.0}, index=idx)


def write_events(rows):
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="", encoding="utf-8")
    w = csv.writer(f)
    w.writerow(["type", "date_et", "time_et", "source"])
    w.writerows(rows)
    f.close()
    return f.name


class TestExpiry(unittest.TestCase):
    def test_types(self):
        t = dashboard.expiry_type
        self.assertEqual(t(date(2026, 10, 23)), "EXPIRY_WEEKLY")
        self.assertEqual(t(date(2026, 10, 30)), "EXPIRY_MONTHLY")
        self.assertEqual(t(date(2026, 12, 25)), "EXPIRY_QUARTERLY")
        self.assertEqual(t(date(2026, 7, 31)), "EXPIRY_MONTHLY")      # last day of month is a Friday

    def test_generated_range(self):
        ev = dashboard.expiry_events(ms(2026, 10, 20), ms(2026, 11, 2))
        self.assertEqual(ev, [("EXPIRY_WEEKLY", ms(2026, 10, 23, 8)), ("EXPIRY_MONTHLY", ms(2026, 10, 30, 8))])


class TestMacroEvents(unittest.TestCase):
    def test_et_to_utc(self):
        p = write_events([("CPI", "2026-10-14", "08:30", "x"), ("CPI", "2026-12-10", "08:30", "x"),
                          ("FOMC", "2026-10-28", "14:00", "x")])
        ev = dict(((t, u) for t, u in dashboard.load_macro_events(p)))
        self.assertEqual(ev["FOMC"], ms(2026, 10, 28, 18))
        got = sorted(u for t, u in dashboard.load_macro_events(p) if t == "CPI")
        self.assertEqual(got, [ms(2026, 10, 14, 12, 30), ms(2026, 12, 10, 13, 30)])


class TestWindows(unittest.TestCase):
    def test_range_value(self):
        b = bars(ms(2026, 3, 2), 10)
        b.loc[ms(2026, 3, 2, 2), "high"] = 110.0
        b.loc[ms(2026, 3, 2, 3), "low"] = 95.0
        self.assertAlmostEqual(dashboard.window_range(b, ms(2026, 3, 2)), (110 / 95 - 1) * 100)

    def test_missing_bar_nan(self):
        b = bars(ms(2026, 3, 2), 10).drop(index=ms(2026, 3, 2, 2))
        self.assertTrue(np.isnan(dashboard.window_range(b, ms(2026, 3, 2))))
        self.assertTrue(np.isnan(dashboard.window_range(b, ms(2026, 3, 2, 8))))   # beyond the data

    def test_baseline_days(self):
        s = ms(2026, 6, 10, 12)                      # Wednesday
        macro = [ms(2026, 6, 4, 12, 30)]             # Thursday window 12:00-16:00 -> that day is skipped
        days = dashboard.baseline_starts(s, macro)
        self.assertEqual(len(days), 20)
        wd = [datetime.fromtimestamp(d / 1000, timezone.utc).weekday() for d in days]
        self.assertTrue(all(w <= 3 for w in wd))     # Mon-Thu only: no Friday, no weekend
        self.assertNotIn(ms(2026, 6, 4, 12), days)
        self.assertTrue(all(d < s and (s - d) % DAY == 0 for d in days))
        self.assertEqual(days[0], ms(2026, 6, 9, 12))

    def test_baseline_overlap_hours(self):
        s = ms(2026, 6, 10, 12)
        macro = [ms(2026, 6, 9, 9)]                  # window 09:00-13:00 overlaps 12:00-16:00 on Tuesday
        self.assertNotIn(ms(2026, 6, 9, 12), dashboard.baseline_starts(s, macro))


class TestStats(unittest.TestCase):
    def test_double_range_gives_ratio_two(self):
        b = bars(ms(2026, 1, 1), 24 * 120)
        events = [("CPI", ms(2026, 4, 15, 12, 30)), ("CPI", ms(2026, 4, 22, 12, 30))]
        for _, t in events:
            s = t // HOUR * HOUR
            for k in range(4):
                b.loc[s + k * HOUR, "high"] = 102.0
        st = dashboard.event_stats(b, events, since_ms=ms(2026, 1, 1))["CPI"]
        self.assertEqual(st["n"], 2)
        self.assertAlmostEqual(st["median_range_pct"], 2.0)
        self.assertAlmostEqual(st["median_base_pct"], 1.0)
        self.assertAlmostEqual(st["ratio"], 2.0)
        self.assertAlmostEqual(st["share_above"], 1.0)

    def test_incomplete_window_excluded_and_since(self):
        b = bars(ms(2026, 1, 1), 24 * 60)
        events = [("NFP", ms(2026, 2, 27, 13, 30)), ("NFP", ms(2026, 6, 5, 12, 30)), ("NFP", ms(2021, 6, 4, 12, 30))]
        st = dashboard.event_stats(b, events, since_ms=ms(2022, 1, 1))
        self.assertTrue("NFP" not in st or st["NFP"]["n"] == 1)


class TestUpcoming(unittest.TestCase):
    def test_filter_sorted_stats(self):
        now = ms(2026, 10, 21, 10)
        events = [("FOMC", ms(2026, 10, 28, 18)), ("CPI", ms(2026, 10, 14, 12, 30)),
                  ("EXPIRY_WEEKLY", ms(2026, 10, 23, 8)), ("NFP", ms(2026, 10, 28, 10))]
        stats = {"FOMC": {"n": 3, "median_range_pct": 1.0, "median_base_pct": 0.5, "ratio": 2.0, "share_above": 1.0}}
        out = dashboard.upcoming(events, now, 7, stats)
        self.assertEqual([e["type"] for e in out], ["EXPIRY_WEEKLY"])        # FOMC is exactly 7d+8h away
        out = dashboard.upcoming(events, now, 8, stats)
        self.assertEqual([e["type"] for e in out], ["EXPIRY_WEEKLY", "NFP", "FOMC"])
        self.assertEqual(out[2]["stats"]["ratio"], 2.0)
        self.assertIsNone(out[1]["stats"])
        self.assertEqual(out[2]["name_ru"], "Решение ФРС (FOMC)")
        self.assertEqual(out[0]["name_ru"], "Недельная экспирация Deribit")


def canned_fetch(url, params):
    assert "get_volatility_index_data" in url and params["currency"] == "BTC"
    if params["resolution"] == "3600":
        rows = [[i * HOUR, 0, 0, 0, 50.0 + i] for i in range(48)]
    else:
        rows = [[i * DAY, 0, 0, 0, 10.0 * (i + 1)] for i in range(10)]
    return {"result": {"data": rows}}


class TestDvol(unittest.TestCase):
    def test_values(self):
        d = dashboard.dvol_stats(canned_fetch, 47 * HOUR)
        self.assertAlmostEqual(d["value"], 97.0)
        self.assertAlmostEqual(d["change_24h"], 24.0)
        self.assertAlmostEqual(d["pct_rank_365d"], 90.0)                    # closes 10..100, value 97 -> 9 below
        self.assertAlmostEqual(d["daily_move_pct"], 97.0 / np.sqrt(365))


class TestBuild(unittest.TestCase):
    def _patch(self):
        fc = {"pred_6h_pct": 1.0, "lo_6h_pct": 0.5, "hi_6h_pct": 2.0, "pred_24h_pct": 2.0, "lo_24h_pct": 1.0,
              "hi_24h_pct": 3.0, "color": "green", "time": 1}
        b = bars(ms(2026, 9, 1), 24 * 60)
        return [mock.patch.object(dashboard.range_model, "forecast_now", return_value=fc),
                mock.patch.object(dashboard.range_model, "hourly", return_value=b),
                mock.patch.object(dashboard, "load_15m", return_value=b.assign(close=123.0))]

    def test_failing_fetch_isolated(self):
        def boom(url, params):
            raise RuntimeError("no network")
        p = write_events([("CPI", "2026-10-22", "08:30", "x")])
        with self._patch()[0], self._patch()[1], self._patch()[2]:
            out = dashboard.build_dashboard(None, ms(2026, 10, 21, 10), p, fetch=boom)
        self.assertEqual(list(out), ["generated_at", "price", "price_time", "range", "dvol", "events", "errors"])
        self.assertIsNone(out["dvol"])
        self.assertTrue(any("dvol" in e.lower() for e in out["errors"]))
        self.assertEqual(out["range"]["color"], "green")
        self.assertEqual(out["price"], 123.0)
        self.assertEqual([e["type"] for e in out["events"]], ["CPI", "EXPIRY_WEEKLY"])

    def test_missing_events_file(self):
        with self._patch()[0], self._patch()[1], self._patch()[2]:
            out = dashboard.build_dashboard(None, ms(2026, 10, 21, 10), "nope.csv", fetch=canned_fetch)
        self.assertTrue(any("events" in e.lower() for e in out["errors"]))
        self.assertEqual([e["type"] for e in out["events"]], ["EXPIRY_WEEKLY"])
        self.assertIsNotNone(out["dvol"])


if __name__ == "__main__":
    unittest.main()
