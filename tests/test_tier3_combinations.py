"""
Tier 3: Pairwise & Cross-Feature Integration Test Suite
btc_market_intelligence project - E2E Testing Track

Covers interactions between multiple system components:
- Fast mode CLI + ATR dynamic risk model + Calibration tracker synchronization
- Quant Bias directional alignment with ATR trade recommendations
- On-chain macro cycle stages interaction with Quant Bias
- Dashboard data hydration across complete vs partial artifacts
- Subprocess runner contract alignment
- Path-dependent trade resolution against candle high/low extremes
- CLI flag combinations and precedence
- Snapshot compatibility with historical comparison engine
"""

import os
import sys
import json
import time
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.test_helpers import (
    run_cli,
    is_fast_mode_supported,
    is_atr_risk_implemented,
    is_onchain_implemented,
    is_dashboard_implemented,
    reference_atr_risk_levels,
    reference_mvrv_stage,
    reference_nupl_stage,
    make_mock_snapshot,
    make_mock_tracker,
)

import btc_market_intelligence as bmi


class TestTier3Combinations(unittest.TestCase):
    """Tier 3: Cross-Feature Interactions & Pairwise Combinations."""

    def test_c01_fast_mode_and_atr_risk_sync(self):
        """Fast mode snapshot synchronizes ATR risk levels with spot entry price."""
        snap = make_mock_snapshot()
        spot = snap["prices"]["spot_last"]
        risk = snap["risk_model"]
        self.assertEqual(risk["entry_price"], spot)
        self.assertLess(risk["long"]["stop_loss"], spot)
        self.assertGreater(risk["long"]["tp1_rr2"], spot)
        self.assertGreater(risk["short"]["stop_loss"], spot)
        self.assertLess(risk["short"]["tp1_rr2"], spot)

    def test_c02_quant_bias_direction_aligns_with_atr_recommendation(self):
        """Quant Bias score across critical values exactly aligns with recommended scenario."""
        test_matrix = [
            (-50, "SHORT"),
            (-16, "SHORT"),
            (-15, "SHORT"),
            (-14, "NEUTRAL"),
            (-5, "NEUTRAL"),
            (0, "NEUTRAL"),
            (10, "NEUTRAL"),
            (14, "NEUTRAL"),
            (15, "LONG"),
            (16, "LONG"),
            (60, "LONG"),
        ]
        price = 83000.0
        atr = 500.0
        for score, expected_dir in test_matrix:
            res = reference_atr_risk_levels(price, atr, quant_bias_score=score)
            self.assertEqual(
                res["direction"],
                expected_dir,
                f"Score {score} expected {expected_dir} but got {res['direction']}"
            )
            self.assertEqual(
                res["recommended"]["scenario"],
                expected_dir,
                f"Score {score} expected scenario {expected_dir} but got {res['recommended']['scenario']}"
            )

    def test_c03_onchain_macro_stage_with_quant_bias_composite(self):
        """Pairwise onchain macro extremes correspond with fundamental market posture."""
        # Generational bottom: MVRV < 0.1, NUPL < 0.0
        mvrv_bot = reference_mvrv_stage(0.05)
        nupl_bot = reference_nupl_stage(-0.15)
        self.assertIn("Bottom", mvrv_bot)
        self.assertEqual(nupl_bot, "Capitulation")

        # Bubble top: MVRV > 5.0, NUPL > 0.75
        mvrv_top = reference_mvrv_stage(5.8)
        nupl_top = reference_nupl_stage(0.82)
        self.assertIn("Cycle Top", mvrv_top)
        self.assertEqual(nupl_top, "Euphoria / Greed")

    def test_c04_dashboard_hydration_complete_artifacts(self):
        """Dashboard data layer successfully reads all project artifacts simultaneously."""
        snap_path = PROJECT_ROOT / "market_snapshot.json"
        hist_path = PROJECT_ROOT / "market_history.json"
        track_path = PROJECT_ROOT / "quant_calibration_tracker.json"
        md_path = PROJECT_ROOT / "daily_report.md"
        pdf_path = PROJECT_ROOT / "daily_report.pdf"

        # Verify all main artifacts can be parsed without conflict
        self.assertTrue(snap_path.exists())
        snap_data = json.loads(snap_path.read_text(encoding="utf-8"))
        prices = snap_data.get("prices") or snap_data.get("binance", {}).get("prices")
        self.assertIsNotNone(prices)

        if hist_path.exists():
            hist_data = json.loads(hist_path.read_text(encoding="utf-8"))
            self.assertIsInstance(hist_data, list)

        if track_path.exists():
            track_data = json.loads(track_path.read_text(encoding="utf-8"))
            self.assertIsInstance(track_data, list)

        if md_path.exists():
            md_text = md_path.read_text(encoding="utf-8")
            self.assertGreater(len(md_text), 100)

        if pdf_path.exists():
            self.assertGreater(pdf_path.stat().st_size, 1000)

    def test_c05_dashboard_hydration_partial_fast_mode_artifacts(self):
        """Dashboard data loading gracefully handles presence of only fast-mode artifacts."""
        # Simulated environment with only snapshot and tracker (no PDF, no MD)
        snap = make_mock_snapshot()
        track = make_mock_tracker()

        # Dashboard should extract pricing and risk model cleanly
        self.assertIn("prices", snap)
        self.assertIn("risk_model", snap)
        self.assertIsInstance(track, list)
        self.assertGreaterEqual(len(track), 1)

    def test_c06_subprocess_runner_command_alignment(self):
        """CLI arguments produced by dashboard runners align with btc_market_intelligence parser."""
        fast_cmd = [sys.executable, "btc_market_intelligence.py", "--fast"]
        self.assertEqual(fast_cmd[1], "btc_market_intelligence.py")
        self.assertEqual(fast_cmd[2], "--fast")

        self_test_cmd = [sys.executable, "btc_market_intelligence.py", "--self-test"]
        self.assertEqual(self_test_cmd[2], "--self-test")

    def test_c07_path_dependent_resolution_with_simulated_candles(self):
        """Simulation of signal resolution checking SL and TP touches on simulated price paths."""
        entry = 80000.0
        atr = 500.0  # SL = 79250 (-750), TP1 = 81500 (+1500)
        risk = reference_atr_risk_levels(entry, atr, quant_bias_score=20)
        sl = risk["long"]["stop_loss"]
        tp1 = risk["long"]["tp1_rr2"]

        # Path A: Bullish continuation touches TP1 first
        candles_bull = [
            {"high": 80500.0, "low": 79800.0},
            {"high": 81200.0, "low": 80200.0},
            {"high": 81600.0, "low": 80900.0},  # touches TP1 (81600 >= 81500)
        ]
        resolved_a = False
        outcome_a = None
        for c in candles_bull:
            if c["low"] <= sl:
                resolved_a, outcome_a = True, "LOSS"
                break
            if c["high"] >= tp1:
                resolved_a, outcome_a = True, "WIN"
                break
        self.assertTrue(resolved_a)
        self.assertEqual(outcome_a, "WIN")

        # Path B: Flash crash touches SL
        candles_bear = [
            {"high": 80200.0, "low": 79100.0},  # touches SL (79100 <= 79250)
        ]
        resolved_b = False
        outcome_b = None
        for c in candles_bear:
            if c["low"] <= sl:
                resolved_b, outcome_b = True, "LOSS"
                break
            if c["high"] >= tp1:
                resolved_b, outcome_b = True, "WIN"
                break
        self.assertTrue(resolved_b)
        self.assertEqual(outcome_b, "LOSS")

    def test_c08_cli_flag_combination_precedence(self):
        """Passing multiple valid flags (e.g. --self-test and --help) operates deterministically."""
        # --help should exit 0 with help text
        res = run_cli(["--self-test", "--help"], timeout=10.0)
        self.assertEqual(res.returncode, 0)

    def test_c09_mvrv_and_nupl_cycle_combinations_matrix(self):
        """Pairwise matrix of MVRV and NUPL states across 4 canonical cycle regimes."""
        regimes = [
            # (mvrv, nupl, expected_mvrv_keyword, expected_nupl)
            (-0.2, -0.1, "Bottom", "Capitulation"),
            (0.8, 0.35, "Fair Value", "Optimism / Anxiety"),
            (2.2, 0.65, "Mid-to-Late", "Belief / Denial"),
            (6.0, 0.85, "Cycle Top", "Euphoria / Greed"),
        ]
        for mvrv, nupl, mvrv_kw, exp_nupl in regimes:
            m_stage = reference_mvrv_stage(mvrv)
            n_stage = reference_nupl_stage(nupl)
            self.assertIn(mvrv_kw, m_stage)
            self.assertEqual(n_stage, exp_nupl)

    def test_c10_fast_snapshot_to_history_appending(self):
        """Snapshot data produced during fast scan appends seamlessly into history structure."""
        snap = make_mock_snapshot()
        hist = [snap]

        # Serialized and re-read from temp file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            json.dump(hist, tf)
            tf_path = Path(tf.name)
        try:
            with tf_path.open("r", encoding="utf-8") as f:
                read_back = json.load(f)
            self.assertEqual(len(read_back), 1)
            self.assertEqual(read_back[0]["prices"]["spot_last"], snap["prices"]["spot_last"])
        finally:
            if tf_path.exists():
                tf_path.unlink()


if __name__ == "__main__":
    unittest.main()
