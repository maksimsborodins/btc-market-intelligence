"""Range forecast: targets, features, walk-forward without look-ahead, traffic light (offline, synthetic bars)."""

import unittest

import numpy as np
import pandas as pd

from btcmi.range_model import features, future_range, traffic_light, walk_forward

HOUR = 3_600_000
T0 = 1_577_836_800_000          # 2020-01-01 UTC


def _toy(highs, lows):
    idx = T0 + np.arange(len(highs)) * HOUR
    return pd.DataFrame({"open": highs, "high": highs, "low": lows, "close": lows, "volume": 1.0}, index=idx)


def _walk(n=14_500, seed=1):
    """Hourly random walk with a daily rhythm in the range, gapless."""
    rng = np.random.default_rng(seed)
    idx = T0 + np.arange(n) * HOUR
    hod = np.arange(n) % 24
    vol = 0.004 * (1 + 0.5 * np.sin(hod / 24 * 2 * np.pi)) * np.exp(np.cumsum(rng.normal(0, 0.02, n)) * 0.2)
    close = 20_000 * np.exp(np.cumsum(rng.normal(0, 1, n) * vol))
    spread = np.abs(rng.normal(0, 1, n)) * vol + 0.0005
    return pd.DataFrame({"open": close, "high": close * (1 + spread), "low": close * (1 - spread), "close": close,
                         "volume": 1.0}, index=idx)


class TestFutureRange(unittest.TestCase):
    def test_hand_computed(self):
        b = _toy([10, 12, 11, 15, 9], [8, 7, 9, 10, 6])
        f = future_range(b, 2)
        self.assertAlmostEqual(f.iloc[0], np.log(12 / 7))
        self.assertAlmostEqual(f.iloc[1], np.log(15 / 9))
        self.assertAlmostEqual(f.iloc[2], np.log(15 / 6))
        self.assertTrue(np.isnan(f.iloc[3]) and np.isnan(f.iloc[4]))     # window incomplete at the end

    def test_gap_gives_nan(self):
        b = _toy([10, 12, 11, 15, 9, 9.5], [8, 7, 9, 10, 6, 7])
        b2 = b.drop(b.index[3])                                           # hour 3 missing
        f = future_range(b2, 2)
        self.assertEqual(len(f), 6)                                       # gapless grid
        self.assertAlmostEqual(f.iloc[0], np.log(12 / 7))
        self.assertTrue(np.isnan(f.iloc[1]) and np.isnan(f.iloc[2]))      # windows touching the missing bar
        self.assertTrue(np.isnan(f.iloc[5]))                              # incomplete window at the end


class TestFeatures(unittest.TestCase):
    def test_features_ignore_later_bars(self):
        b = _walk(2_000)
        f1 = features(b)
        b2 = b.copy()
        k = 1_500
        b2.iloc[k:, b2.columns.get_loc("high")] *= 1.4
        b2.iloc[k:, b2.columns.get_loc("low")] *= 0.7
        f2 = features(b2)
        pd.testing.assert_frame_equal(f1.iloc[:k], f2.iloc[:k])
        self.assertFalse(f1.iloc[1_000].isna().any())

    def test_r6_and_d_values(self):
        b = _toy(list(np.arange(1, 41, dtype=float) + 1), list(np.arange(1, 41, dtype=float)))
        f = features(b)
        self.assertAlmostEqual(f["r6"].iloc[10], np.log(np.log(12 / 6)))   # bars 5..10: high 12, low 6 -> ln range
        self.assertAlmostEqual(f["d"].iloc[30], np.log(np.log(32 / 8)))    # bars 7..30: high 32, low 8


class TestWalkForward(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = _walk()
        cls.pred, cls.fits = walk_forward(cls.b, 24)

    def test_first_prediction_after_a_year_of_training(self):
        first = pd.Timestamp(self.pred.index[0], unit="ms")
        self.assertGreaterEqual(first, pd.Timestamp("2021-01-31"))
        self.assertTrue(((self.pred["lo"] < self.pred["pred"]) & (self.pred["pred"] < self.pred["hi"])).all())

    def test_no_look_ahead(self):
        month_starts = sorted(self.fits)
        s = month_starts[len(month_starts) // 2]
        b2 = self.b.copy()
        late = b2.index >= s
        b2.loc[late, "high"] *= 1.5
        b2.loc[late, "low"] *= 0.8
        pred2, fits2 = walk_forward(b2, 24)
        np.testing.assert_allclose(self.fits[s], fits2[s])               # the fit for that month ignores its own bars
        before = self.pred.index <= s                                     # decision at s uses only bars that closed by s
        pd.testing.assert_frame_equal(self.pred[before][["pred", "lo", "hi"]], pred2[pred2.index <= s][["pred", "lo", "hi"]])
        self.assertFalse(np.allclose(self.pred[~before]["pred"].iloc[:50], pred2[pred2.index > s]["pred"].iloc[:50]))

    def test_baseline_columns(self):
        p, _ = walk_forward(self.b, 24, cols=("d",))
        self.assertEqual(len(p), len(self.pred))


class TestTrafficLight(unittest.TestCase):
    def _series(self, n=24 * 150, seed=3):
        rng = np.random.default_rng(seed)
        return pd.Series(rng.normal(size=n), index=T0 + np.arange(n) * HOUR)

    def test_needs_90_days(self):
        c = traffic_light(self._series())
        self.assertTrue((c.iloc[:24 * 90] == "none").all())
        self.assertTrue(set(c.iloc[24 * 90:]) <= {"red", "yellow", "green"})

    def test_extremes(self):
        p = self._series()
        p.iloc[-1] = 99.0
        p.iloc[-2] = -99.0
        c = traffic_light(p)
        self.assertEqual(c.iloc[-1], "green")
        self.assertEqual(c.iloc[-2], "red")

    def test_uses_only_past(self):
        p = self._series()
        c1 = traffic_light(p)
        p2 = p.copy()
        k = 24 * 120
        p2.iloc[k:] = np.random.default_rng(9).normal(5, 3, len(p) - k)
        c2 = traffic_light(p2)
        self.assertTrue((c1.iloc[:k] == c2.iloc[:k]).all())


if __name__ == "__main__":
    unittest.main()
