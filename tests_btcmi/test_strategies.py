"""Trade simulator and indicator sanity (offline, synthetic bars)."""

import unittest

import numpy as np
import pandas as pd

from btcmi.strategies import (
    FUNDING_8H, HOUR_MS, M15, MAKER, RISK_USD, SLIPPAGE, TAKER, Trade, alligator, first_breach, fractal_known,
    fractals, range_tag, retest_fill, simulate, state_4h, state_4h_at, teeth_exit,
)

START = 1_700_000_000_000 // M15 * M15


def _bars(rows):
    """rows: (open, high, low, close) per 15m bar."""
    idx = START + np.arange(len(rows)) * M15
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx).assign(volume=1.0)


class TestSimulate(unittest.TestCase):
    def test_stop_loses_one_r_plus_costs(self):
        b = _bars([(100, 100.5, 99.8, 100), (100, 100.2, 98.5, 99)])
        t = simulate(b, Trade("x", 1, START, 100.0, 99.0), True, [(102.0, 1.0)], False, None, 48)
        self.assertEqual(t.exit_reason, "stop")
        self.assertAlmostEqual(t.r_gross, -1.0)
        size = RISK_USD / 1.0
        fees = size * 100 * (TAKER + SLIPPAGE) + size * 99 * (TAKER + SLIPPAGE) + size * 100 * FUNDING_8H * 0.5 / 8
        self.assertAlmostEqual(t.fee_r, fees / RISK_USD)
        self.assertAlmostEqual(t.r_net, -1.0 - fees / RISK_USD)

    def test_stop_first_when_both_in_one_bar(self):
        b = _bars([(100, 100, 100, 100), (100, 102.5, 98.5, 100)])
        t = simulate(b, Trade("x", 1, START, 100.0, 99.0), True, [(102.0, 1.0)], False, None, 48)
        self.assertEqual(t.exit_reason, "stop")

    def test_targets_and_breakeven_short(self):
        # short from 100, stop 101; TP1 98 (half) then the stop moves to 100 and is hit
        b = _bars([(100, 100, 100, 100), (100, 100.2, 97.9, 98.5), (98.5, 100.1, 98.4, 100)])
        t = simulate(b, Trade("x", -1, START, 100.0, 101.0), True, [(98.0, 0.5), (96.0, 0.5)], True, None, 48)
        self.assertEqual(t.exit_reason, "stop")
        self.assertAlmostEqual(t.r_gross, 0.5 * 2.0 + 0.5 * 0.0)
        self.assertGreater(t.fee_r, 0)
        size = RISK_USD
        self.assertGreater(t.fee_r, size * 98 * 0.5 * MAKER / RISK_USD)

    def test_trail_moves_only_in_favour(self):
        b = _bars([(100, 100, 100, 100), (100, 103, 100, 103), (103, 103, 101.4, 101.5)])
        trail = [(START + M15, 98.0), (START + 2 * M15, 101.5)]   # first is worse than the stop: ignored
        t = simulate(b, Trade("x", 1, START, 100.0, 99.0), True, [], False, trail, 48)
        self.assertEqual(t.exit_reason, "stop")
        self.assertAlmostEqual(t.r_gross, 1.5)


class TestIndicators(unittest.TestCase):
    def test_fractals(self):
        h = [1, 2, 5, 2, 1, 1, 1]
        l = [1, 1, 1, 1, 1, 0.2, 1]
        up, dn = fractals(pd.DataFrame({"high": h, "low": l}))
        self.assertEqual(list(np.flatnonzero(up)), [2])
        self.assertEqual(list(np.flatnonzero(dn)), [])   # bar 5 has only one bar after it

    def test_fractal_is_taken_once_at_its_first_breach(self):
        # up fractal at bar 2 (high 5) is known after bar 4; bar 6 trades through it, bar 9 again
        h = [1, 2, 5, 2, 1, 3, 6, 2, 1, 7, 2]
        b = pd.DataFrame({"high": h, "low": [0.5] * len(h)})
        self.assertEqual(first_breach(b, 2, 5.0, True), 6)
        self.assertEqual(first_breach(b, 2, 50.0, True), len(h))
        ts = np.arange(len(h)) * HOUR_MS
        self.assertEqual(fractal_known(ts)[2], ts[4] + HOUR_MS)

    def test_alligator_has_no_look_ahead(self):
        rng = np.random.default_rng(0)
        x = 100 + np.cumsum(rng.normal(size=300))
        b = pd.DataFrame({"high": x + 1, "low": x - 1})
        a1 = alligator(b)
        b2 = b.copy()
        b2.iloc[200:] += 50
        a2 = alligator(b2)
        pd.testing.assert_frame_equal(a1.iloc[:200], a2.iloc[:200])
        self.assertTrue(np.isnan(a1["jaw"].iloc[7]))


class TestLimitRetest(unittest.TestCase):
    """Long, trigger level 100, stop 98; the window starts at START + M15 (end of the breach bar)."""

    def test_trade_through_fills_at_level_with_maker_fee(self):
        b = _bars([(99, 101, 99, 100.5),            # breach bar
                   (100.5, 100.6, 100.0, 100.4),    # touches exactly: no fill
                   (100.4, 100.5, 99.9, 100.2),     # trades through: fill at 100
                   (100.2, 100.3, 97.0, 98.0)])     # stop
        fill_ts, _ = retest_fill(b, START + M15, 100.0, 1, 98.0, 4)
        self.assertEqual(fill_ts, START + 2 * M15)
        t = simulate(b, Trade("x", 1, fill_ts, 100.0, 98.0), False, [], False, None, 48)
        self.assertEqual(t.exit_reason, "stop")
        size = RISK_USD / 2.0
        fees = size * 100 * MAKER + size * 98 * (TAKER + SLIPPAGE) + size * 100 * FUNDING_8H * 0.5 / 8
        self.assertAlmostEqual(t.fee_r, fees / RISK_USD)
        self.assertAlmostEqual(t.r_gross, -1.0)

    def test_touch_exactly_at_level_is_no_fill(self):
        b = _bars([(99, 101, 99, 100.5), (100.5, 101, 100.0, 100.6), (100.6, 101, 100.0, 100.8)])
        fill_ts, _ = retest_fill(b, START + M15, 100.0, 1, 98.0, 4)
        self.assertIsNone(fill_ts)

    def test_stop_before_retest_is_no_trade(self):
        b = _bars([(99, 101, 99, 100.5), (100.5, 100.6, 97.5, 98.2), (98.2, 100.5, 98.0, 100.0)])
        fill_ts, done = retest_fill(b, START + M15, 100.0, 1, 98.0, 4)   # bar 1 trades through the level and the stop
        self.assertIsNone(fill_ts)
        self.assertEqual(done, START + 2 * M15)                            # the order is cancelled when the stop is touched

    def test_window_expires(self):
        rows = [(99, 101, 99, 100.5)] + [(101, 102, 100.5, 101)] * 8 + [(101, 101, 99.0, 99.5)]
        b = _bars(rows)                                                    # trade-through only in bar 9, after 2 h
        fill_ts, done = retest_fill(b, START + M15, 100.0, 1, 98.0, 2)
        self.assertIsNone(fill_ts)
        self.assertEqual(done, START + M15 + 2 * HOUR_MS)
        self.assertEqual(retest_fill(b, START + M15, 100.0, 1, 98.0, 4)[0], START + 9 * M15)

    def test_short_mirror(self):
        b = _bars([(101, 101, 99, 99.5), (99.5, 100.0, 99.4, 99.6), (99.6, 100.1, 99.5, 99.9)])
        self.assertEqual(retest_fill(b, START + M15, 100.0, -1, 102.0, 4)[0], START + 2 * M15)


class TestFilter4h(unittest.TestCase):
    def _b15(self, n_hours=24 * 40, seed=2):
        rng = np.random.default_rng(seed)
        n = n_hours * 4
        x = 100 + np.cumsum(rng.normal(0.02, 0.4, n))
        idx = START // (4 * HOUR_MS) * (4 * HOUR_MS) + np.arange(n) * M15
        return pd.DataFrame({"open": x, "high": x + 0.3, "low": x - 0.3, "close": x, "volume": 1.0}, index=idx)

    def test_only_completed_4h_bars(self):
        b = self._b15()
        known, state = state_4h(b)
        now = int(b.index[400]) + 2 * M15 + M15 // 2 * 0         # inside a 4h bar
        now = now // (4 * HOUR_MS) * (4 * HOUR_MS) + 2 * HOUR_MS
        s1 = state_4h_at(known, state, now)
        b2 = b.copy()
        cur = (b2.index >= now // (4 * HOUR_MS) * (4 * HOUR_MS))      # the unfinished 4h bar and everything after
        b2.loc[cur, ["high", "low", "close"]] += 500.0
        known2, state2 = state_4h(b2)
        self.assertEqual(s1, state_4h_at(known2, state2, now))
        self.assertIn(s1, (-1, 0, 1))

    def test_mouth_direction(self):
        n = 4 * 24 * 60
        idx = START // (4 * HOUR_MS) * (4 * HOUR_MS) + np.arange(n) * M15
        up = pd.DataFrame({"open": 100 + np.arange(n) * 0.1}, index=idx)
        for k in ("high", "low", "close"):
            up[k] = up["open"]
        up["volume"] = 1.0
        known, state = state_4h(up)
        self.assertEqual(state_4h_at(known, state, int(idx[-1])), 1)   # steady rise: lips > teeth > jaw
        dn = up.copy()
        for k in ("open", "high", "low", "close"):
            dn[k] = 1000 - up[k]
        known, state = state_4h(dn)
        self.assertEqual(state_4h_at(known, state, int(idx[-1])), -1)


class TestTeethExit(unittest.TestCase):
    def test_first_close_beyond_teeth(self):
        idx = START + np.arange(6) * HOUR_MS
        b1 = pd.DataFrame({"close": [105, 104, 102.0, 99.0, 101.0, 98.0]}, index=idx)
        teeth = np.array([100.0, 100.0, 100.0, 100.0, 100.0, 100.0])
        # long entered during hour 1; first close below teeth is hour 3 (close time = idx[3] + 1h)
        self.assertEqual(teeth_exit(b1, teeth, 1, int(idx[1]) + M15), (int(idx[3]) + HOUR_MS, 99.0))
        self.assertEqual(teeth_exit(b1, teeth, 1, int(idx[3]) + M15), (int(idx[3]) + HOUR_MS, 99.0))   # same hour: its close counts
        self.assertEqual(teeth_exit(b1, teeth, 1, int(idx[3]) + HOUR_MS)[1], 98.0)                    # after that hour closed
        self.assertEqual(teeth_exit(b1, teeth, -1, int(idx[3]) + M15), (int(idx[4]) + HOUR_MS, 101.0))  # short: close above
        self.assertIsNone(teeth_exit(b1, teeth, 1, int(idx[5]) + HOUR_MS))

    def test_simulate_exits_at_that_close(self):
        b = _bars([(100, 100.5, 99.5, 100.2)] * 4 + [(100.2, 100.4, 99.0, 99.2)] * 4)
        exit_at = (START + 4 * M15, 99.4)
        t = simulate(b, Trade("x", 1, START, 100.0, 97.0), True, [], False, None, 48, exit_at=exit_at)
        self.assertEqual(t.exit_reason, "teeth")
        self.assertEqual(t.exit_ts, START + 4 * M15)
        size = RISK_USD / 3.0
        self.assertAlmostEqual(t.r_gross, size * (99.4 - 100.0) / RISK_USD)
        fees = size * 100 * (TAKER + SLIPPAGE) + size * 99.4 * (TAKER + SLIPPAGE) + size * 100 * FUNDING_8H * 1.0 / 8
        self.assertAlmostEqual(t.fee_r, fees / RISK_USD)

    def test_stop_before_exit_time_still_applies(self):
        b = _bars([(100, 100.5, 99.5, 100.2), (100.2, 100.3, 96.0, 97.0)] + [(97, 97, 97, 97)] * 6)
        t = simulate(b, Trade("x", 1, START, 100.0, 97.0), True, [], False, None, 48, exit_at=(START + 4 * M15, 99.0))
        self.assertEqual(t.exit_reason, "stop")


class TestRangeTag(unittest.TestCase):
    def test_tag_uses_forecast_at_the_decision_close(self):
        fc = pd.DataFrame({"color": ["green", "red"], "pred_24h_pct": [4.0, 9.0]}, index=[1_000 * HOUR_MS, 1_001 * HOUR_MS])
        self.assertEqual(range_tag(fc, 1_000 * HOUR_MS), {"range_color": "green", "range_pred_24h_pct": 4.0})
        self.assertEqual(range_tag(fc, 999 * HOUR_MS)["range_color"], "none")
        self.assertEqual(range_tag(None, 1_000 * HOUR_MS)["range_color"], "none")


if __name__ == "__main__":
    unittest.main()
