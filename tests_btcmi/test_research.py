"""Point-in-time correctness of the picture and sanity of the research statistics (offline, synthetic data)."""

import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from btcmi import db
from btcmi.features import HOUR_MS, add_targets, asof_series, build_picture, FEATURE_COLUMNS
from btcmi.research import (
    block_bootstrap_ic, block_bootstrap_mean, evaluate_states, run_research, us_session_mask, walk_forward_quintiles,
)

START = 1_700_000_000_000 // HOUR_MS * HOUR_MS  # 2023-11-14, hour aligned


def _bars(venue, symbol, closes, taker_share, start=START):
    rows = []
    for i, c in enumerate(closes):
        vol = 100.0
        rows.append({
            "venue": venue, "symbol": symbol, "interval": "1h", "ts": start + i * HOUR_MS,
            "open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
            "volume": vol, "quote_volume": vol * c, "taker_buy_volume": vol * taker_share[i], "trades": 10,
        })
    return rows


def _series(metric, values, lag_h=0, start=START):
    return [{"metric": metric, "ts": start + i * HOUR_MS, "value": v, "available_at": start + (i + lag_h) * HOUR_MS}
            for i, v in enumerate(values)]


class TempDb(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.conn = db.connect(os.path.join(self.dir.name, "t.db"))
        self.addCleanup(self.conn.close)

    def fill(self, n=24 * 60, seed=1):
        rng = np.random.default_rng(seed)
        closes = 30000 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
        spot_share = np.clip(0.5 + rng.normal(0, 0.05, n), 0.05, 0.95)
        perp_share = np.clip(0.5 + rng.normal(0, 0.05, n), 0.05, 0.95)
        oi = 80000 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
        db.upsert_bars(self.conn, _bars("binance_spot", "BTCUSDT", closes, spot_share))
        db.upsert_bars(self.conn, _bars("binance_perp", "BTCUSDT", closes * 1.0002, perp_share))
        db.upsert_bars(self.conn, _bars("coinbase_spot", "BTC-USD", closes * 1.0005, spot_share))
        db.upsert_series(self.conn, _series("binance.oi", oi))
        db.upsert_series(self.conn, _series("bybit.oi", oi * 0.6))
        db.upsert_series(self.conn, _series("binance.premium", rng.normal(0, 1e-4, n), lag_h=1))
        db.upsert_series(self.conn, _series("binance.funding", np.full(n, 1e-4)))
        return n


class TestPointInTime(TempDb):
    def test_asof_respects_publication_time(self):
        # value for hour 0 is published 3 hours later: it must not be visible at T = hour 1 or 2
        db.upsert_series(self.conn, [{"metric": "binance.funding", "ts": START, "value": 7.0,
                                      "available_at": START + 3 * HOUR_MS}])
        grid = pd.Index([START + k * HOUR_MS for k in range(1, 6)])
        s = asof_series(self.conn, "binance.funding", grid)
        self.assertTrue(np.isnan(s.iloc[0]) and np.isnan(s.iloc[1]))
        self.assertEqual(s.iloc[2], 7.0)

    def test_stale_values_are_dropped(self):
        db.upsert_series(self.conn, [{"metric": "binance.oi", "ts": START, "value": 5.0, "available_at": START}])
        grid = pd.Index([START, START + HOUR_MS, START + 3 * HOUR_MS])
        s = asof_series(self.conn, "binance.oi", grid)  # binance.oi staleness limit: 1 h
        self.assertEqual(list(s.iloc[:2]), [5.0, 5.0])
        self.assertTrue(np.isnan(s.iloc[2]))

    def test_future_data_does_not_change_the_past(self):
        n = self.fill()
        before = build_picture(self.conn)
        cut = START + (n // 2) * HOUR_MS
        # rewrite everything after the cut: bars that close after the cut and series published after it
        self.conn.execute("UPDATE bars SET close = close * 1.5, taker_buy_volume = volume WHERE ts + ? > ?", (HOUR_MS, cut))
        self.conn.execute("UPDATE series SET value = value * 3 WHERE available_at > ?", (cut,))
        self.conn.commit()
        after = build_picture(self.conn)
        cols = [c for c in before.columns if not c.startswith("fwd_")]
        a = before.loc[before.index <= cut, cols]
        b = after.loc[after.index <= cut, cols]
        pd.testing.assert_frame_equal(a, b)
        self.assertFalse(before.loc[before.index > cut, "close"].equals(after.loc[after.index > cut, "close"]))

    def test_rise_on_leverage_state(self):
        n = 24 * 40
        closes = np.concatenate([np.full(n - 4, 30000.0), 30000 * np.array([1.003, 1.006, 1.009, 1.012])])
        spot_share = np.concatenate([np.full(n - 4, 0.5), np.full(4, 0.3)])   # spot takers selling into the rise
        perp_share = np.concatenate([np.full(n - 4, 0.5), np.full(4, 0.7)])
        rng = np.random.default_rng(3)
        closes[: n - 4] *= np.exp(rng.normal(0, 0.002, n - 4))
        oi = np.concatenate([80000 * np.exp(rng.normal(0, 0.001, n - 4)), 80000 * np.array([1.01, 1.02, 1.03, 1.04])])
        db.upsert_bars(self.conn, _bars("binance_spot", "BTCUSDT", closes, spot_share))
        db.upsert_bars(self.conn, _bars("binance_perp", "BTCUSDT", closes, perp_share))
        db.upsert_series(self.conn, _series("binance.oi", oi))
        db.upsert_series(self.conn, _series("bybit.oi", oi * 0.5))
        df = build_picture(self.conn)
        last = df.iloc[-1]
        self.assertEqual(last["combo_4h"], "rise_on_leverage")
        self.assertEqual(last["oi_state_4h"], "long_buildup")
        self.assertEqual(last["driver_4h"], "rise_spot_selling")

    def test_missing_bar_keeps_hour_arithmetic(self):
        # a 3-hour exchange outage: ret_24h and fwd_24h must still span 24 real hours, not 24 stored rows
        n = self.fill(n=24 * 40)
        gap = START + 500 * HOUR_MS
        self.conn.execute("DELETE FROM bars WHERE venue = 'binance_spot' AND ts BETWEEN ? AND ?", (gap, gap + 2 * HOUR_MS))
        self.conn.commit()
        df = add_targets(build_picture(self.conn))
        self.assertEqual(len(df), n)
        T = START + 520 * HOUR_MS
        self.assertAlmostEqual(df.loc[T, "ret_24h"], np.log(df.loc[T, "close"] / df.loc[T - 24 * HOUR_MS, "close"]))
        T0 = START + 480 * HOUR_MS
        self.assertAlmostEqual(df.loc[T0, "fwd_24h"], np.log(df.loc[T0 + 24 * HOUR_MS, "close"] / df.loc[T0, "close"]))
        self.assertTrue(np.isnan(df.loc[gap + HOUR_MS, "close"]))

    def test_missing_flow_gives_no_state(self):
        self.fill(n=24 * 40)
        self.conn.execute("DELETE FROM bars WHERE venue = 'binance_perp'")
        self.conn.commit()
        df = build_picture(self.conn)
        self.assertTrue(df["combo_4h"].isna().all())


class TestStatistics(unittest.TestCase):
    def test_bootstrap_mean_covers_true_mean(self):
        rng = np.random.default_rng(0)
        v = rng.normal(0.5, 1, 5000)
        m, lo, hi = block_bootstrap_mean(v, 10, rng)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        self.assertLess(hi - lo, 0.2)

    def test_ic_detects_signal_and_not_noise(self):
        rng = np.random.default_rng(1)
        x = rng.normal(size=5000)
        ic, lo, hi, _ = block_bootstrap_ic(x, x + rng.normal(scale=3, size=5000), 4, rng)
        self.assertGreater(lo, 0)
        ic0, lo0, hi0, _ = block_bootstrap_ic(x, rng.normal(size=5000), 4, rng)
        self.assertLess(lo0, 0)
        self.assertGreater(hi0, 0)

    def test_walk_forward_uses_only_the_past(self):
        # the feature predicts the 1h return perfectly, but the sign flips at a month boundary: the first month after
        # the flip must still be traded with the OLD sign (it could not have been known), so it loses
        hours = 24 * 400
        idx = pd.Index([START + k * HOUR_MS for k in range(hours)])
        rng = np.random.default_rng(2)
        y = pd.Series(rng.normal(0, 0.01, hours), index=idx)
        t = pd.to_datetime(np.asarray(idx), unit="ms", utc=True)
        flip_month = t[24 * 300].to_period("M")
        flip_ms = int(flip_month.to_timestamp().tz_localize("UTC").value // 1_000_000)
        x = y.copy()
        x[idx >= flip_ms] = -y[idx >= flip_ms]
        pos = walk_forward_quintiles(x, y, 1)
        first_month = (pd.Series(t.to_period("M"), index=idx) == flip_month).to_numpy()
        pnl_after = (pos[first_month] * y[first_month]).sum()
        before = (idx < flip_ms) & pos.notna().to_numpy()
        pnl_before = (pos[before] * y[before]).sum()
        self.assertGreater(pnl_before, 0)
        self.assertLess(pnl_after, 0)
        self.assertTrue(pos[: 24 * 170].isna().all())  # no positions before the minimum training period

    def test_state_is_compared_with_the_whole_market(self):
        # a sparse state with no effect on a rising market: its base must be every hour, not only state hours
        hours = 24 * 400
        idx = pd.Index([START + k * HOUR_MS for k in range(hours)])
        rng = np.random.default_rng(4)
        y = rng.normal(0.001, 0.01, hours)
        state = np.full(hours, None, dtype=object)
        on = rng.random(hours) < 0.05
        state[on] = "a"
        y[on] -= 0.003                       # "a" is worse than the market...
        b = (~on) & (rng.random(hours) < 0.05)
        state[b] = "b"                       # ..."b" is the market itself
        df = pd.DataFrame({"combo_24h": state, "fwd_24h": y}, index=idx)
        res = {r.state: r for r in evaluate_states(df, "combo_24h", 24, "all", np.ones(hours, bool), rng)}
        self.assertAlmostEqual(res["a"].base_mean, y.mean())
        self.assertLess(res["a"].excess, 0)
        self.assertLess(abs(res["b"].excess), 0.001)

    def test_us_session_mask_follows_riga_time(self):
        # 2026-07-01 14:00 UTC = 17:00 Riga (summer, UTC+3); 2026-01-15 14:00 UTC = 16:00 Riga (winter, UTC+2)
        summer = int(pd.Timestamp("2026-07-01 14:00", tz="UTC").value // 1_000_000)
        winter = int(pd.Timestamp("2026-01-15 14:00", tz="UTC").value // 1_000_000)
        self.assertEqual(list(us_session_mask(pd.Index([summer, winter]))), [True, False])


class TestEndToEnd(TempDb):
    """Two years of synthetic data: the acceptance rule must reject noise AND find a planted effect."""

    def test_pure_noise_is_rejected(self):
        self.fill(n=24 * 730, seed=5)
        report = run_research(add_targets(build_picture(self.conn)), seed=1)
        self.assertGreater(report["tests"]["features"], 0)
        self.assertGreater(report["tests"]["states"], 0)
        accepted_f = [(r["feature"], r["horizon_h"], r["subset"]) for r in report["features"] if r["accepted"]]
        accepted_s = [(r["state"], r["state_column"], r["horizon_h"]) for r in report["states"] if r["accepted"]]
        # a random walk has no edge: an accepted result here is a false positive of the method itself
        self.assertLessEqual(len(accepted_f), 1, accepted_f)
        self.assertLessEqual(len(accepted_s), 1, accepted_s)
        self.assertTrue(set(FEATURE_COLUMNS) >= {r["feature"] for r in report["features"]})

    def test_planted_spot_flow_effect_is_found(self):
        n = 24 * 730
        rng = np.random.default_rng(11)
        # persistent spot taker share; the next hours drift with the last day's spot buying
        share = np.empty(n)
        share[0] = 0.5
        for i in range(1, n):
            share[i] = 0.5 + 0.97 * (share[i - 1] - 0.5) + rng.normal(0, 0.01)
        share = np.clip(share, 0.05, 0.95)
        past_day = pd.Series(share).rolling(24).mean().shift(1).fillna(0.5).to_numpy()
        returns = 0.004 * (past_day - 0.5) / 0.05 * 0.25 + rng.normal(0, 0.004, n)
        closes = 30000 * np.exp(np.cumsum(returns))
        perp_share = np.clip(0.5 + rng.normal(0, 0.03, n), 0.05, 0.95)
        oi = 80000 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
        db.upsert_bars(self.conn, _bars("binance_spot", "BTCUSDT", closes, share))
        db.upsert_bars(self.conn, _bars("binance_perp", "BTCUSDT", closes, perp_share))
        db.upsert_series(self.conn, _series("binance.oi", oi))
        db.upsert_series(self.conn, _series("bybit.oi", oi * 0.6))
        report = run_research(add_targets(build_picture(self.conn)), seed=1)
        found = {(r["feature"], r["horizon_h"]) for r in report["features"] if r["accepted"] and r["subset"] == "all_hours"}
        self.assertTrue(any(f.startswith("spot_delta_24h") for f, _ in found), found)


if __name__ == "__main__":
    unittest.main()
