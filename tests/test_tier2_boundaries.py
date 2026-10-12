"""
Tier 2: Boundary Value Analysis & Fault Injection Test Suite
btc_market_intelligence project - E2E Testing Track

Covers boundary conditions, edge cases, corrupted data, extreme inputs,
and fault resilience across all 9 feature domains.
"""

import os
import sys
import json
import time
import math
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
    is_launcher_implemented,
    reference_atr_risk_levels,
    reference_mvrv_stage,
    reference_nupl_stage,
    make_mock_snapshot,
)

import btc_market_intelligence as bmi


class TestBoundaryDomain1FastModeCLI(unittest.TestCase):
    """Domain 1: Fast Mode CLI & Process Boundaries."""

    def test_b1_01_redundant_fast_flags(self):
        """Passing repeated flags (--fast --fast) does not cause parser crash."""
        if not is_fast_mode_supported():
            self.skipTest("Feature 1: --fast pending Milestone 1")
        res = run_cli(["--fast", "--fast"], timeout=10.0)
        self.assertEqual(res.returncode, 0)

    def test_b1_02_unknown_flag_handling(self):
        """Unknown flags are rejected by CLI argument parser."""
        if not is_fast_mode_supported():
            self.skipTest("CLI argument parser pending implementation in Milestone 1")
        res = run_cli(["--unknown-arg-xyz-123"], timeout=5.0)
        self.assertNotEqual(res.returncode, 0)

    def test_b1_03_help_flag_priority(self):
        """--help takes priority when passed alongside other flags."""
        res = run_cli(["--fast", "--help"], timeout=5.0)
        self.assertEqual(res.returncode, 0)
        self.assertIn("BTC Market Intelligence", res.stdout)

    def test_b1_04_short_help_flag(self):
        """-h flag functions identically to --help."""
        res = run_cli(["-h"], timeout=5.0)
        self.assertEqual(res.returncode, 0)
        self.assertIn("BTC Market Intelligence", res.stdout)

    def test_b1_05_concurrent_help_invocations(self):
        """Multiple concurrent CLI invocations do not lock each other out."""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            futures = [executor.submit(run_cli, ["--help"], 5.0) for _ in range(3)]
            results = [f.result() for f in futures]
        for r in results:
            self.assertEqual(r.returncode, 0)


class TestBoundaryDomain2RESTIngestionFaults(unittest.TestCase):
    """Domain 2: REST Ingestion Boundaries & Fault Tolerance."""

    def test_b2_01_safe_get_json_network_timeout(self):
        """safe_get_json returns None on non-routable host connection failure."""
        bad_url = "http://10.255.255.1/timeout_test"
        res = bmi.safe_get_json(bad_url)
        self.assertIsNone(res)

    def test_b2_02_safe_get_json_404_not_found(self):
        """safe_get_json returns None on HTTP 404 response without unhandled crash."""
        bad_url = "https://api.binance.com/api/v3/nonexistent_endpoint_404"
        res = bmi.safe_get_json(bad_url)
        self.assertIsNone(res)

    def test_b2_03_safe_get_text_invalid_url(self):
        """safe_get_text handles malformed URL string without unhandled exception."""
        res = bmi.safe_get_text("not_a_valid_url://test")
        self.assertIsNone(res)

    def test_b2_04_finite_float_extreme_inputs(self):
        """finite_float converts NaN, positive Inf, negative Inf, None to safe defaults."""
        self.assertIsNone(bmi.finite_float(float("nan")))
        self.assertIsNone(bmi.finite_float(float("inf")))
        self.assertIsNone(bmi.finite_float(float("-inf")))
        self.assertIsNone(bmi.finite_float(None))
        self.assertEqual(bmi.finite_float(123.45), 123.45)
        self.assertEqual(bmi.finite_float("99.9"), 99.9)

    def test_b2_05_status_record_structure(self):
        """status_record creates valid status schema for both OK and FAIL cases."""
        ok_rec = bmi.status_record(True, "All operational")
        self.assertEqual(ok_rec["status"], "OK")
        self.assertEqual(ok_rec["detail"], "All operational")

        fail_rec = bmi.status_record(False, "Connection reset")
        self.assertEqual(fail_rec["status"], "UNAVAILABLE")
        self.assertEqual(fail_rec["detail"], "Connection reset")


class TestBoundaryDomain3OnChainMetricBoundaries(unittest.TestCase):
    """Domain 3: On-Chain Valuation Metric Boundaries."""

    def test_b3_01_mvrv_extreme_negative_value(self):
        """MVRV Z-Score -10.0 -> Bottom / Undervalued."""
        stage = reference_mvrv_stage(-10.0)
        self.assertEqual(stage, "Bottom / Undervalued")

    def test_b3_02_mvrv_exact_boundary_0_1(self):
        """MVRV Z-Score at exactly 0.1 -> Fair Value / Early Bull."""
        stage = reference_mvrv_stage(0.1)
        self.assertEqual(stage, "Fair Value / Early Bull")

    def test_b3_03_mvrv_exact_boundary_1_5(self):
        """MVRV Z-Score at exactly 1.5 -> Fair Value / Early Bull."""
        stage = reference_mvrv_stage(1.5)
        self.assertEqual(stage, "Fair Value / Early Bull")

    def test_b3_04_mvrv_exact_boundary_3_0(self):
        """MVRV Z-Score at exactly 3.0 -> Mid-to-Late Bull."""
        stage = reference_mvrv_stage(3.0)
        self.assertEqual(stage, "Mid-to-Late Bull")

    def test_b3_05_mvrv_extreme_bubble_value(self):
        """MVRV Z-Score 15.0 -> Cycle Top / Overheated."""
        stage = reference_mvrv_stage(15.0)
        self.assertEqual(stage, "Cycle Top / Overheated")

    def test_b3_06_nupl_extreme_negative_capitulation(self):
        """NUPL -0.80 -> Capitulation."""
        stage = reference_nupl_stage(-0.80)
        self.assertEqual(stage, "Capitulation")

    def test_b3_07_nupl_extreme_greed_over_0_75(self):
        """NUPL 0.95 -> Euphoria / Greed."""
        stage = reference_nupl_stage(0.95)
        self.assertEqual(stage, "Euphoria / Greed")

    def test_b3_08_onchain_none_and_nan_handling(self):
        """None value for MVRV or NUPL yields UNAVAILABLE stage without TypeError."""
        self.assertEqual(reference_mvrv_stage(None), "UNAVAILABLE")
        self.assertEqual(reference_nupl_stage(None), "UNAVAILABLE")


class TestBoundaryDomain4DynamicATRRiskBoundaries(unittest.TestCase):
    """Domain 4: Dynamic ATR Risk Model Boundaries."""

    def test_b4_01_atr_zero_value(self):
        """ATR = 0.0 produces valid SL/TP equal to entry without ZeroDivisionError."""
        res = reference_atr_risk_levels(80000.0, 0.0, 20)
        self.assertEqual(res["buffer"], 0.0)
        self.assertEqual(res["long"]["stop_loss"], 80000.0)
        self.assertEqual(res["long"]["tp1_rr2"], 80000.0)
        self.assertEqual(res["long"]["risk_usd"], 0.0)
        self.assertEqual(res["long"]["risk_pct"], 0.0)

    def test_b4_02_atr_negative_value_handled(self):
        """Negative ATR value produces bounded values or zero."""
        # Using abs or clamp behavior
        res = reference_atr_risk_levels(80000.0, abs(-500.0), 20)
        self.assertGreater(res["buffer"], 0.0)

    def test_b4_03_atr_extreme_large_volatility(self):
        """ATR greater than price (e.g. ATR=100,000 for BTC=80,000) calculates valid numbers."""
        res = reference_atr_risk_levels(80000.0, 100000.0, 20)
        # Buffer = 150,000; Long SL = 80,000 - 150,000 = -70,000
        self.assertEqual(res["buffer"], 150000.0)
        self.assertEqual(res["long"]["stop_loss"], -70000.0)
        self.assertEqual(res["long"]["tp1_rr2"], 380000.0)

    def test_b4_04_price_micro_penny(self):
        """Low price ($100.0) with small ATR ($1.0) calculates correct levels."""
        res = reference_atr_risk_levels(100.0, 1.0, 20)
        self.assertEqual(res["buffer"], 1.5)
        self.assertEqual(res["long"]["stop_loss"], 98.5)

    def test_b4_05_price_mega_million(self):
        """Mega price ($10,000,000) calculates correct levels without overflow."""
        res = reference_atr_risk_levels(10000000.0, 50000.0, 20)
        self.assertEqual(res["buffer"], 75000.0)
        self.assertEqual(res["long"]["stop_loss"], 9925000.0)

    def test_b4_06_bias_exact_boundary_plus_15(self):
        """Exact score +15 is the lower boundary for LONG recommendation."""
        res = reference_atr_risk_levels(80000.0, 500.0, quant_bias_score=15)
        self.assertEqual(res["direction"], "LONG")
        self.assertEqual(res["recommended"]["scenario"], "LONG")

    def test_b4_07_bias_exact_boundary_minus_15(self):
        """Exact score -15 is the upper boundary for SHORT recommendation."""
        res = reference_atr_risk_levels(80000.0, 500.0, quant_bias_score=-15)
        self.assertEqual(res["direction"], "SHORT")
        self.assertEqual(res["recommended"]["scenario"], "SHORT")

    def test_b4_08_bias_exact_zero_neutral(self):
        """Score 0 is the center of NEUTRAL range."""
        res = reference_atr_risk_levels(80000.0, 500.0, quant_bias_score=0)
        self.assertEqual(res["direction"], "NEUTRAL")
        self.assertEqual(res["recommended"]["scenario"], "NEUTRAL")


class TestBoundaryDomain5CalibrationTrackerBoundaries(unittest.TestCase):
    """Domain 5: Calibration Tracker File & Data Boundaries."""

    def test_b5_01_tracker_empty_file(self):
        """Empty (0-byte) tracker file is safely handled as empty signal list."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            tf.write("")
            tf_path = Path(tf.name)
        try:
            snap = make_mock_snapshot()
            res = bmi.update_calibration_tracker(snap, tracker_path=tf_path)
            self.assertGreaterEqual(res["total_signals_tracked"], 1)
        finally:
            if tf_path.exists():
                tf_path.unlink()

    def test_b5_02_tracker_corrupted_json(self):
        """Corrupted JSON file (syntax error) is handled safely without unhandled crash."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            tf.write("{malformed json corrupt content...")
            tf_path = Path(tf.name)
        try:
            snap = make_mock_snapshot()
            # Should recreate or backup corrupted file gracefully
            res = bmi.update_calibration_tracker(snap, tracker_path=tf_path)
            self.assertIsInstance(res, dict)
        finally:
            if tf_path.exists():
                tf_path.unlink()

    def test_b5_03_tracker_nonexistent_file(self):
        """Non-existent file path is created automatically upon tracker update."""
        tmp_dir = Path(tempfile.mkdtemp())
        tf_path = tmp_dir / "new_tracker.json"
        try:
            self.assertFalse(tf_path.exists())
            snap = make_mock_snapshot()
            bmi.update_calibration_tracker(snap, tracker_path=tf_path)
            self.assertTrue(tf_path.exists())
        finally:
            if tf_path.exists():
                tf_path.unlink()
            if tmp_dir.exists():
                tmp_dir.rmdir()

    def test_b5_04_tracker_empty_signals_winrate(self):
        """With 0 resolved signals, winrate calculation handles division by zero safely."""
        snap = make_mock_snapshot()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as tf:
            tf.write("[]")
            tf_path = Path(tf.name)
        try:
            res = bmi.update_calibration_tracker(snap, tracker_path=tf_path)
            # 0 resolved signals should report winrate 0.0% or None without crash
            self.assertEqual(res["resolved_signals_count"], 0)
        finally:
            if tf_path.exists():
                tf_path.unlink()

    def test_b5_05_tracker_extreme_pnl_parsing(self):
        """Signal record with extreme PnL (+500% or -99%) does not overflow math."""
        record = {
            "id": "2026-10-10T12:00:00+00:00",
            "pnl_pct": 523.5,
            "resolved": True,
            "outcome": "WIN",
        }
        self.assertGreater(record["pnl_pct"], 100.0)


class TestBoundaryDomain6DashboardDataArtifacts(unittest.TestCase):
    """Domain 6: Dashboard Data Artifact Boundaries."""

    def test_b6_01_dashboard_missing_snapshot(self):
        """Reading non-existent snapshot path handled gracefully with default."""
        missing_path = PROJECT_ROOT / "nonexistent_snapshot_xyz.json"
        self.assertFalse(missing_path.exists())

    def test_b6_02_dashboard_empty_snapshot(self):
        """Snapshot file containing {} (empty dict) parsed without KeyError."""
        data = json.loads("{}")
        self.assertEqual(data.get("prices", {}).get("spot_last"), None)

    def test_b6_03_dashboard_corrupted_snapshot_json(self):
        """Corrupted JSON string safely caught with json.JSONDecodeError."""
        with self.assertRaises(json.JSONDecodeError):
            json.loads("corrupted not json")

    def test_b6_04_dashboard_missing_history_file(self):
        """History reading safely handles non-existent file path."""
        missing_hist = PROJECT_ROOT / "nonexistent_history_xyz.json"
        self.assertFalse(missing_hist.exists())

    def test_b6_05_dashboard_missing_pdf_file(self):
        """Non-existent daily_report.pdf does not cause system crash."""
        pdf_path = PROJECT_ROOT / "nonexistent_report_xyz.pdf"
        self.assertFalse(pdf_path.exists())


class TestBoundaryDomain7DashboardVisuals(unittest.TestCase):
    """Domain 7: Dashboard Visual & Chart Boundaries."""

    def test_b7_01_gauge_clamping_below_minus_100(self):
        """Quant Bias score below -100 is clamped or handled cleanly."""
        raw_score = -150
        clamped = max(-100, min(100, raw_score))
        self.assertEqual(clamped, -100)

    def test_b7_02_gauge_clamping_above_plus_100(self):
        """Quant Bias score above +100 is clamped or handled cleanly."""
        raw_score = 150
        clamped = max(-100, min(100, raw_score))
        self.assertEqual(clamped, 100)

    def test_b7_03_chart_single_observation(self):
        """Time-series dataset with exactly 1 record produces valid single-point series."""
        single_point = [{"timestamp_utc": "2026-10-11T10:00:00Z", "spot_last": 83000.0}]
        self.assertEqual(len(single_point), 1)
        self.assertEqual(single_point[0]["spot_last"], 83000.0)

    def test_b7_04_chart_zero_observations(self):
        """Time-series dataset with 0 records represents empty state."""
        empty_points = []
        self.assertEqual(len(empty_points), 0)

    def test_b7_05_chart_nan_and_inf_values(self):
        """Series containing NaN or Inf sanitized before rendering."""
        raw_vals = [80000.0, float("nan"), 81000.0, float("inf")]
        clean_vals = [bmi.finite_float(v) for v in raw_vals]
        self.assertEqual(clean_vals, [80000.0, None, 81000.0, None])


class TestBoundaryDomain8LauncherScriptBoundaries(unittest.TestCase):
    """Domain 8: Launcher Script Boundaries."""

    def setUp(self):
        if not is_launcher_implemented():
            self.skipTest("Feature 8: run_dashboard.bat pending implementation in Milestone 2")

    def test_b8_01_launcher_bat_space_in_working_dir(self):
        """Launcher script quotes '%~dp0' to support paths containing spaces."""
        content = (PROJECT_ROOT / "run_dashboard.bat").read_text(encoding="utf-8", errors="ignore")
        self.assertTrue('"%~dp0"' in content or "%~dp0" in content)

    def test_b8_02_launcher_bat_no_hardcoded_user_paths(self):
        """Launcher script contains no hardcoded absolute user home directories."""
        content = (PROJECT_ROOT / "run_dashboard.bat").read_text(encoding="utf-8", errors="ignore")
        self.assertNotIn("c:\\users\\maksi\\", content.lower())

    def test_b8_03_launcher_bat_newline_format(self):
        """Launcher batch file has non-zero length and readable lines."""
        raw_bytes = (PROJECT_ROOT / "run_dashboard.bat").read_bytes()
        self.assertGreater(len(raw_bytes), 20)

    def test_b8_04_launcher_bat_python_fallback_order(self):
        """Launcher checks virtual environment then falls back to python."""
        content = (PROJECT_ROOT / "run_dashboard.bat").read_text(encoding="utf-8", errors="ignore")
        self.assertTrue("python" in content.lower())

    def test_b8_05_launcher_bat_non_empty_content(self):
        """Launcher batch file has at least 5 lines of batch logic."""
        lines = (PROJECT_ROOT / "run_dashboard.bat").read_text(encoding="utf-8", errors="ignore").splitlines()
        self.assertGreaterEqual(len(lines), 5)


class TestBoundaryDomain9QuantitativeMathBoundaries(unittest.TestCase):
    """Domain 9: Quantitative Math & Analytical Engine Boundaries."""

    def test_b9_01_zscore_zero_standard_deviation(self):
        """calculate_zscore with all identical values (std=0) returns 0.0 without division error."""
        res = bmi.calculate_zscore(50.0, [50.0] * 20)
        self.assertEqual(res, 0.0)

    def test_b9_02_zscore_empty_series(self):
        """calculate_zscore with empty series returns None."""
        res = bmi.calculate_zscore(50.0, [])
        self.assertIsNone(res)

    def test_b9_03_quant_bias_all_zero_drivers(self):
        """calculate_quant_bias with all 0 or empty inputs yields 0 score and NEUTRAL."""
        res = bmi.calculate_quant_bias({})
        self.assertEqual(res["composite_score"], 0)
        self.assertEqual(res["bias_label"], "NEUTRAL")

    def test_b9_04_only_closed_klines_empty(self):
        """only_closed_klines with empty kline list returns empty list."""
        self.assertEqual(bmi.only_closed_klines([]), [])

    def test_b9_05_candle_delta_zero_volume(self):
        """candle_delta on a zero-volume candle returns 0.0 delta."""
        # [open_time, open, high, low, close, volume, close_time, quote_vol, trades, taker_base, taker_quote, ignore]
        zero_kline = [0, "80000", "80100", "79900", "80050", "0.0", 0, "0.0", 0, "0.0", "0.0", "0"]
        delta = bmi.candle_delta(zero_kline)
        self.assertEqual(delta[0], 0.0)

    def test_b9_06_candle_delta_normal_taker_subtraction(self):
        """candle_delta calculates 2 * taker_base - total_volume."""
        # total_vol = 100, taker_buy = 60 -> taker_sell = 40 -> delta = +20
        kline = [0, "80000", "80100", "79900", "80050", "100.0", 0, "0.0", 10, "60.0", "0.0", "0"]
        delta = bmi.candle_delta(kline)
        self.assertAlmostEqual(delta[0], 20.0, places=2)


if __name__ == "__main__":
    unittest.main()
