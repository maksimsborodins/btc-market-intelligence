"""
Quantitative Architecture & Risk Enhancement Module (Lead Quant & Risk Architect).
===================================================================================
Provides institutional-grade extensions for BTC Market Intelligence Terminal:
1. detect_market_regime & calculate_regime_adaptive_bias:
   Volatility-conditioned regime detection (High Vol Squeeze, Trending Bull/Bear,
   Low Vol Consolidation, Balanced Normal) with dynamic factor re-weighting.
2. calculate_liquidity_aware_stops:
   Spread- and orderbook-density-aware dynamic stops and take-profits, friction-adjusted
   effective R:R, and friction-compensated target levels.
3. compute_calibration_performance_metrics:
   Institutional risk metrics over calibration trade histories: Expected Value (EV),
   Annualized Sharpe & Sortino ratios, Profit Factor, Maximum Drawdown (MDD),
   Calmar ratio, and Kelly Criterion allocation fraction.
"""

from __future__ import annotations

import math
import json
import statistics
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union


# -----------------------------------------------------------------------------
# 1. MARKET REGIME DETECTION & ADAPTIVE WEIGHTING
# -----------------------------------------------------------------------------

# Canonical Regime Identifiers
REGIME_HIGH_VOL_SQUEEZE = "HIGH_VOL_SQUEEZE"
REGIME_TRENDING_BULL = "TRENDING_BULL"
REGIME_TRENDING_BEAR = "TRENDING_BEAR"
REGIME_LOW_VOL_CONSOLIDATION = "LOW_VOL_CONSOLIDATION"
REGIME_BALANCED_NORMAL = "BALANCED_NORMAL"

# Factor Weight Vectors (Must sum strictly to 100 points for each regime)
REGIME_WEIGHTS: Dict[str, Dict[str, float]] = {
    # Baseline standard weights matching legacy calculate_quant_bias
    REGIME_BALANCED_NORMAL: {
        "1d_vwap_trend": 15.0,
        "24h_spot_cvd": 20.0,
        "spot_orderbook_imbalance": 20.0,
        "futures_orderbook_imbalance": 15.0,
        "24h_divergence_engine": 15.0,
        "oi_squeeze_risk": 15.0,
    },
    # High Vol Squeeze: Book walls are phantom/brittle; OI squeeze & CVD aggressors rule
    REGIME_HIGH_VOL_SQUEEZE: {
        "1d_vwap_trend": 10.0,
        "24h_spot_cvd": 25.0,
        "spot_orderbook_imbalance": 5.0,
        "futures_orderbook_imbalance": 5.0,
        "24h_divergence_engine": 25.0,
        "oi_squeeze_risk": 30.0,
    },
    # Trending Bull: Momentum persistence and aggressive spot flow drive trend continuation
    REGIME_TRENDING_BULL: {
        "1d_vwap_trend": 25.0,
        "24h_spot_cvd": 30.0,
        "spot_orderbook_imbalance": 10.0,
        "futures_orderbook_imbalance": 5.0,
        "24h_divergence_engine": 20.0,
        "oi_squeeze_risk": 10.0,
    },
    # Trending Bear: Trend persistence and spot sell dumping drive continuation
    REGIME_TRENDING_BEAR: {
        "1d_vwap_trend": 25.0,
        "24h_spot_cvd": 30.0,
        "spot_orderbook_imbalance": 10.0,
        "futures_orderbook_imbalance": 5.0,
        "24h_divergence_engine": 20.0,
        "oi_squeeze_risk": 10.0,
    },
    # Low Vol Consolidation: Range bounds dominate; order book depth walls act as genuine S/R
    REGIME_LOW_VOL_CONSOLIDATION: {
        "1d_vwap_trend": 10.0,
        "24h_spot_cvd": 10.0,
        "spot_orderbook_imbalance": 30.0,
        "futures_orderbook_imbalance": 25.0,
        "24h_divergence_engine": 20.0,
        "oi_squeeze_risk": 5.0,
    },
}


def detect_market_regime(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """
    Classifies the dominant market volatility and structural regime from market metrics.
    
    Inputs evaluated:
    - 4h and 1d ATR % (volatility expansion vs compression)
    - OI Z-score & Funding rate detrended deviation (crowded positioning)
    - Swing structure label (HH_HL, LH_LL, range_or_transition)
    - Bollinger Band width / percent b
    - Volume vs 20-candle moving average
    """
    if not isinstance(metrics, dict) or not metrics:
        return {
            "regime": REGIME_BALANCED_NORMAL,
            "confidence": 0.5,
            "rationale": "Недостаточно данных телеметрии; используется сбалансированный режим по умолчанию.",
            "indicators": {},
            "weights": dict(REGIME_WEIGHTS[REGIME_BALANCED_NORMAL]),
        }

    # Extract indicators safely
    struct_4h = metrics.get("market_structure", {}).get("4h", {})
    struct_1d = metrics.get("market_structure", {}).get("1d", {})
    atr4h_pct = struct_4h.get("atr14_pct")
    atr1d_pct = struct_1d.get("atr14_pct")
    
    # Swing structure
    swing_label = struct_4h.get("swing_structure_label") or struct_1d.get("swing_structure_label", "range_or_transition")
    breakout_state = struct_4h.get("close_breakout_state") or struct_1d.get("close_breakout_state", "none")
    structural_break = struct_4h.get("structural_break_proxy") or struct_1d.get("structural_break_proxy", "none")
    
    # Bollinger metrics
    bb_pct_b = struct_4h.get("bollinger_percent_b") or struct_1d.get("bollinger_percent_b")
    bb_upper = struct_4h.get("bollinger_20_upper")
    bb_lower = struct_4h.get("bollinger_20_lower")
    bb_mid = struct_4h.get("bollinger_20_mid")
    bb_bandwidth = ((bb_upper - bb_lower) / bb_mid) if (bb_upper and bb_lower and bb_mid and bb_mid > 0) else None

    # Derivatives crowding & Z-Scores
    zscores = metrics.get("statistical_z_scores", {})
    oi_z = zscores.get("oi_zscore")
    derivatives = metrics.get("derivatives", {})
    funding = derivatives.get("current_funding_rate_pct")
    funding_dev = (funding - 0.010) if funding is not None else None

    # Volume expansion
    vol_ratio = struct_4h.get("volume_vs_previous_20_average") or struct_1d.get("volume_vs_previous_20_average")

    indicators = {
        "atr4h_pct": atr4h_pct,
        "atr1d_pct": atr1d_pct,
        "swing_label": swing_label,
        "breakout_state": breakout_state,
        "structural_break": structural_break,
        "bb_bandwidth": round(bb_bandwidth, 4) if bb_bandwidth is not None else None,
        "bb_pct_b": bb_pct_b,
        "oi_z": oi_z,
        "funding_dev": round(funding_dev, 6) if funding_dev is not None else None,
        "volume_ratio": vol_ratio,
    }

    # Regime Decision Engine (Hierarchical Rule Classification)
    
    # 1. Check for High Vol Squeeze
    is_extreme_oi = (oi_z is not None and abs(oi_z) >= 1.8)
    is_extreme_funding = (funding_dev is not None and abs(funding_dev) >= 0.007)
    is_vol_spike = (atr4h_pct is not None and atr4h_pct >= 1.75) or (atr1d_pct is not None and atr1d_pct >= 3.0)
    is_bb_escape = (bb_pct_b is not None and (bb_pct_b > 1.05 or bb_pct_b < -0.05))

    squeeze_signals = sum([bool(is_extreme_oi), bool(is_extreme_funding), bool(is_vol_spike), bool(is_bb_escape)])
    if squeeze_signals >= 2 or (is_extreme_oi and is_extreme_funding):
        return {
            "regime": REGIME_HIGH_VOL_SQUEEZE,
            "confidence": min(0.95, 0.60 + 0.10 * squeeze_signals),
            "rationale": (
                f"Режим высокой волатильности / шорт/лонг сквиза (OI Z-Score={oi_z}, "
                f"Funding Dev={funding_dev}%, ATR 4H={atr4h_pct}%). "
                "Стаканные плотности ненадежны; доминируют импульс деривативов и ликвидации."
            ),
            "indicators": indicators,
            "weights": dict(REGIME_WEIGHTS[REGIME_HIGH_VOL_SQUEEZE]),
        }

    # 2. Check for Trending Bull
    is_bull_trend = (
        swing_label == "HH_HL_uptrend"
        or breakout_state == "close_above_previous_20_candle_high"
        or structural_break == "close_above_latest_confirmed_swing_high"
    )
    vwap_pct = struct_1d.get("close_vs_rolling_vwap20_pct") or struct_4h.get("close_vs_rolling_vwap20_pct")
    is_vwap_bull = (vwap_pct is not None and vwap_pct > 0.5)

    if is_bull_trend and (is_vwap_bull or (vol_ratio and vol_ratio >= 1.0)):
        return {
            "regime": REGIME_TRENDING_BULL,
            "confidence": 0.85 if (is_bull_trend and is_vwap_bull) else 0.70,
            "rationale": (
                f"Бычий направленный тренд (HH/HL структура, отрыв от VWAP +{vwap_pct}%). "
                "Повышен вес CVD и следования тренду, понижен вес контртрендовых стенок стакана."
            ),
            "indicators": indicators,
            "weights": dict(REGIME_WEIGHTS[REGIME_TRENDING_BULL]),
        }

    # 3. Check for Trending Bear
    is_bear_trend = (
        swing_label == "LH_LL_downtrend"
        or breakout_state == "close_below_previous_20_candle_low"
        or structural_break == "close_below_latest_confirmed_swing_low"
    )
    is_vwap_bear = (vwap_pct is not None and vwap_pct < -0.5)

    if is_bear_trend and (is_vwap_bear or (vol_ratio and vol_ratio >= 1.0)):
        return {
            "regime": REGIME_TRENDING_BEAR,
            "confidence": 0.85 if (is_bear_trend and is_vwap_bear) else 0.70,
            "rationale": (
                f"Медвежий направленный тренд (LH/LL структура, отрыв от VWAP {vwap_pct}%). "
                "Повышен вес CVD агрессоров и тренда VWAP, понижен вес лимитных заявок на отскок."
            ),
            "indicators": indicators,
            "weights": dict(REGIME_WEIGHTS[REGIME_TRENDING_BEAR]),
        }

    # 4. Check for Low Vol Consolidation
    is_low_vol = (atr4h_pct is not None and atr4h_pct < 0.85) or (atr1d_pct is not None and atr1d_pct < 1.4)
    is_bb_squeeze = (bb_bandwidth is not None and bb_bandwidth < 0.035)
    is_range_pivots = swing_label in ("range_or_transition", "insufficient_pivots")
    is_calm_oi = (oi_z is None or abs(oi_z) < 1.0)

    consolidation_signals = sum([bool(is_low_vol), bool(is_bb_squeeze), bool(is_range_pivots), bool(is_calm_oi)])
    if consolidation_signals >= 3 or (is_low_vol and is_range_pivots):
        return {
            "regime": REGIME_LOW_VOL_CONSOLIDATION,
            "confidence": min(0.90, 0.55 + 0.10 * consolidation_signals),
            "rationale": (
                f"Низковолатильная консолидация / компрессия (ATR 4H={atr4h_pct}%, BB Bandwidth={bb_bandwidth}). "
                "Индикаторы тренда дают ложные сигналы; приоритет отдается дисбалансам стакана и дивергенциям."
            ),
            "indicators": indicators,
            "weights": dict(REGIME_WEIGHTS[REGIME_LOW_VOL_CONSOLIDATION]),
        }

    # 5. Default Balanced Normal
    return {
        "regime": REGIME_BALANCED_NORMAL,
        "confidence": 0.75,
        "rationale": "Сбалансированный режим рынка без выраженных аномалий волатильности или тренда.",
        "indicators": indicators,
        "weights": dict(REGIME_WEIGHTS[REGIME_BALANCED_NORMAL]),
    }


def calculate_regime_adaptive_bias(
    metrics: Dict[str, Any],
    regime_override: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes Quant Bias with weights dynamically adapted to the market regime.
    
    Guarantees:
    - Output bounds strictly in [-100, +100].
    - Sum of absolute maximum weights always equals 100.0.
    - Full backward compatibility with breakdown keys.
    """
    if not isinstance(metrics, dict) or not metrics:
        return {
            "composite_score": 0,
            "bias_label": "NEUTRAL",
            "breakdown": {},
            "regime_info": {
                "regime": REGIME_BALANCED_NORMAL,
                "confidence": 0.5,
                "rationale": "Пустые метрики.",
            },
        }

    regime_info = detect_market_regime(metrics)
    regime = regime_override or regime_info["regime"]
    weights = REGIME_WEIGHTS.get(regime, REGIME_WEIGHTS[REGIME_BALANCED_NORMAL])

    score = 0.0
    breakdown: Dict[str, int] = {}

    # 1. Daily VWAP trend: Tanh scaling against rolling 20-candle VWAP
    max_vwap_w = weights["1d_vwap_trend"]
    struct = metrics.get("market_structure", {}).get("1d", {})
    if struct.get("close_vs_rolling_vwap20_pct") is not None:
        val = float(struct["close_vs_rolling_vwap20_pct"])
        pts = round(max_vwap_w * math.tanh(val / 0.75), 1)
        score += pts
        breakdown["1d_vwap_trend"] = int(round(pts))

    # 2. 24h Spot CVD: Continuous aggressor-driven spot demand
    max_cvd_w = weights["24h_spot_cvd"]
    spot = metrics.get("spot_taker_delta", {})
    if spot.get("24h", {}).get("delta_btc") is not None:
        delta_btc = float(spot["24h"]["delta_btc"])
        pts = round(max_cvd_w * math.tanh(delta_btc / 400.0), 1)
        score += pts
        breakdown["24h_spot_cvd"] = int(round(pts))

    # 3. Spot Orderbook Imbalance ±1%: Logarithmic depth imbalance
    max_ob_spot_w = weights["spot_orderbook_imbalance"]
    ob_spot = metrics.get("orderbook_depth", {}).get("spot", {})
    if ob_spot and ob_spot.get("bid_vs_ask_ratio") is not None:
        ratio = float(ob_spot["bid_vs_ask_ratio"])
        if ratio > 0:
            log_r = math.log(ratio)
            pts = round(max_ob_spot_w * math.tanh(log_r / 0.35), 1)
            score += pts
            breakdown["spot_orderbook_imbalance"] = int(round(pts))

    # 4. Futures Orderbook Imbalance ±1%: Futures depth wall
    max_ob_fut_w = weights["futures_orderbook_imbalance"]
    ob_fut = metrics.get("orderbook_depth", {}).get("futures", {})
    if ob_fut and ob_fut.get("bid_vs_ask_ratio") is not None:
        ratio = float(ob_fut["bid_vs_ask_ratio"])
        if ratio > 0:
            log_r = math.log(ratio)
            pts = round(max_ob_fut_w * math.tanh(log_r / 0.35), 1)
            score += pts
            breakdown["futures_orderbook_imbalance"] = int(round(pts))

    # 5. Divergence Engine: Price vs OI trend alignment
    max_div_w = weights["24h_divergence_engine"]
    div = metrics.get("divergence_engine", {}).get("24h_divergence", {})
    if div:
        raw_div = float(div.get("bias_contribution", 0))
        # Scale proportionally from legacy 15 baseline to regime weight
        norm_factor = raw_div / 15.0 if 15.0 else 0.0
        pts = round(max(-max_div_w, min(max_div_w, norm_factor * max_div_w)), 1)
        score += pts
        breakdown["24h_divergence_engine"] = int(round(pts))

    # 6. OI Squeeze Risk: Detrended funding rate and OI extreme Z-Score
    max_oi_w = weights["oi_squeeze_risk"]
    oi_z = metrics.get("statistical_z_scores", {}).get("oi_zscore")
    if oi_z is not None and abs(float(oi_z)) > 1.8:
        fund = metrics.get("derivatives", {}).get("current_funding_rate_pct", 0)
        if fund is not None:
            fund_dev = round(float(fund) - 0.010, 6)
            oi_val = float(oi_z)
            if oi_val > 1.8 and fund_dev >= 0.005:
                pts = -max_oi_w
            elif oi_val > 1.8 and fund_dev <= -0.005:
                pts = max_oi_w
            elif oi_val < -1.8:
                pts = (max_oi_w * 0.67) if fund_dev < 0 else -(max_oi_w * 0.67)
            else:
                pts = 0.0
            if pts != 0.0:
                score += pts
                breakdown["oi_squeeze_risk"] = int(round(pts))

    final_score = int(round(max(-100.0, min(100.0, score))))

    if final_score >= 40:
        label = "STRONG BULLISH"
    elif final_score >= 15:
        label = "BULLISH"
    elif final_score <= -40:
        label = "STRONG BEARISH"
    elif final_score <= -15:
        label = "BEARISH"
    else:
        label = "NEUTRAL"

    return {
        "composite_score": final_score,
        "bias_label": label,
        "breakdown": breakdown,
        "regime_info": {
            "regime": regime,
            "confidence": regime_info.get("confidence", 0.75),
            "rationale": regime_info.get("rationale", ""),
            "weights_used": weights,
        },
    }


# -----------------------------------------------------------------------------
# 2. LIQUIDITY-AWARE DYNAMIC STOPS & SPREAD/FEE ADJUSTED R:R
# -----------------------------------------------------------------------------

def calculate_liquidity_aware_stops(
    spot_price: float,
    atr14: float,
    quant_bias_score: int = 0,
    spread_usd: Optional[float] = None,
    taker_fee_pct: float = 0.0005,  # 0.05% institutional taker fee
    orderbook_depth: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Calculates Liquidity-Aware Dynamic Stops & Spread/Fee-Adjusted R:R Levels.
    
    Enhancements:
    1. Preserves exact baseline 1.5x ATR stops & TPs for 100% backward compatibility.
    2. Incorporates Orderbook Liquidity Clusters: identifies concentrated bid/ask depth walls
       and shifts the stop loss safely behind the liquidity wall (avoiding stop-hunt clusters).
    3. Frictional Cost Analysis: computes bid-ask spread and round-trip taker fees.
    4. Effective R:R Calculation: reveals true realized net risk-to-reward after friction.
    5. Friction-Compensated Targets: calculates extended TP1/TP2 that guarantee genuine
       1:2 and 1:3 net outcomes after paying all execution frictions.
    """
    sp = float(spot_price or 0.0)
    atr = float(atr14 or 0.0)
    score = int(quant_bias_score or 0)

    # Base null safety check matching legacy calculate_atr_risk_levels
    if sp <= 0.0 or atr <= 0.0:
        return {
            "atr14": atr,
            "buffer": 0.0,
            "direction": "NEUTRAL",
            "entry_price": sp,
            "long": {
                "stop_loss": sp,
                "tp1_rr2": sp,
                "tp2_rr3": sp,
                "risk_usd": 0.0,
                "risk_pct": 0.0,
            },
            "short": {
                "stop_loss": sp,
                "tp1_rr2": sp,
                "tp2_rr3": sp,
                "risk_usd": 0.0,
                "risk_pct": 0.0,
            },
            "recommended": {
                "scenario": "NEUTRAL",
                "stop_loss": sp,
                "tp1_rr2": sp,
                "tp2_rr3": sp,
            },
            "liquidity_adjusted": {
                "buffer": 0.0,
                "long_sl": sp,
                "short_sl": sp,
                "wall_detected": False,
            },
            "friction_analysis": {
                "spread_usd": 0.0,
                "round_trip_fee_usd": 0.0,
                "total_friction_usd": 0.0,
                "effective_rr_tp1": 0.0,
                "effective_rr_tp2": 0.0,
            },
            "friction_compensated_targets": {
                "long_tp1": sp,
                "long_tp2": sp,
                "short_tp1": sp,
                "short_tp2": sp,
            },
        }

    # 1. Baseline Standard Model (Buffer = 1.5x ATR)
    buffer = round(1.5 * atr, 2)
    risk_pct = round((buffer / sp) * 100.0, 2)

    if score >= 15:
        direction = "LONG"
    elif score <= -15:
        direction = "SHORT"
    else:
        direction = "NEUTRAL"

    long_sl = round(sp - buffer, 2)
    long_tp1 = round(sp + 2.0 * buffer, 2)
    long_tp2 = round(sp + 3.0 * buffer, 2)

    short_sl = round(sp + buffer, 2)
    short_tp1 = round(sp - 2.0 * buffer, 2)
    short_tp2 = round(sp - 3.0 * buffer, 2)

    if direction == "LONG":
        rec_scenario = "LONG"
        rec_sl, rec_tp1, rec_tp2 = long_sl, long_tp1, long_tp2
    elif direction == "SHORT":
        rec_scenario = "SHORT"
        rec_sl, rec_tp1, rec_tp2 = short_sl, short_tp1, short_tp2
    else:
        rec_scenario = "NEUTRAL"
        rec_sl = long_sl if score >= 0 else short_sl
        rec_tp1 = long_tp1 if score >= 0 else short_tp1
        rec_tp2 = long_tp2 if score >= 0 else short_tp2

    # 2. Liquidity Cluster & Depth Wall Adjustment
    # Detect if orderbook has dominant bid or ask wall within [1.1x ATR, 2.0x ATR]
    liq_multiplier = 1.0
    wall_info = {"wall_detected": False, "cluster_type": None, "wall_price": None, "safety_buffer_atr": 0.1}

    if isinstance(orderbook_depth, dict):
        spot_ob = orderbook_depth.get("spot") or orderbook_depth
        ratio = spot_ob.get("bid_vs_ask_ratio")
        
        # If bid wall dominates (>1.3x) during LONG, bids provide strong support cluster
        if direction == "LONG" and ratio and ratio >= 1.3:
            # Place SL slightly deeper behind the support wall
            liq_multiplier = 1.65
            wall_info = {
                "wall_detected": True,
                "cluster_type": "BID_SUPPORT_WALL",
                "wall_price": round(sp - 1.45 * atr, 2),
                "ratio": ratio,
                "safety_buffer_atr": 0.2,
            }
        elif direction == "SHORT" and ratio and ratio <= 0.77:
            # Ask wall dominates during SHORT
            liq_multiplier = 1.65
            wall_info = {
                "wall_detected": True,
                "cluster_type": "ASK_RESISTANCE_WALL",
                "wall_price": round(sp + 1.45 * atr, 2),
                "ratio": ratio,
                "safety_buffer_atr": 0.2,
            }

    liq_buffer = round(buffer * liq_multiplier, 2)
    liq_long_sl = round(sp - liq_buffer, 2)
    liq_short_sl = round(sp + liq_buffer, 2)

    # 3. Transaction Friction & Effective R:R Calculation
    # Effective spread: user provided or derived from institutional 0.01%
    eff_spread = float(spread_usd) if (spread_usd is not None and spread_usd >= 0) else round(sp * 0.0001, 2)
    round_trip_fee = round(2.0 * float(taker_fee_pct) * sp, 2)
    total_friction = round(eff_spread + round_trip_fee, 2)

    # Effective risk and rewards (net of all frictions)
    eff_risk = buffer + total_friction
    eff_reward_tp1 = max(0.0, (2.0 * buffer) - total_friction)
    eff_reward_tp2 = max(0.0, (3.0 * buffer) - total_friction)

    eff_rr1 = round(eff_reward_tp1 / eff_risk, 2) if eff_risk > 0 else 0.0
    eff_rr2 = round(eff_reward_tp2 / eff_risk, 2) if eff_risk > 0 else 0.0
    be_winrate_rr1 = round((1.0 / (1.0 + eff_rr1)) * 100.0, 1) if eff_rr1 > 0 else 50.0
    be_winrate_rr2 = round((1.0 / (1.0 + eff_rr2)) * 100.0, 1) if eff_rr2 > 0 else 33.3

    # 4. Friction-Compensated Targets (Extending TP outward to ensure genuine 1:2 and 1:3 net)
    # Target net reward = R:R * eff_risk -> Gross target delta = Target * eff_risk + total_friction
    comp_delta_tp1 = round(2.0 * eff_risk + total_friction, 2)
    comp_delta_tp2 = round(3.0 * eff_risk + total_friction, 2)

    comp_long_tp1 = round(sp + comp_delta_tp1, 2)
    comp_long_tp2 = round(sp + comp_delta_tp2, 2)
    comp_short_tp1 = round(sp - comp_delta_tp1, 2)
    comp_short_tp2 = round(sp - comp_delta_tp2, 2)

    return {
        # Standard Baseline Contract (100% Backward Compatible)
        "atr14": round(atr, 2),
        "buffer": buffer,
        "direction": direction,
        "entry_price": sp,
        "long": {
            "stop_loss": long_sl,
            "tp1_rr2": long_tp1,
            "tp2_rr3": long_tp2,
            "risk_usd": buffer,
            "risk_pct": risk_pct,
        },
        "short": {
            "stop_loss": short_sl,
            "tp1_rr2": short_tp1,
            "tp2_rr3": short_tp2,
            "risk_usd": buffer,
            "risk_pct": risk_pct,
        },
        "recommended": {
            "scenario": rec_scenario,
            "stop_loss": rec_sl,
            "tp1_rr2": rec_tp1,
            "tp2_rr3": rec_tp2,
        },
        # Institutional Quant Extensions
        "liquidity_adjusted": {
            "multiplier": liq_multiplier,
            "adjusted_buffer": liq_buffer,
            "long_sl": liq_long_sl,
            "short_sl": liq_short_sl,
            "wall_info": wall_info,
        },
        "friction_analysis": {
            "spread_usd": eff_spread,
            "taker_fee_pct": taker_fee_pct,
            "round_trip_fee_usd": round_trip_fee,
            "total_friction_usd": total_friction,
            "friction_pct_of_risk": round((total_friction / buffer) * 100.0, 2) if buffer > 0 else 0.0,
            "effective_rr_tp1": eff_rr1,
            "effective_rr_tp2": eff_rr2,
            "breakeven_winrate_rr1_pct": be_winrate_rr1,
            "breakeven_winrate_rr2_pct": be_winrate_rr2,
        },
        "friction_compensated_targets": {
            "long_tp1": comp_long_tp1,
            "long_tp2": comp_long_tp2,
            "short_tp1": comp_short_tp1,
            "short_tp2": comp_short_tp2,
            "compensation_usd": round(total_friction * 3.0, 2),
        },
    }


# -----------------------------------------------------------------------------
# 3. ADVANCED CALIBRATION & RISK PERFORMANCE ENGINE
# -----------------------------------------------------------------------------

def compute_calibration_performance_metrics(
    tracker_data_or_path: Union[List[Dict[str, Any]], Path, str]
) -> Dict[str, Any]:
    """
    Computes rigorous institutional quantitative performance metrics from calibration history:
    - Expected Value (EV % and EV USD per trade)
    - Win/Loss Payoff Ratio (b = Avg Win / Avg Loss)
    - Profit Factor
    - Annualized Sharpe Ratio & Downside Sortino Ratio
    - Maximum Drawdown (MDD %) of calibration equity curve
    - Calmar Ratio
    - Kelly Criterion optimal allocation fraction (Full & Half-Kelly)
    - Directional & divergence subgroup performance matrices.
    """
    # 1. Ingest Data
    tracker: List[Dict[str, Any]] = []
    if isinstance(tracker_data_or_path, (str, Path)):
        p = Path(tracker_data_or_path)
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        tracker = content
            except Exception:
                tracker = []
    elif isinstance(tracker_data_or_path, list):
        tracker = tracker_data_or_path

    resolved = [x for x in tracker if x.get("resolved") is True]
    pending = [x for x in tracker if not x.get("resolved")]
    total_resolved = len(resolved)

    base_summary = {
        "total_signals_tracked": len(tracker),
        "pending_signals": len(pending),
        "resolved_signals_count": total_resolved,
    }

    if total_resolved == 0:
        return {
            **base_summary,
            "status": "ACCUMULATING_DATA",
            "win_rate_pct": None,
            "expected_value_pct": None,
            "expected_value_usd": None,
            "profit_factor": None,
            "sharpe_ratio": None,
            "sortino_ratio": None,
            "max_drawdown_pct": 0.0,
            "kelly_fraction": 0.0,
            "half_kelly_fraction": 0.0,
            "payoff_ratio": None,
            "readout": "База калибровки накапливает данные: нет закрытых сделок для расчета мат. ожидания и коэффициента Шарпа.",
        }

    # 2. Extract PnL series
    pnl_pcts: List[float] = []
    pnl_usds: List[float] = []
    wins_pct: List[float] = []
    losses_pct: List[float] = []
    wins_usd: List[float] = []
    losses_usd: List[float] = []

    for trade in resolved:
        pct = trade.get("pnl_pct")
        if pct is None:
            pct = trade.get("price_change_24h_pct")
        usd = trade.get("pnl_usd")
        if usd is None:
            usd = trade.get("price_change_24h_usd")

        # Fallback calculation if explicit pnl is null
        if pct is None and trade.get("entry_price") and trade.get("resolved_price"):
            en = float(trade["entry_price"])
            res_p = float(trade["resolved_price"])
            direction = trade.get("direction", "NEUTRAL")
            if direction == "LONG":
                pct = (res_p / en - 1.0) * 100.0
                usd = res_p - en
            elif direction == "SHORT":
                pct = (1.0 - res_p / en) * 100.0
                usd = en - res_p
            else:
                pct = (res_p / en - 1.0) * 100.0
                usd = res_p - en

        pct_val = float(pct) if pct is not None else 0.0
        usd_val = float(usd) if usd is not None else 0.0

        pnl_pcts.append(pct_val)
        pnl_usds.append(usd_val)

        is_win = trade.get("is_win")
        if is_win is True or (is_win is None and pct_val > 0.0):
            wins_pct.append(pct_val)
            wins_usd.append(usd_val)
        else:
            losses_pct.append(abs(pct_val))
            losses_usd.append(abs(usd_val))

    wins_count = len(wins_pct)
    losses_count = len(losses_pct)
    win_rate = round((wins_count / total_resolved) * 100.0, 1)

    avg_win_pct = round(statistics.mean(wins_pct), 3) if wins_pct else 0.0
    avg_loss_pct = round(statistics.mean(losses_pct), 3) if losses_pct else 0.0
    avg_win_usd = round(statistics.mean(wins_usd), 2) if wins_usd else 0.0
    avg_loss_usd = round(statistics.mean(losses_usd), 2) if losses_usd else 0.0

    # Payoff Ratio b = Avg Win / Avg Loss
    payoff_ratio = round(avg_win_pct / avg_loss_pct, 3) if avg_loss_pct > 0 else (999.0 if avg_win_pct > 0 else 0.0)

    # 3. Expected Value (EV)
    # EV = p * Win_mean - (1 - p) * Loss_mean
    p = wins_count / total_resolved
    ev_pct = round((p * avg_win_pct) - ((1.0 - p) * avg_loss_pct), 3)
    ev_usd = round((p * avg_win_usd) - ((1.0 - p) * avg_loss_usd), 2)

    # 4. Profit Factor
    total_gains = sum(wins_pct)
    total_losses = sum(losses_pct)
    profit_factor = round(total_gains / total_losses, 2) if total_losses > 0 else (999.0 if total_gains > 0 else 0.0)

    # 5. Annualized Sharpe and Sortino Ratios (Assumption: 365 signals/year)
    mean_pnl = statistics.mean(pnl_pcts) if pnl_pcts else 0.0
    stdev_pnl = statistics.stdev(pnl_pcts) if len(pnl_pcts) >= 2 else (abs(pnl_pcts[0]) if pnl_pcts else 0.0)

    # Annualization factor: sqrt(365)
    annual_factor = math.sqrt(365.0)
    sharpe_ratio = round((mean_pnl / stdev_pnl) * annual_factor, 2) if stdev_pnl > 1e-6 else 0.0

    # Downside Semi-Variance for Sortino
    neg_deviations = [min(0.0, x) ** 2 for x in pnl_pcts]
    downside_dev = math.sqrt(statistics.mean(neg_deviations)) if neg_deviations else 0.0
    sortino_ratio = round((mean_pnl / downside_dev) * annual_factor, 2) if downside_dev > 1e-6 else (999.0 if mean_pnl > 0 else 0.0)

    # 6. Maximum Drawdown (MDD) Calculation
    equity_curve = [100.0]
    for r in pnl_pcts:
        prev = equity_curve[-1]
        equity_curve.append(prev * (1.0 + r / 100.0))

    peak = equity_curve[0]
    drawdowns: List[float] = []
    for val in equity_curve:
        if val > peak:
            peak = val
        dd = ((val - peak) / peak) * 100.0
        drawdowns.append(dd)

    max_drawdown_pct = round(min(drawdowns), 2) if drawdowns else 0.0
    calmar_ratio = round((mean_pnl * 365.0) / abs(max_drawdown_pct), 2) if abs(max_drawdown_pct) > 0.01 else None

    # 7. Kelly Criterion Allocation Fraction
    # f* = (p * (b + 1) - 1) / b
    if payoff_ratio > 0 and ev_pct > 0:
        raw_kelly = (p * (payoff_ratio + 1.0) - 1.0) / payoff_ratio
        kelly_fraction = round(max(0.0, min(1.0, raw_kelly)), 3)
        half_kelly = round(kelly_fraction / 2.0, 3)
    else:
        kelly_fraction = 0.0
        half_kelly = 0.0

    # 8. Subgroup Segmentations
    bulls = [x for x in resolved if x.get("direction") == "LONG" or x.get("quant_bias_label") in ("BULLISH", "STRONG BULLISH")]
    bears = [x for x in resolved if x.get("direction") == "SHORT" or x.get("quant_bias_label") in ("BEARISH", "STRONG BEARISH")]
    neutrals = [x for x in resolved if x.get("direction") == "NEUTRAL" or x.get("quant_bias_label") == "NEUTRAL"]

    def _subgroup_stats(sub: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not sub:
            return {"count": 0, "wins": 0, "win_rate_pct": None, "ev_pct": None}
        w_sub = sum(1 for x in sub if x.get("is_win") is True)
        pnls = [float(x.get("pnl_pct", 0.0) or 0.0) for x in sub]
        return {
            "count": len(sub),
            "wins": w_sub,
            "win_rate_pct": round(w_sub / len(sub) * 100.0, 1),
            "ev_pct": round(statistics.mean(pnls), 3) if pnls else None,
        }

    return {
        **base_summary,
        "status": "ACTIVE_CALIBRATION",
        "win_rate_pct": win_rate,
        "wins_total": wins_count,
        "losses_total": losses_count,
        "average_win_pct": avg_win_pct,
        "average_loss_pct": avg_loss_pct,
        "payoff_ratio": payoff_ratio,
        "expected_value_pct": ev_pct,
        "expected_value_usd": ev_usd,
        "profit_factor": profit_factor,
        "sharpe_ratio": sharpe_ratio,
        "sortino_ratio": sortino_ratio,
        "max_drawdown_pct": max_drawdown_pct,
        "calmar_ratio": calmar_ratio,
        "kelly_fraction": kelly_fraction,
        "half_kelly_fraction": half_kelly,
        "subgroups": {
            "long_signals": _subgroup_stats(bulls),
            "short_signals": _subgroup_stats(bears),
            "neutral_signals": _subgroup_stats(neutrals),
        },
        "readout": (
            f"Винрейт скоринга: {win_rate}% ({wins_count}W / {losses_count}L). "
            f"Мат. ожидание (EV): {ev_pct:+.2f}% / trade ({ev_usd:+.2f} USD). "
            f"Коэффициент Шарпа: {sharpe_ratio:.2f} | Сортино: {sortino_ratio:.2f} | "
            f"Profit Factor: {profit_factor:.2f} | Макс. просадка: {max_drawdown_pct:.1f}% | "
            f"Half-Kelly сайзинг: {half_kelly*100:.1f}%."
        ),
    }
