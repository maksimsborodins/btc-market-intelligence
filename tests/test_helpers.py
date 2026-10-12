"""
Shared testing utilities and reference oracles for BTC Market Intelligence E2E test suite.
"""

import os
import sys
import json
import time
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

def run_cli(args: list[str], timeout: float = 15.0) -> subprocess.CompletedProcess:
    """Run a CLI command with project root as working directory."""
    cmd = [sys.executable, str(PROJECT_ROOT / "btc_market_intelligence.py")] + args
    return subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )

def is_fast_mode_supported() -> bool:
    """Check if --fast CLI argument is wired in __main__ of btc_market_intelligence.py."""
    try:
        bmi_path = PROJECT_ROOT / "btc_market_intelligence.py"
        if not bmi_path.exists():
            return False
        content = bmi_path.read_text(encoding="utf-8", errors="ignore")
        if "__main__" in content:
            main_block = content.split("__main__")[-1]
            return "--fast" in main_block
        return False
    except Exception:
        return False

def is_atr_risk_implemented() -> bool:
    """Check if calculate_atr_risk_levels is implemented in btc_market_intelligence."""
    try:
        import btc_market_intelligence as bmi
        return hasattr(bmi, "calculate_atr_risk_levels")
    except Exception:
        return False

def is_onchain_implemented() -> bool:
    """Check if fetch_onchain_metrics is implemented in btc_market_intelligence."""
    try:
        import btc_market_intelligence as bmi
        return hasattr(bmi, "fetch_onchain_metrics")
    except Exception:
        return False

def is_dashboard_implemented() -> bool:
    """Check if dashboard.py exists in project root."""
    return (PROJECT_ROOT / "dashboard.py").is_file()

def is_launcher_implemented() -> bool:
    """Check if run_dashboard.bat exists in project root."""
    return (PROJECT_ROOT / "run_dashboard.bat").is_file()

# --- Reference Mathematical Oracles strictly derived from PROJECT.md ---

def reference_atr_risk_levels(spot_price: float, atr14: float, quant_bias_score: int = 0) -> dict:
    """Authoritative mathematical reference for ATR risk levels (PROJECT.md contract)."""
    buffer = 1.5 * atr14
    direction = "LONG" if quant_bias_score >= 15 else ("SHORT" if quant_bias_score <= -15 else "NEUTRAL")
    
    long_sl = spot_price - buffer
    long_tp1 = spot_price + (2.0 * buffer)
    long_tp2 = spot_price + (3.0 * buffer)
    
    short_sl = spot_price + buffer
    short_tp1 = spot_price - (2.0 * buffer)
    short_tp2 = spot_price - (3.0 * buffer)
    
    risk_usd = buffer
    risk_pct = (risk_usd / spot_price * 100) if spot_price > 0 else 0.0

    if direction == "LONG":
        recommended = {"scenario": "LONG", "stop_loss": round(long_sl, 2), "tp1_rr2": round(long_tp1, 2), "tp2_rr3": round(long_tp2, 2)}
    elif direction == "SHORT":
        recommended = {"scenario": "SHORT", "stop_loss": round(short_sl, 2), "tp1_rr2": round(short_tp1, 2), "tp2_rr3": round(short_tp2, 2)}
    else:
        recommended = {"scenario": "NEUTRAL", "stop_loss": round(long_sl, 2), "tp1_rr2": round(long_tp1, 2), "tp2_rr3": round(long_tp2, 2)}

    return {
        "atr14": round(atr14, 2),
        "buffer": round(buffer, 2),
        "direction": direction,
        "entry_price": round(spot_price, 2),
        "long": {
            "stop_loss": round(long_sl, 2),
            "tp1_rr2": round(long_tp1, 2),
            "tp2_rr3": round(long_tp2, 2),
            "risk_usd": round(risk_usd, 2),
            "risk_pct": round(risk_pct, 3),
        },
        "short": {
            "stop_loss": round(short_sl, 2),
            "tp1_rr2": round(short_tp1, 2),
            "tp2_rr3": round(short_tp2, 2),
            "risk_usd": round(risk_usd, 2),
            "risk_pct": round(risk_pct, 3),
        },
        "recommended": recommended,
    }

def reference_mvrv_stage(zscore: float | None) -> str:
    """Authoritative classification for MVRV Z-Score (PROJECT.md contract)."""
    if zscore is None:
        return "UNAVAILABLE"
    if zscore < 0.1:
        return "Bottom / Undervalued"
    if zscore <= 1.5:
        return "Fair Value / Early Bull"
    if zscore <= 3.0:
        return "Mid-to-Late Bull"
    if zscore <= 5.0:
        return "Distribution / Late Cycle"
    return "Cycle Top / Overheated"

def reference_nupl_stage(nupl: float | None) -> str:
    """Authoritative classification for NUPL (PROJECT.md contract)."""
    if nupl is None:
        return "UNAVAILABLE"
    if nupl < 0.0:
        return "Capitulation"
    if nupl < 0.25:
        return "Hope / Fear"
    if nupl < 0.50:
        return "Optimism / Anxiety"
    if nupl < 0.75:
        return "Belief / Denial"
    return "Euphoria / Greed"

def make_mock_snapshot() -> dict:
    """Create a complete valid mock market_snapshot.json dictionary."""
    return {
        "timestamp_utc": "2026-10-11T12:00:00+00:00",
        "prices": {
            "spot_last": 83000.0,
            "futures_mark": 82960.0,
            "basis_abs": -40.0,
            "basis_pct": -0.048,
        },
        "quant_bias": {
            "composite_score": 32,
            "bias_label": "BULLISH",
            "breakdown": {
                "spot_cvd_24h": 15,
                "orderbook_imbalance": 15,
                "divergence": 10,
                "vwap_trend": -8,
            },
        },
        "statistical_z_scores": {
            "oi_zscore": -0.85,
            "funding_zscore": -1.48,
        },
        "spot_cvd": {
            "15m": 25.5,
            "1h": 85.2,
            "4h": 190.0,
            "24h": 315.4,
        },
        "risk_model": reference_atr_risk_levels(83000.0, 476.0, 32),
        "onchain_valuation": {
            "mvrv_zscore": 1.09,
            "mvrv_stage": "Fair Value / Early Bull",
            "nupl": 0.384,
            "nupl_stage": "Optimism / Anxiety",
            "realized_price": 53295.0,
            "status": "OK",
        },
        "execution_time_sec": 2.8,
    }

def make_mock_tracker() -> list[dict]:
    """Create a complete valid mock quant_calibration_tracker.json list."""
    return [
        {
            "id": "2026-10-10T10:00:00+00:00",
            "epoch": 1791626400.0,
            "timestamp_utc": "2026-10-10T10:00:00+00:00",
            "direction": "LONG",
            "entry_price": 82000.0,
            "spot_price": 82000.0,
            "quant_bias_score": 25,
            "quant_bias_label": "BULLISH",
            "divergence_state": "Bullish Accumulation",
            "oi_zscore": -0.5,
            "atr14_4h": 450.0,
            "stop_loss": 81325.0,
            "tp1_rr2": 82900.0,
            "tp2_rr3": 83350.0,
            "resolved": True,
            "resolution_type": "TP1_HIT",
            "resolved_at_utc": "2026-10-10T14:30:00+00:00",
            "resolved_price": 82950.0,
            "pnl_pct": 1.158,
            "is_win": True,
            "outcome": "WIN",
            "actual_elapsed_hours": 4.5,
        },
        {
            "id": "2026-10-11T08:00:00+00:00",
            "epoch": 1791705600.0,
            "timestamp_utc": "2026-10-11T08:00:00+00:00",
            "direction": "LONG",
            "entry_price": 83050.0,
            "spot_price": 83050.0,
            "quant_bias_score": 32,
            "quant_bias_label": "BULLISH",
            "divergence_state": "Neutral",
            "oi_zscore": -0.85,
            "atr14_4h": 476.0,
            "stop_loss": 82336.0,
            "tp1_rr2": 84478.0,
            "tp2_rr3": 85192.0,
            "resolved": False,
            "resolution_type": "PENDING",
            "resolved_at_utc": None,
            "resolved_price": None,
            "pnl_pct": None,
            "is_win": None,
            "outcome": None,
            "actual_elapsed_hours": None,
        },
    ]
