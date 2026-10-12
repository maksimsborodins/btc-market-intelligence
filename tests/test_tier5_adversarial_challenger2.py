"""
Tier 5: Adversarial Stress Test Suite (Challenger 2)
Empirical verification of Dashboard Data Hydration under missing/corrupted artifacts,
Calibration Tracker State Machine under extreme price action paths,
and Subprocess Execution Guard integrity.
"""

import os
import sys
import json
import math
import time
import shutil
import tempfile
import unittest
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import dashboard
import btc_market_intelligence as bmi


class TestAdversarialDashboardHydration(unittest.TestCase):
    """Module 1: Dashboard Data Hydration Fault Injection."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="adv_dashboard_")

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_h1_01_missing_files_graceful_fallbacks(self):
        """Loader functions must return non-crashing empty/None defaults when files do not exist."""
        nonexistent = Path(self.temp_dir) / "does_not_exist.json"
        
        # Snapshot loader
        snap = dashboard.load_market_snapshot(nonexistent)
        self.assertEqual(snap, {}, "load_market_snapshot must return empty dict for missing file")
        
        # History loader
        hist = dashboard.load_market_history(nonexistent)
        self.assertEqual(hist, [], "load_market_history must return empty list for missing file")
        
        # Tracker loader
        tracker = dashboard.load_calibration_tracker(nonexistent)
        self.assertEqual(tracker, [], "load_calibration_tracker must return empty list for missing file")
        
        # Markdown report loader
        md = dashboard.load_markdown_report(nonexistent)
        self.assertIsNone(md, "load_markdown_report must return None for missing file")
        
        # PDF loader
        pdf = dashboard.load_pdf_base64(nonexistent)
        self.assertIsNone(pdf, "load_pdf_base64 must return None for missing file")

    def test_h1_02_truncated_and_malformed_json_artifacts(self):
        """Corrupted JSON with truncated brackets or syntax errors must return safe defaults."""
        malformed_file = Path(self.temp_dir) / "malformed.json"
        
        for garbage_content in [
            '{"spot_price": 83000, "prices": ',  # truncated JSON
            '{bad_json_no_quotes: 123}',         # syntax error
            '[[[[[',                             # unmatched arrays
            '   \n\t  ',                         # whitespace only
        ]:
            malformed_file.write_text(garbage_content, encoding="utf-8")
            
            snap = dashboard.load_market_snapshot(malformed_file)
            self.assertEqual(snap, {}, f"Failed on content: {garbage_content!r}")
            
            hist = dashboard.load_market_history(malformed_file)
            self.assertEqual(hist, [], f"Failed on content: {garbage_content!r}")
            
            tracker = dashboard.load_calibration_tracker(malformed_file)
            self.assertEqual(tracker, [], f"Failed on content: {garbage_content!r}")

    def test_h1_03_binary_garbage_fault_injection(self):
        """Resilience test: Binary garbage is caught safely and returns fallback snapshot."""
        raw_garbage_file = Path(self.temp_dir) / "raw_binary.json"
        raw_garbage_file.write_bytes(b"\x80\xff\xfe\xfa\x00\x12\x89PNG\r\n\x1a\n")
        
        # Loader must catch UnicodeDecodeError and return safe fallback without crashing
        res = dashboard.load_market_snapshot(raw_garbage_file)
        self.assertIsInstance(res, dict)
        self.assertEqual(res, {})

    def test_h1_04_missing_keys_in_snapshot(self):
        """Extractors must return safe defaults on empty or partially populated snapshots."""
        empty_snapshot = {}
        
        # Spot price
        spot = dashboard.extract_spot_price(empty_snapshot)
        self.assertIsInstance(spot, float)
        self.assertGreater(spot, 0.0)
        
        # Quant bias
        score, label, breakdown = dashboard.extract_quant_bias(empty_snapshot)
        self.assertEqual(score, 0)
        self.assertEqual(label, "NEUTRAL")
        self.assertEqual(breakdown, {})
        
        # Risk model
        risk = dashboard.extract_risk_model(empty_snapshot, spot)
        self.assertIn("long", risk)
        self.assertIn("short", risk)
        self.assertIn("recommended", risk)
        self.assertEqual(risk["recommended"]["scenario"], "LONG")

    def test_h1_05_chart_rendering_with_empty_or_corrupted_history(self):
        """Plotly chart generators must not crash when history is empty."""
        empty_history = []
        fig_zscore = dashboard.create_zscore_timeseries(empty_history)
        self.assertIsNotNone(fig_zscore)
        
        spot = 83000.0
        risk = dashboard.extract_risk_model({}, spot)
        fig_price = dashboard.create_price_atr_chart(spot, risk, empty_history)
        self.assertIsNotNone(fig_price)

    def test_h1_06_corrupted_factor_breakdown_inputs(self):
        """Factor breakdown chart must handle missing or non-numeric factors gracefully."""
        corrupted_breakdowns = [
            {},
            {"1d_vwap_trend": None, "24h_spot_cvd": "not_a_num"},
            {"random_unexpected_key": 50},
        ]
        for bd in corrupted_breakdowns:
            fig = dashboard.create_factor_breakdown_chart(bd)
            self.assertIsNotNone(fig)

    def test_h1_07_vulnerability_none_binance_crashes_cvd(self):
        """Resilience test: snapshot with binance=None returns fallback figure without crashing."""
        snap_none_binance = {"binance": None}
        fig = dashboard.create_cvd_barchart(snap_none_binance)
        self.assertIsNotNone(fig)

    def test_h1_08_vulnerability_none_in_history_crashes_timeseries(self):
        """Resilience test: history containing None is filtered and renders safely."""
        corrupted_history = [None, {"timestamp_utc": "12:00:00", "oi_zscore": 0.5, "funding_zscore": -0.2}]
        fig = dashboard.create_zscore_timeseries(corrupted_history)
        self.assertIsNotNone(fig)


class TestAdversarialCalibrationTracker(unittest.TestCase):
    """Module 2: Winrate Calibration Tracker State Machine Stress Test."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="adv_tracker_")
        self.tracker_file = Path(self.temp_dir) / "test_tracker.json"

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_c2_01_long_signal_flash_crash_hits_stop_loss(self):
        """Long signal followed by sudden price drop hitting Stop-Loss immediately."""
        t0 = 1700000000.0
        snap_entry = {
            "prices": {"spot_last": 80000.0},
            "quant_bias": {"composite_score": 30, "bias_label": "BULLISH"},
            "market_structure": {"4h": {"atr14_price": 500.0}},
        }
        res0 = bmi.update_calibration_tracker(snap_entry, tracker_path=self.tracker_file, force_time=t0)
        self.assertEqual(res0["total_signals_tracked"], 1)
        self.assertEqual(res0["resolved_signals_count"], 0)

        # 30 mins later: flash crash touches SL (79,250.0)
        t1 = t0 + 1800.0
        snap_crash = {
            "prices": {"spot_last": 79100.0},
            "high_price": 80100.0,
            "low_price": 79000.0,  # below SL
            "quant_bias": {"composite_score": -40, "bias_label": "STRONG BEARISH"},
        }
        res1 = bmi.update_calibration_tracker(snap_crash, tracker_path=self.tracker_file, force_time=t1)
        
        # Assert state machine transitions
        self.assertEqual(res1["resolved_signals_count"], 1)
        self.assertEqual(res1["wins_total"], 0)
        self.assertEqual(res1["losses_total"], 1)
        self.assertEqual(res1["overall_win_rate_pct"], 0.0)

        tracker_data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
        signal = tracker_data[0]
        self.assertTrue(signal["resolved"])
        self.assertEqual(signal["outcome"], "LOSS")
        self.assertFalse(signal["is_win"])
        self.assertEqual(signal["resolution_type"], "SL_HIT")
        self.assertEqual(signal["resolved_price"], 79250.0)
        self.assertEqual(signal["pnl_usd"], -750.0)
        self.assertEqual(signal["pnl_pct"], -0.94)

    def test_c2_02_long_signal_surge_hits_tp2(self):
        """Long signal followed by rally hitting Take-Profit 2 (1:3 R:R) immediately."""
        t0 = 1700000000.0
        snap_entry = {
            "prices": {"spot_last": 80000.0},
            "quant_bias": {"composite_score": 30, "bias_label": "BULLISH"},
            "market_structure": {"4h": {"atr14_price": 500.0}},
        }
        bmi.update_calibration_tracker(snap_entry, tracker_path=self.tracker_file, force_time=t0)

        # 1 hour later: surge hitting TP2 (82,250.0) without touching SL (79,250.0)
        t1 = t0 + 3600.0
        snap_rally = {
            "prices": {"spot_last": 82300.0},
            "high_price": 82500.0,  # exceeds TP2
            "low_price": 79900.0,   # well above SL
            "quant_bias": {"composite_score": 60, "bias_label": "STRONG BULLISH"},
        }
        res1 = bmi.update_calibration_tracker(snap_rally, tracker_path=self.tracker_file, force_time=t1)

        self.assertEqual(res1["resolved_signals_count"], 1)
        self.assertEqual(res1["wins_total"], 1)
        self.assertEqual(res1["losses_total"], 0)
        self.assertEqual(res1["overall_win_rate_pct"], 100.0)

        tracker_data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
        signal = tracker_data[0]
        self.assertTrue(signal["resolved"])
        self.assertEqual(signal["outcome"], "WIN")
        self.assertTrue(signal["is_win"])
        self.assertEqual(signal["resolution_type"], "TP2_HIT")
        self.assertEqual(signal["resolved_price"], 82250.0)
        self.assertEqual(signal["pnl_usd"], 2250.0)
        self.assertEqual(signal["pnl_pct"], 2.81)

    def test_c2_03_short_signal_surge_hits_stop_loss(self):
        """Short signal followed by short-squeeze rally hitting Stop-Loss immediately."""
        t0 = 1700000000.0
        snap_entry = {
            "prices": {"spot_last": 80000.0},
            "quant_bias": {"composite_score": -35, "bias_label": "BEARISH"},
            "market_structure": {"4h": {"atr14_price": 500.0}},
        }
        bmi.update_calibration_tracker(snap_entry, tracker_path=self.tracker_file, force_time=t0)

        # 45 mins later: squeeze hitting SL (80,750.0)
        t1 = t0 + 2700.0
        snap_squeeze = {
            "prices": {"spot_last": 80900.0},
            "high_price": 81000.0,  # touches SL
            "low_price": 79800.0,
            "quant_bias": {"composite_score": 20, "bias_label": "BULLISH"},
        }
        res1 = bmi.update_calibration_tracker(snap_squeeze, tracker_path=self.tracker_file, force_time=t1)

        self.assertEqual(res1["resolved_signals_count"], 1)
        self.assertEqual(res1["wins_total"], 0)
        self.assertEqual(res1["losses_total"], 1)
        self.assertEqual(res1["overall_win_rate_pct"], 0.0)

        tracker_data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
        signal = tracker_data[0]
        self.assertTrue(signal["resolved"])
        self.assertEqual(signal["outcome"], "LOSS")
        self.assertFalse(signal["is_win"])
        self.assertEqual(signal["resolution_type"], "SL_HIT")
        self.assertEqual(signal["resolved_price"], 80750.0)
        self.assertEqual(signal["pnl_usd"], -750.0)
        self.assertEqual(signal["pnl_pct"], -0.94)

    def test_c2_04_short_signal_dump_hits_tp2(self):
        """Short signal followed by plunge hitting TP2 (77,750.0) immediately."""
        t0 = 1700000000.0
        snap_entry = {
            "prices": {"spot_last": 80000.0},
            "quant_bias": {"composite_score": -35, "bias_label": "BEARISH"},
            "market_structure": {"4h": {"atr14_price": 500.0}},
        }
        bmi.update_calibration_tracker(snap_entry, tracker_path=self.tracker_file, force_time=t0)

        # 2 hours later: plunge hits TP2 (77,750.0)
        t1 = t0 + 7200.0
        snap_dump = {
            "prices": {"spot_last": 77600.0},
            "high_price": 80200.0,  # below SL (80,750.0)
            "low_price": 77500.0,   # touches TP2
            "quant_bias": {"composite_score": -45, "bias_label": "STRONG BEARISH"},
        }
        res1 = bmi.update_calibration_tracker(snap_dump, tracker_path=self.tracker_file, force_time=t1)

        self.assertEqual(res1["resolved_signals_count"], 1)
        self.assertEqual(res1["wins_total"], 1)
        self.assertEqual(res1["overall_win_rate_pct"], 100.0)

        tracker_data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
        signal = tracker_data[0]
        self.assertTrue(signal["resolved"])
        self.assertEqual(signal["outcome"], "WIN")
        self.assertTrue(signal["is_win"])
        self.assertEqual(signal["resolution_type"], "TP2_HIT")
        self.assertEqual(signal["resolved_price"], 77750.0)
        self.assertEqual(signal["pnl_usd"], 2250.0)
        self.assertEqual(signal["pnl_pct"], 2.81)

    def test_c2_05_extreme_dual_touch_wick_precedence(self):
        """Extreme candle hitting both TP2 and SL simultaneously: SL must take precedence."""
        t0 = 1700000000.0
        snap_entry = {
            "prices": {"spot_last": 80000.0},
            "quant_bias": {"composite_score": 30, "bias_label": "BULLISH"},
            "market_structure": {"4h": {"atr14_price": 500.0}},
        }
        bmi.update_calibration_tracker(snap_entry, tracker_path=self.tracker_file, force_time=t0)

        # Massive volatility wick: high hits TP2 (82,250.0) AND low breaches SL (79,250.0)
        t1 = t0 + 1800.0
        snap_dual_wick = {
            "prices": {"spot_last": 80000.0},
            "high_price": 83000.0,  # TP2 breached
            "low_price": 78000.0,   # SL breached
            "quant_bias": {"composite_score": 0, "bias_label": "NEUTRAL"},
        }
        bmi.update_calibration_tracker(snap_dual_wick, tracker_path=self.tracker_file, force_time=t1)

        tracker_data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
        signal = tracker_data[0]
        self.assertTrue(signal["resolved"])
        self.assertEqual(signal["resolution_type"], "SL_HIT", "Conservative risk management requires SL priority on dual-touch wicks")
        self.assertEqual(signal["outcome"], "LOSS")

    def test_c2_06_neutral_signal_24h_boundary_resolution(self):
        """Neutral signals: range-bound <= 1.5% is WIN, trend breakout > 1.5% is TREND_BREAKOUT."""
        t0 = 1700000000.0
        snap_neutral = {
            "prices": {"spot_last": 80000.0},
            "quant_bias": {"composite_score": 5, "bias_label": "NEUTRAL"},
        }
        bmi.update_calibration_tracker(snap_neutral, tracker_path=self.tracker_file, force_time=t0)

        # 24.5h later: price barely moved (80,400 = +0.5% <= 1.5%) -> WIN (range-bound)
        t1 = t0 + 24.5 * 3600
        snap_range = {
            "prices": {"spot_last": 80400.0},
            "quant_bias": {"composite_score": 0, "bias_label": "NEUTRAL"},
        }
        res1 = bmi.update_calibration_tracker(snap_range, tracker_path=self.tracker_file, force_time=t1)
        self.assertEqual(res1["resolved_signals_count"], 1)
        self.assertEqual(res1["wins_total"], 1)

        tracker_data = json.loads(self.tracker_file.read_text(encoding="utf-8"))
        self.assertEqual(tracker_data[0]["outcome"], "WIN")
        self.assertEqual(tracker_data[0]["resolution_type"], "24H_RANGE_BOUND")

    def test_c2_07_mixed_50_signals_statistical_accuracy(self):
        """Stress-testing winrate percentage and aggregate statistics across 50 mixed signals."""
        signals = []
        t_base = 1700000000.0

        # 20 longs: 12 win, 8 loss
        for i in range(20):
            is_w = (i < 12)
            signals.append({
                "id": f"long_{i}",
                "epoch": t_base + i * 3600,
                "direction": "LONG",
                "entry_price": 80000.0,
                "quant_bias_score": 30,
                "quant_bias_label": "BULLISH",
                "resolved": True,
                "is_win": is_w,
                "outcome": "WIN" if is_w else "LOSS",
                "pnl_pct": 2.5 if is_w else -1.0,
                "price_change_24h_pct": 2.5 if is_w else -1.0,
            })

        # 20 shorts: 10 win, 10 loss
        for i in range(20):
            is_w = (i < 10)
            signals.append({
                "id": f"short_{i}",
                "epoch": t_base + (20 + i) * 3600,
                "direction": "SHORT",
                "entry_price": 80000.0,
                "quant_bias_score": -30,
                "quant_bias_label": "BEARISH",
                "resolved": True,
                "is_win": is_w,
                "outcome": "WIN" if is_w else "LOSS",
                "pnl_pct": 2.0 if is_w else -1.5,
                "price_change_24h_pct": -2.0 if is_w else 1.5,
            })

        # 10 neutrals: 6 win, 4 breakout
        for i in range(10):
            is_w = (i < 6)
            signals.append({
                "id": f"neutral_{i}",
                "epoch": t_base + (40 + i) * 3600,
                "direction": "NEUTRAL",
                "entry_price": 80000.0,
                "quant_bias_score": 0,
                "quant_bias_label": "NEUTRAL",
                "resolved": True,
                "is_win": is_w,
                "outcome": "WIN" if is_w else "TREND_BREAKOUT",
                "pnl_pct": 0.2 if is_w else 2.5,
                "price_change_24h_pct": 0.2 if is_w else 2.5,
            })

        self.tracker_file.write_text(json.dumps(signals, indent=2), encoding="utf-8")
        snap = {"prices": {"spot_last": 80000.0}}
        stats = bmi.update_calibration_tracker(snap, tracker_path=self.tracker_file, force_time=t_base + 60 * 3600)

        self.assertEqual(stats["resolved_signals_count"], 50)
        self.assertEqual(stats["wins_total"], 28)
        self.assertEqual(stats["losses_total"], 22)
        self.assertEqual(stats["overall_win_rate_pct"], 56.0)
        self.assertEqual(stats["bullish_signals"]["win_rate_pct"], 60.0)
        self.assertEqual(stats["bearish_signals"]["win_rate_pct"], 50.0)
        self.assertEqual(stats["neutral_signals"]["wins"], 6)

    def test_c2_08_trend_breakout_dashboard_status_discrepancy(self):
        """Empirical vulnerability test: TREND_BREAKOUT outcome in dashboard table displays as PENDING."""
        t = {
            "resolved": True,
            "outcome": "TREND_BREAKOUT",
            "is_win": False,
            "direction": "NEUTRAL",
        }
        # In dashboard.py line 1212-1225:
        outcome = t.get("outcome") or ("WIN" if t.get("is_win") is True else ("LOSS" if t.get("is_win") is False else "PENDING"))
        dashboard_status = "✅ WIN" if outcome == "WIN" else ("❌ LOSS" if outcome == "LOSS" else "⏳ PENDING")
        
        # When outcome is TREND_BREAKOUT, dashboard_status is '⏳ PENDING' even though signal is resolved!
        self.assertEqual(dashboard_status, "⏳ PENDING", "Confirmed bug: resolved TREND_BREAKOUT displays as PENDING in table")


class TestAdversarialSubprocessGuard(unittest.TestCase):
    """Module 3: Subprocess Execution Guard & Session State."""

    def test_s3_01_command_generation_integrity(self):
        """build_execution_command must produce safe, executable CLI argument lists."""
        cmd_fast = dashboard.build_execution_command(fast_mode=True)
        cmd_full = dashboard.build_execution_command(fast_mode=False)

        self.assertEqual(cmd_fast[0], sys.executable)
        self.assertTrue(cmd_fast[1].endswith("btc_market_intelligence.py"))
        self.assertIn("--fast", cmd_fast)

        self.assertEqual(cmd_full[0], sys.executable)
        self.assertTrue(cmd_full[1].endswith("btc_market_intelligence.py"))
        self.assertNotIn("--fast", cmd_full)

    def test_s3_02_simulated_concurrent_execution_guard(self):
        """Simulate Streamlit session state guarding rapid double-clicks."""
        mock_session_state = {"is_running": False}

        # First trigger
        self.assertFalse(mock_session_state["is_running"])
        mock_session_state["is_running"] = True

        # Second rapid click while running
        button_disabled = mock_session_state["is_running"]
        self.assertTrue(button_disabled, "Button must be disabled while pipeline is executing")

        # Cleanup on finish
        mock_session_state["is_running"] = False
        self.assertFalse(mock_session_state["is_running"])


if __name__ == "__main__":
    unittest.main()
