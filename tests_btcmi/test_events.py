"""Event-study helpers: onsets and the size-stratified calendar-block bootstrap."""

import unittest

import numpy as np
import pandas as pd

from btcmi.events import HOUR_MS, onsets, stratified_diff

START = 1_700_000_000_000 // HOUR_MS * HOUR_MS


def _events(n, effect, seed, size_effect=0.0):
    rng = np.random.default_rng(seed)
    idx = pd.Index(START + np.sort(rng.choice(24 * 2000, n, replace=False)) * HOUR_MS)
    size = rng.normal(size=n)
    # signal events are mostly the small ones: a naive difference would pick up the size effect
    signal = rng.random(n) < 1 / (1 + np.exp(2 * size))
    y = size_effect * size + effect * signal + rng.normal(0, 0.03, n)
    return pd.DataFrame({"y": y, "size": size, "signal": signal}, index=idx)


class TestEvents(unittest.TestCase):
    def test_onsets_take_first_hour_and_block(self):
        cond = pd.Series([False, True, True, False, True, False, False, True, True])
        self.assertEqual(list(np.flatnonzero(onsets(cond, 5))), [1, 7])

    def test_planted_effect_is_found(self):
        r = stratified_diff(_events(1500, 0.01, 1), 72, np.random.default_rng(0))
        self.assertGreater(r["lo"], 0)
        self.assertGreater(r["t"], 2.5)

    def test_size_confounding_is_removed(self):
        # outcome depends only on size; signal is concentrated in small sizes; stratified difference ~ 0
        ev = _events(1500, 0.0, 2, size_effect=0.02)
        naive = ev[ev.signal].y.mean() - ev[~ev.signal].y.mean()
        r = stratified_diff(ev, 72, np.random.default_rng(0))
        self.assertLess(naive, -0.01)
        self.assertLess(r["lo"], 0)
        self.assertGreater(r["hi"], 0)
        self.assertLess(abs(r["diff"]), abs(naive) / 3)

    def test_too_few_events(self):
        r = stratified_diff(_events(1500, 0.0, 3).iloc[:2], 72, np.random.default_rng(0))
        self.assertTrue(np.isnan(r["diff"]))


if __name__ == "__main__":
    unittest.main()
