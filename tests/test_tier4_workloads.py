"""
Tier 4: Realistic Workloads & User Journeys Test Suite
btc_market_intelligence project - E2E Testing Track

Simulates complete end-to-end user journeys and operational scenarios:
- Workload 1: Fresh cold start run to fast momentum scan
- Workload 2: Repeated momentum scans under high volatility (latency stability)
- Workload 3: Signal issuance to 24h win/loss calibration resolution cycle
- Workload 4: Dashboard full data readiness across all 5 navigation tabs
- Workload 5: Offline verification pipeline and analytical integrity
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


class TestTier4Workloads(unittest.TestCase):
    """Tier 4: Real-World Workloads & End-to-End User Journeys."""

    def test_w01_journey_cold_start_to_fast_momentum_scan(self):
        """User Journey: Cold start initialization into fast momentum scan."""
        if not is_fast_mode_supported():
            self.skipTest("Feature 1: --fast pending implementation in Milestone 1")

        # Execute fast scan from cold state
        t0 = time.time()
        res = run_cli(["--fast"], timeout=10.0)
        duration = time.time() - t0

        self.assertEqual(res.returncode, 0)
        self.assertLess(duration, 7.0)

        # Verify output artifacts exist and are readable
        snapshot_path = PROJECT_ROOT / "market_snapshot.json"
        self.assertTrue(snapshot_path.exists())
        data = json.loads(snapshot_path.read_text(encoding="utf-8"))

        self.assertIn("prices", data)
        self.assertIn("quant_bias", data)
        self.assertIn("spot_last", data["prices"])
        self.assertIn("composite_score", data["quant_bias"])

    def test_w02_journey_repeated_momentum_scans_latency_stability(self):
        """User Journey: Active trader executes successive fast momentum scans."""
        if not is_fast_mode_supported():
            self.skipTest("Feature 1 & 2: Fast mode pending implementation in Milestone 1")

        durations = []
        for i in range(3):
            t0 = time.time()
            res = run_cli(["--fast"], timeout=10.0)
            elapsed = time.time() - t0
            self.assertEqual(res.returncode, 0, f"Run {i+1} failed: {res.stderr}")
            self.assertLess(elapsed, 8.5, f"Run {i+1} exceeded 8.5s ({elapsed:.2f}s)")
            durations.append(elapsed)

        # Average duration should remain within stable latency threshold
        avg_duration = sum(durations) / len(durations)
        self.assertLess(avg_duration, 8.0)

    def test_w03_journey_signal_issuance_to_calibration_resolution(self):
        """User Journey: Signal issuance at T0 -> 24h market move -> calibration resolution."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            tf_path = Path(tf.name)

        try:
            # 1. T0: Issue Bullish signal at $80,000
            t0 = time.time() - 25 * 3600  # 25 hours ago
            snap_t0 = {
                "prices": {"spot_last": 80000.0},
                "quant_bias": {"composite_score": 30, "bias_label": "BULLISH"},
                "divergence_engine": {"24h_divergence": {"divergence_state": "Bullish Accumulation"}},
                "statistical_z_scores": {"oi_zscore": -0.5},
            }
            res_t0 = bmi.update_calibration_tracker(snap_t0, tracker_path=tf_path, force_time=t0)
            self.assertEqual(res_t0["total_signals_tracked"], 1)
            self.assertEqual(res_t0["resolved_signals_count"], 0)

            # 2. T1: 25 hours later, price moves to $82,000 (+2.5%)
            t1 = t0 + 25 * 3600
            snap_t1 = {
                "prices": {"spot_last": 82000.0},
                "quant_bias": {"composite_score": 15, "bias_label": "BULLISH"},
                "divergence_engine": {"24h_divergence": {"divergence_state": "Neutral"}},
                "statistical_z_scores": {"oi_zscore": 0.0},
            }
            res_t1 = bmi.update_calibration_tracker(snap_t1, tracker_path=tf_path, force_time=t1)

            # 3. Verify signal transitioned from PENDING to RESOLVED (WIN)
            self.assertEqual(res_t1["resolved_signals_count"], 1)
            self.assertEqual(res_t1["wins_total"], 1)
            winrate = (res_t1["wins_total"] / res_t1["resolved_signals_count"]) * 100.0
            self.assertEqual(winrate, 100.0)

            # Verify persisted JSON records
            records = json.loads(tf_path.read_text(encoding="utf-8"))
            resolved_rec = [r for r in records if r.get("resolved")][0]
            self.assertTrue(resolved_rec["resolved"])
            self.assertEqual(resolved_rec["outcome"], "WIN")
        finally:
            if tf_path.exists():
                tf_path.unlink()

    def test_w04_journey_dashboard_data_readiness_across_all_tabs(self):
        """User Journey: Dashboard hydration engine prepares full dataset for all 5 tabs."""
        # Synthesize complete environment snapshot
        snap = make_mock_snapshot()
        track = make_mock_tracker()

        # Tab 1 Data Readiness: Quant Bias Speedometer & Factor Breakdown
        self.assertIn("composite_score", snap["quant_bias"])
        self.assertIn("bias_label", snap["quant_bias"])
        self.assertIn("breakdown", snap["quant_bias"])
        score = snap["quant_bias"]["composite_score"]
        self.assertTrue(-100 <= score <= 100)

        # Tab 2 Data Readiness: Interactive Technical Charts (CVD, OI, Funding)
        self.assertIn("spot_cvd", snap)
        self.assertIn("15m", snap["spot_cvd"])
        self.assertIn("24h", snap["spot_cvd"])
        self.assertIn("statistical_z_scores", snap)
        self.assertIn("oi_zscore", snap["statistical_z_scores"])

        # Tab 3 Data Readiness: Dynamic ATR Risk & Trade Plans
        self.assertIn("risk_model", snap)
        risk = snap["risk_model"]
        self.assertIn("long", risk)
        self.assertIn("short", risk)
        self.assertIn("recommended", risk)
        self.assertIn("stop_loss", risk["long"])
        self.assertIn("tp1_rr2", risk["long"])
        self.assertIn("tp2_rr3", risk["long"])

        # Tab 4 Data Readiness: Reports & Artifacts
        md_file = PROJECT_ROOT / "daily_report.md"
        pdf_file = PROJECT_ROOT / "daily_report.pdf"
        self.assertTrue(md_file.exists())
        self.assertTrue(pdf_file.exists())

        # Tab 5 Data Readiness: Winrate Calibration & History Table
        self.assertIsInstance(track, list)
        self.assertGreater(len(track), 0)
        rec = track[0]
        self.assertIn("id", rec)
        self.assertIn("spot_price", rec)
        self.assertIn("quant_bias_score", rec)

    def test_w05_journey_offline_verification_and_pipeline_integrity(self):
        """User Journey: Full offline self-test execution validates all subsystems."""
        t0 = time.time()
        res = run_cli(["--self-test"], timeout=20.0)
        duration = time.time() - t0

        self.assertEqual(res.returncode, 0, f"Self-test failed: {res.stderr}")
        self.assertIn("SELF-TEST: PASS", res.stdout)
        self.assertIn("No network/API/Gemini credentials were used", res.stdout)
        self.assertLess(duration, 15.0)


if __name__ == "__main__":
    unittest.main()
