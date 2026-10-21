"""Trade simulator and indicator sanity (offline, synthetic bars)."""

import unittest

import numpy as np
import pandas as pd

from btcmi.strategies import (
    FUNDING_8H, M15, MAKER, RISK_USD, SLIPPAGE, TAKER, Trade, alligator, fractals, simulate,
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


if __name__ == "__main__":
    unittest.main()
