"""
Unit and Boundary Test Suite for quant_enhancements.py
=====================================================
Validates:
1. Market Regime Detection & Adaptive Weights (High Vol Squeeze, Bull/Bear Trend, Consolidation, Normal)
2. Quant Bias computation across regimes (bounds [-100, +100], mathematical symmetry, edge cases)
3. Liquidity-Aware Dynamic Stops & Spread/Fee Adjusted R:R (clustering, friction compensation, null safety)
4. Calibration Performance Metrics (EV, Sharpe, Sortino, Profit Factor, MDD, Kelly sizing, zero-division safety)
"""

import math
import unittest
from pathlib import Path

import quant_enhancements as qe


class TestMarketRegimeDetection(unittest.TestCase):
    """Test Suite for detect_market_regime & calculate_regime_adaptive_bias."""

    def test_empty_or_none_metrics(self):
        """Empty or invalid metrics fall back safely to BALANCED_NORMAL."""
        res_empty = qe.detect_market_regime({})
        self.assertEqual(res_empty["regime"], qe.REGIME_BALANCED_NORMAL)
        self.assertEqual(sum(res_empty["weights"].values()), 100.0)

        bias_empty = qe.calculate_regime_adaptive_bias({})
        self.assertEqual(bias_empty["composite_score"], 0)
        self.assertEqual(bias_empty["bias_label"], "NEUTRAL")

    def test_high_vol_squeeze_detection(self):
        """Extreme OI Z-score and detrended funding trigger HIGH_VOL_SQUEEZE."""
        metrics = {
            "statistical_z_scores": {"oi_zscore": 2.4},
            "derivatives": {"current_funding_rate_pct": 0.025},  # dev = +0.015%
            "market_structure": {"4h": {"atr14_pct": 2.1}},
        }
        res = qe.detect_market_regime(metrics)
        self.assertEqual(res["regime"], qe.REGIME_HIGH_VOL_SQUEEZE)
        self.assertGreaterEqual(res["weights"]["oi_squeeze_risk"], 25.0)
        self.assertEqual(sum(res["weights"].values()), 100.0)

        # Test adaptive scoring under High Vol Squeeze
        bias = qe.calculate_regime_adaptive_bias(metrics)
        # Extreme positive funding + extreme positive OI -> Long crowd squeeze risk -> points deducted
        self.assertLess(bias["breakdown"].get("oi_squeeze_risk", 0), 0)
        self.assertIn(bias["bias_label"], ("BEARISH", "STRONG BEARISH"))

    def test_trending_bull_detection(self):
        """HH_HL uptrend with positive VWAP divergence triggers TRENDING_BULL."""
        metrics = {
            "market_structure": {
                "4h": {"swing_structure_label": "HH_HL_uptrend", "close_vs_rolling_vwap20_pct": 1.2},
                "1d": {"close_vs_rolling_vwap20_pct": 1.5},
            },
            "spot_taker_delta": {"24h": {"delta_btc": 650.0}},
            "orderbook_depth": {"spot": {"bid_vs_ask_ratio": 1.4}},
        }
        res = qe.detect_market_regime(metrics)
        self.assertEqual(res["regime"], qe.REGIME_TRENDING_BULL)
        self.assertEqual(res["weights"]["24h_spot_cvd"], 30.0)
        self.assertEqual(sum(res["weights"].values()), 100.0)

        bias = qe.calculate_regime_adaptive_bias(metrics)
        self.assertGreater(bias["composite_score"], 35)
        self.assertIn(bias["bias_label"], ("BULLISH", "STRONG BULLISH"))

    def test_trending_bear_detection(self):
        """LH_LL downtrend with negative VWAP triggers TRENDING_BEAR."""
        metrics = {
            "market_structure": {
                "4h": {"swing_structure_label": "LH_LL_downtrend", "close_vs_rolling_vwap20_pct": -1.2},
                "1d": {"close_vs_rolling_vwap20_pct": -1.5},
            },
            "spot_taker_delta": {"24h": {"delta_btc": -650.0}},
        }
        res = qe.detect_market_regime(metrics)
        self.assertEqual(res["regime"], qe.REGIME_TRENDING_BEAR)
        bias = qe.calculate_regime_adaptive_bias(metrics)
        self.assertLess(bias["composite_score"], -35)
        self.assertIn(bias["bias_label"], ("BEARISH", "STRONG BEARISH"))

    def test_low_vol_consolidation_detection(self):
        """Low ATR % and compressed Bollinger bandwidth trigger LOW_VOL_CONSOLIDATION."""
        metrics = {
            "market_structure": {
                "4h": {
                    "atr14_pct": 0.55,
                    "swing_structure_label": "range_or_transition",
                    "bollinger_20_upper": 83200.0,
                    "bollinger_20_lower": 82800.0,
                    "bollinger_20_mid": 83000.0,  # Bandwidth = 400 / 83000 = 0.0048 (0.48%)
                }
            },
            "statistical_z_scores": {"oi_zscore": 0.2},
            "orderbook_depth": {"spot": {"bid_vs_ask_ratio": 1.8}, "futures": {"bid_vs_ask_ratio": 1.6}},
        }
        res = qe.detect_market_regime(metrics)
        self.assertEqual(res["regime"], qe.REGIME_LOW_VOL_CONSOLIDATION)
        # In consolidation, order book weights are boosted
        self.assertEqual(res["weights"]["spot_orderbook_imbalance"], 30.0)
        self.assertEqual(res["weights"]["futures_orderbook_imbalance"], 25.0)

        bias = qe.calculate_regime_adaptive_bias(metrics)
        self.assertGreater(bias["breakdown"]["spot_orderbook_imbalance"], 20)

    def test_score_boundary_invariance(self):
        """Score must never exceed [-100, +100] across any extreme input permutation."""
        extreme_bull = {
            "market_structure": {"1d": {"close_vs_rolling_vwap20_pct": 100.0}},
            "spot_taker_delta": {"24h": {"delta_btc": 10000.0}},
            "orderbook_depth": {"spot": {"bid_vs_ask_ratio": 50.0}, "futures": {"bid_vs_ask_ratio": 50.0}},
            "divergence_engine": {"24h_divergence": {"bias_contribution": 100}},
            "statistical_z_scores": {"oi_zscore": 3.0},
            "derivatives": {"current_funding_rate_pct": -0.05},
        }
        res_bull = qe.calculate_regime_adaptive_bias(extreme_bull)
        self.assertLessEqual(res_bull["composite_score"], 100)
        self.assertEqual(res_bull["bias_label"], "STRONG BULLISH")

        extreme_bear = {
            "market_structure": {"1d": {"close_vs_rolling_vwap20_pct": -100.0}},
            "spot_taker_delta": {"24h": {"delta_btc": -10000.0}},
            "orderbook_depth": {"spot": {"bid_vs_ask_ratio": 0.01}, "futures": {"bid_vs_ask_ratio": 0.01}},
            "divergence_engine": {"24h_divergence": {"bias_contribution": -100}},
            "statistical_z_scores": {"oi_zscore": 3.0},
            "derivatives": {"current_funding_rate_pct": 0.05},
        }
        res_bear = qe.calculate_regime_adaptive_bias(extreme_bear)
        self.assertGreaterEqual(res_bear["composite_score"], -100)
        self.assertEqual(res_bear["bias_label"], "STRONG BEARISH")


class TestLiquidityAwareDynamicStops(unittest.TestCase):
    """Test Suite for calculate_liquidity_aware_stops."""

    def test_baseline_exactness(self):
        """With standard inputs and no liquidity wall, matches baseline 1.5x ATR contract."""
        sp = 83056.16
        atr = 476.16
        res = qe.calculate_liquidity_aware_stops(sp, atr, quant_bias_score=30)

        # Baseline contract assertions
        self.assertEqual(res["buffer"], 714.24)
        self.assertEqual(res["direction"], "LONG")
        self.assertEqual(res["long"]["stop_loss"], 82341.92)
        self.assertEqual(res["long"]["tp1_rr2"], 84484.64)
        self.assertEqual(res["long"]["tp2_rr3"], 85198.88)
        self.assertEqual(res["recommended"]["stop_loss"], 82341.92)

    def test_zero_and_negative_boundaries(self):
        """Handles non-positive spot price or ATR gracefully without exception."""
        res_zero = qe.calculate_liquidity_aware_stops(0.0, 0.0)
        self.assertEqual(res_zero["buffer"], 0.0)
        self.assertEqual(res_zero["direction"], "NEUTRAL")
        self.assertEqual(res_zero["friction_analysis"]["effective_rr_tp1"], 0.0)

        res_neg = qe.calculate_liquidity_aware_stops(-100.0, -10.0)
        self.assertEqual(res_neg["buffer"], 0.0)

    def test_orderbook_liquidity_wall_adjustment(self):
        """Strong orderbook bid depth shifts long stop safely behind the wall."""
        sp = 83000.0
        atr = 500.0
        # Buffer = 1.5 * 500 = 750. Normal SL = 82250.
        ob_depth = {"spot": {"bid_vs_ask_ratio": 1.6}}  # Strong bid support wall
        res = qe.calculate_liquidity_aware_stops(sp, atr, quant_bias_score=25, orderbook_depth=ob_depth)

        liq = res["liquidity_adjusted"]
        self.assertTrue(liq["wall_info"]["wall_detected"])
        self.assertGreater(liq["adjusted_buffer"], res["buffer"])
        # Stop loss is widened to sit safely behind support wall
        self.assertLess(liq["long_sl"], res["long"]["stop_loss"])

    def test_friction_and_effective_rr(self):
        """Calculates true friction and reduced effective R:R accurately."""
        sp = 80000.0
        atr = 400.0  # Buffer = 600 USD
        spread = 8.0  # $8 spread
        fee_pct = 0.0005  # 0.05% taker -> 2 * 0.0005 * 80000 = $80 round-trip fee
        # Total friction = 8 + 80 = $88

        res = qe.calculate_liquidity_aware_stops(
            sp, atr, quant_bias_score=20, spread_usd=spread, taker_fee_pct=fee_pct
        )
        fric = res["friction_analysis"]
        self.assertEqual(fric["spread_usd"], 8.0)
        self.assertEqual(fric["round_trip_fee_usd"], 80.0)
        self.assertEqual(fric["total_friction_usd"], 88.0)

        # Realized effective R:R should be strictly less than nominal 2.0 and 3.0
        self.assertLess(fric["effective_rr_tp1"], 2.0)
        self.assertLess(fric["effective_rr_tp2"], 3.0)

        # Friction-compensated TP1 must be greater than nominal TP1
        comp = res["friction_compensated_targets"]
        self.assertGreater(comp["long_tp1"], res["long"]["tp1_rr2"])
        self.assertGreater(comp["long_tp2"], res["long"]["tp2_rr3"])


class TestCalibrationPerformanceMetrics(unittest.TestCase):
    """Test Suite for compute_calibration_performance_metrics."""

    def test_empty_tracker(self):
        """Empty trade list returns accumulating status gracefully."""
        res = qe.compute_calibration_performance_metrics([])
        self.assertEqual(res["status"], "ACCUMULATING_DATA")
        self.assertIsNone(res["expected_value_pct"])
        self.assertEqual(res["max_drawdown_pct"], 0.0)
        self.assertEqual(res["kelly_fraction"], 0.0)

    def test_all_losses(self):
        """All-loss sequence returns 0% win rate, negative EV, and zero Kelly fraction."""
        trades = [
            {"resolved": True, "is_win": False, "pnl_pct": -0.94, "pnl_usd": -778.0},
            {"resolved": True, "is_win": False, "pnl_pct": -1.02, "pnl_usd": -830.0},
        ]
        res = qe.compute_calibration_performance_metrics(trades)
        self.assertEqual(res["win_rate_pct"], 0.0)
        self.assertLess(res["expected_value_pct"], 0.0)
        self.assertEqual(res["profit_factor"], 0.0)
        self.assertEqual(res["kelly_fraction"], 0.0)
        self.assertLess(res["max_drawdown_pct"], 0.0)

    def test_all_wins(self):
        """All-win sequence returns 100% win rate, positive EV, and high profit factor."""
        trades = [
            {"resolved": True, "is_win": True, "pnl_pct": 2.1, "pnl_usd": 1600.0},
            {"resolved": True, "is_win": True, "pnl_pct": 3.0, "pnl_usd": 2400.0},
        ]
        res = qe.compute_calibration_performance_metrics(trades)
        self.assertEqual(res["win_rate_pct"], 100.0)
        self.assertGreater(res["expected_value_pct"], 0.0)
        self.assertEqual(res["profit_factor"], 999.0)  # Capped on zero loss
        self.assertGreater(res["kelly_fraction"], 0.0)

    def test_realistic_mixed_trades_statistics(self):
        """Validates realistic trade sequence EV, Sharpe, Drawdown, and Kelly sizing."""
        trades = [
            {"resolved": True, "is_win": True, "pnl_pct": 2.4, "pnl_usd": 1900.0, "direction": "LONG"},
            {"resolved": True, "is_win": True, "pnl_pct": 3.2, "pnl_usd": 2500.0, "direction": "LONG"},
            {"resolved": True, "is_win": False, "pnl_pct": -1.0, "pnl_usd": -800.0, "direction": "LONG"},
            {"resolved": True, "is_win": True, "pnl_pct": 1.8, "pnl_usd": 1400.0, "direction": "SHORT"},
            {"resolved": True, "is_win": False, "pnl_pct": -0.9, "pnl_usd": -720.0, "direction": "SHORT"},
        ]
        # 3 Wins: 2.4, 3.2, 1.8 -> Avg Win = 2.467%
        # 2 Losses: 1.0, 0.9 -> Avg Loss = 0.95%
        # Win Rate = 60.0%
        # Payoff Ratio = 2.467 / 0.95 = 2.597
        # EV = 0.6 * 2.467 - 0.4 * 0.95 = 1.480 - 0.380 = +1.10%
        res = qe.compute_calibration_performance_metrics(trades)
        self.assertEqual(res["total_signals_tracked"], 5)
        self.assertEqual(res["win_rate_pct"], 60.0)
        self.assertAlmostEqual(res["expected_value_pct"], 1.10, places=1)
        self.assertGreater(res["profit_factor"], 2.0)
        self.assertGreater(res["sharpe_ratio"], 0.0)
        self.assertGreater(res["kelly_fraction"], 0.3)
        self.assertEqual(res["half_kelly_fraction"], round(res["kelly_fraction"] / 2.0, 3))
        self.assertIn("long_signals", res["subgroups"])
        self.assertIn("short_signals", res["subgroups"])

    def test_actual_disk_tracker_file(self):
        """Runs on the repo's real quant_calibration_tracker.json cleanly."""
        tracker_path = Path(__file__).resolve().parent.parent / "quant_calibration_tracker.json"
        if tracker_path.exists():
            res = qe.compute_calibration_performance_metrics(tracker_path)
            self.assertIn("status", res)
            self.assertIn("readout", res)


if __name__ == "__main__":
    unittest.main()
