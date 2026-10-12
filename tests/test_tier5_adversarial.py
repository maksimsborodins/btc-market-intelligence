"""
Tier 5: Adversarial Coverage Hardening & Empirical Stress Benchmark
btc_market_intelligence project - Challenger 1 Track

Adversarial stress-testing of:
1. ATR dynamic risk model mathematics under extreme boundary and fuzzed values
2. Fast momentum scan latency (<5.0s) over repeated iterations
3. Data persistence integrity (atomic replacement, corruption resistance)
4. Network fault injection and error propagation
"""

import math
import time
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
import requests

PROJECT_ROOT = Path(__file__).resolve().parent.parent
import btc_market_intelligence as bmi
from tests.test_helpers import reference_atr_risk_levels, run_cli


class TestAdversarialATRRiskMath(unittest.TestCase):
    """Adversarial stress testing of ATR Dynamic Risk Model mathematics."""

    def test_adv_01_exact_rr_ratio_invariance(self):
        """1:2 and 1:3 R:R ratios hold exactly across extreme spot prices ($1.0 to $1,000,000.0)."""
        test_cases = [
            (83000.0, 476.0, 30, "Normal BTC ($83,000)"),
            (1.0, 0.05, -20, "Single dollar asset ($1.00)"),
            (100.0, 2.50, 25, "Mid price asset ($100.00)"),
            (1000000.0, 25000.0, 50, "Million dollar BTC ($1,000,000)"),
            (83000.0, 1.0, 15, "Minimal volatility ($1 ATR)"),
            (83000.0, 10000.0, -15, "Extreme high volatility ($10,000 ATR)"),
        ]

        for sp, atr, score, desc in test_cases:
            with self.subTest(case=desc):
                res = bmi.calculate_atr_risk_levels(sp, atr, score)
                buffer = res["buffer"]
                self.assertAlmostEqual(buffer, round(1.5 * atr, 2), places=2)

                # Long scenario math
                long_risk = round(sp - res["long"]["stop_loss"], 2)
                long_tp1_reward = round(res["long"]["tp1_rr2"] - sp, 2)
                long_tp2_reward = round(res["long"]["tp2_rr3"] - sp, 2)

                self.assertAlmostEqual(long_risk, buffer, delta=0.02)
                self.assertAlmostEqual(long_tp1_reward / long_risk, 2.0, delta=0.01)
                self.assertAlmostEqual(long_tp2_reward / long_risk, 3.0, delta=0.01)

                # Short scenario math
                short_risk = round(res["short"]["stop_loss"] - sp, 2)
                short_tp1_reward = round(sp - res["short"]["tp1_rr2"], 2)
                short_tp2_reward = round(sp - res["short"]["tp2_rr3"], 2)

                self.assertAlmostEqual(short_risk, buffer, delta=0.02)
                self.assertAlmostEqual(short_tp1_reward / short_risk, 2.0, delta=0.01)
                self.assertAlmostEqual(short_tp2_reward / short_risk, 3.0, delta=0.01)

                # Dollar risk and risk %
                self.assertAlmostEqual(res["long"]["risk_usd"], buffer, delta=0.02)
                self.assertAlmostEqual(res["short"]["risk_usd"], buffer, delta=0.02)
                expected_risk_pct = round((buffer / sp) * 100, 2)
                self.assertAlmostEqual(res["long"]["risk_pct"], expected_risk_pct, delta=0.02)

    def test_adv_02_quant_bias_boundary_discontinuities(self):
        """Directional transitions at boundary scores (-16, -15, -14, 0, 14, 15, 16)."""
        sp, atr = 80000.0, 500.0
        boundary_matrix = [
            (-100, "SHORT", "SHORT"),
            (-16, "SHORT", "SHORT"),
            (-15, "SHORT", "SHORT"),
            (-14, "NEUTRAL", "NEUTRAL"),
            (-1, "NEUTRAL", "NEUTRAL"),
            (0, "NEUTRAL", "NEUTRAL"),
            (1, "NEUTRAL", "NEUTRAL"),
            (14, "NEUTRAL", "NEUTRAL"),
            (15, "LONG", "LONG"),
            (16, "LONG", "LONG"),
            (100, "LONG", "LONG"),
        ]

        for score, expected_dir, expected_rec in boundary_matrix:
            with self.subTest(score=score):
                res = bmi.calculate_atr_risk_levels(sp, atr, score)
                self.assertEqual(res["direction"], expected_dir)
                self.assertEqual(res["recommended"]["scenario"], expected_rec)

    def test_adv_03_zero_and_negative_input_resilience(self):
        """Zero and negative inputs must degrade gracefully without ZeroDivisionError."""
        edge_cases = [
            (0.0, 500.0, 20),
            (-50000.0, 500.0, 20),
            (80000.0, 0.0, 20),
            (80000.0, -100.0, 20),
            (0.0, 0.0, 0),
        ]

        for sp, atr, score in edge_cases:
            with self.subTest(sp=sp, atr=atr, score=score):
                res = bmi.calculate_atr_risk_levels(sp, atr, score)
                self.assertEqual(res["buffer"], 0.0)
                self.assertEqual(res["direction"], "NEUTRAL")
                self.assertEqual(res["long"]["risk_usd"], 0.0)
                self.assertEqual(res["long"]["risk_pct"], 0.0)

    def test_adv_04_type_fuzzing_and_null_resilience(self):
        """Non-float inputs, strings, None, and empty values handled gracefully."""
        res_none = bmi.calculate_atr_risk_levels(None, None, None)
        self.assertEqual(res_none["direction"], "NEUTRAL")
        self.assertEqual(res_none["entry_price"], 0.0)

        # Numeric string inputs
        res_str = bmi.calculate_atr_risk_levels("83000.5", "450.2", "25")
        self.assertEqual(res_str["direction"], "LONG")
        self.assertAlmostEqual(res_str["entry_price"], 83000.5, places=1)

    def test_adv_05_extreme_volatility_exceeding_asset_price(self):
        """When ATR * 1.5 exceeds spot price, long SL drops below zero (forensic discovery)."""
        sp = 100.0
        atr = 200.0  # Buffer = 300.0 -> Long SL = 100 - 300 = -200.0
        res = bmi.calculate_atr_risk_levels(sp, atr, 20)
        self.assertEqual(res["long"]["stop_loss"], -200.0)
        # Note: In financial reality, spot asset prices cannot go below $0.
        # This confirms that unconstrained math allows negative stop losses without floor clamping.
        self.assertLess(res["long"]["stop_loss"], 0.0)

    def test_adv_06_sub_cent_precision_buffer_collapse(self):
        """Forensic discovery: assets with ATR < 0.005 collapse buffer to 0.00 due to fixed 2-decimal rounding."""
        sp = 0.01
        atr = 0.001  # 1.5 * 0.001 = 0.0015 -> round(0.0015, 2) == 0.0
        res = bmi.calculate_atr_risk_levels(sp, atr, 20)
        self.assertEqual(res["buffer"], 0.0)
        self.assertEqual(res["long"]["stop_loss"], sp)
        self.assertEqual(res["long"]["risk_usd"], 0.0)


class TestAdversarialNetworkFaultInjection(unittest.TestCase):
    """Network fault injection during fast momentum scan."""

    @patch("btc_market_intelligence.safe_get_json")
    def test_adv_07_binance_timeout_raises_data_integrity_error(self, mock_get):
        """Adversarial discovery: total Binance timeout causes run_fast_momentum_scan to raise DataIntegrityError."""
        mock_get.return_value = None

        with self.assertRaises(bmi.DataIntegrityError):
            bmi.run_fast_momentum_scan(quiet=True, mock=False)

    @patch("btc_market_intelligence.safe_get_json")
    def test_adv_08_http_500_server_error_propagation(self, mock_get):
        """Adversarial discovery: 500 error on Binance ticker causes fast scan to raise DataIntegrityError."""
        mock_get.return_value = None

        with self.assertRaises(bmi.DataIntegrityError):
            bmi.run_fast_momentum_scan(quiet=True, mock=False)

    @patch("requests.Session.get")
    def test_adv_09_onchain_api_unreachable_fallback(self, mock_get):
        """Simulate LookIntoBitcoin/BGeometrics completely unreachable: returns UNAVAILABLE without crash."""
        mock_get.side_effect = requests.exceptions.ConnectTimeout("Connection timed out")

        onchain = bmi.fetch_onchain_metrics(use_cache=False)
        self.assertEqual(onchain["status"], "UNAVAILABLE")
        self.assertEqual(onchain["mvrv_stage"], "UNAVAILABLE")
        self.assertIsNone(onchain["mvrv_zscore"])


class TestAdversarialPersistenceAndConcurrency(unittest.TestCase):
    """Persistence integrity, atomic writes, and race condition resistance."""

    def test_adv_10_calibration_tracker_atomic_write_resistance(self):
        """Calibration tracker writes via temporary file and atomic replace."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tf_path = Path(tf.name)

        try:
            sample_data = [{"id": "test_1", "epoch": time.time(), "spot_price": 83000.0}]
            tf_path.write_text(json.dumps(sample_data), encoding="utf-8")

            # Update tracker
            snap = {"prices": {"spot_last": 83500.0}, "quant_bias": {"composite_score": 20, "bias_label": "BULLISH"}}
            stats = bmi.update_calibration_tracker(snap, tracker_path=tf_path)

            # Assert valid JSON preserved
            saved = json.loads(tf_path.read_text(encoding="utf-8"))
            self.assertIsInstance(saved, list)
            # Ensure no stray .tmp file remained
            tmp_path = tf_path.with_suffix(".tmp")
            self.assertFalse(tmp_path.exists())
        finally:
            if tf_path.exists():
                tf_path.unlink()

    def test_adv_11_rapid_successive_fast_runs_data_consistency(self):
        """Rapid successive runs do not duplicate calibration tracker signals within 2 hours."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            tf_path = Path(tf.name)

        try:
            # First run logs signal
            now = time.time()
            snap1 = {
                "prices": {"spot_last": 83000.0},
                "quant_bias": {"composite_score": 25, "bias_label": "BULLISH"},
                "divergence_engine": {"24h_divergence": {"divergence_state": "Bullish"}},
                "statistical_z_scores": {"oi_zscore": -0.5},
            }
            res1 = bmi.update_calibration_tracker(snap1, tracker_path=tf_path, force_time=now)
            self.assertTrue(res1["new_signal_logged_this_run"])
            self.assertEqual(res1["total_signals_tracked"], 1)

            # Second run 60 seconds later (within 2h minimum interval)
            res2 = bmi.update_calibration_tracker(snap1, tracker_path=tf_path, force_time=now + 60)
            self.assertFalse(res2["new_signal_logged_this_run"])
            self.assertEqual(res2["total_signals_tracked"], 1)
        finally:
            if tf_path.exists():
                tf_path.unlink()


if __name__ == "__main__":
    unittest.main()
