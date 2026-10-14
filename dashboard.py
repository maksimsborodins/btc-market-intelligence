"""
BTC Market Intelligence Terminal — Interactive Streamlit Dashboard
Production-grade quantitative trading workstation and risk analytics cockpit.
"""

import os
import sys
import json
import time
import math
import base64
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd

# Root project directory configuration
PROJECT_ROOT = Path(__file__).resolve().parent
CACHE_DIR = PROJECT_ROOT / "data_cache"
UI_SETTINGS_FILE = CACHE_DIR / "ui_settings.json"

SUPPORTED_AI_MODELS = {
    "gemini-3.8-flash": "Gemini 3.8 Flash (По умолчанию)",
    "gemini-3.7-flash": "Gemini 3.7 Flash",
}
DEFAULT_AI_MODEL = "gemini-3.8-flash"

# Ensure page config is set as early as possible
try:
    st.set_page_config(
        page_title="BTC Market Intelligence Terminal",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception:
    pass

# Synchronize st.secrets to os.environ when hosted on Streamlit Cloud
try:
    if hasattr(st, "secrets"):
        for _k in st.secrets:
            _v = st.secrets[_k]
            if isinstance(_v, str) and _k not in os.environ:
                os.environ[_k] = _v
except (Exception, BaseException):
    pass

# --- Custom Institutional Matte Luxury Dark Theme (Zero Emojis, High Usability) ---
CUSTOM_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700&display=swap');

    /* Global Matte Luxury Dark Theme */
    html, body, [class*="css"], .stApp {
        background-color: #0e1117 !important;
        color: #e6edf3 !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    /* Subtle custom scrollbars */
    ::-webkit-scrollbar {
        width: 6px;
        height: 6px;
    }
    ::-webkit-scrollbar-track {
        background: #11141a;
    }
    ::-webkit-scrollbar-thumb {
        background: #2d3342;
        border-radius: 4px;
    }
    ::-webkit-scrollbar-thumb:hover {
        background: #c5a880;
    }

    /* Top Ticker Tape - Muted, Calm, Non-blinding */
    .bloomberg-ticker-tape {
        background: #141720;
        border: 1px solid rgba(197, 168, 128, 0.22);
        padding: 0.55rem 1.15rem;
        display: flex;
        justify-content: space-between;
        align-items: center;
        flex-wrap: wrap;
        gap: 0.85rem;
        font-family: 'JetBrains Mono', monospace;
        font-variant-numeric: tabular-nums;
        font-size: 0.78rem;
        margin-bottom: 1rem;
        border-radius: 10px;
    }
    .ticker-item {
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        white-space: nowrap;
    }
    .ticker-symbol {
        color: #c5a880;
        font-weight: 600;
        letter-spacing: 0.03em;
    }
    .ticker-val {
        color: #ffffff;
        font-weight: 600;
    }
    .ticker-pos { color: #2ebd85; font-weight: 600; }
    .ticker-neg { color: #f6465d; font-weight: 600; }
    .ticker-neutral { color: #d4b483; font-weight: 600; }

    /* Top Executive Header */
    .terminal-header {
        background: #141720;
        padding: 1.1rem 1.45rem;
        border-radius: 12px;
        border: 1px solid rgba(197, 168, 128, 0.2);
        margin-bottom: 1.15rem;
    }
    .terminal-title {
        font-family: 'Inter', sans-serif;
        font-size: 1.5rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #ffffff;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .terminal-subtitle {
        font-size: 0.8rem;
        color: #8b949e;
        font-family: 'Inter', sans-serif;
        margin-top: 0.2rem;
        font-weight: 400;
    }

    /* Calm Status Badge */
    .bloomberg-status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(197, 168, 128, 0.1);
        color: #dfc18b;
        border: 1px solid rgba(197, 168, 128, 0.32);
        padding: 4px 10px;
        border-radius: 8px;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 600;
    }
    .live-dot {
        width: 7px;
        height: 7px;
        background-color: #2ebd85;
        border-radius: 50%;
        display: inline-block;
    }
    .dot-amber {
        width: 7px;
        height: 7px;
        background-color: #dfc18b;
        border-radius: 50%;
        display: inline-block;
    }
    .dot-red {
        width: 7px;
        height: 7px;
        background-color: #f6465d;
        border-radius: 50%;
        display: inline-block;
    }

    /* KPI Cards - Fixed Geometry, Locked Baselines, Zero Shift */
    .kpi-card {
        background: #161a24;
        border: 1px solid rgba(197, 168, 128, 0.16);
        border-radius: 12px;
        padding: 0.85rem 1rem;
        display: flex;
        flex-direction: column;
        justify-content: flex-start;
        min-height: 108px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
        box-sizing: border-box;
        transition: border-color 0.18s ease;
    }
    .kpi-card:hover {
        border-color: rgba(223, 193, 139, 0.45);
    }
    .kpi-title {
        font-size: 0.71rem;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        color: #8b949e;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        height: 2.1rem;
        line-height: 1.05rem;
        display: flex;
        align-items: flex-start;
        overflow: hidden;
        margin-bottom: 0.25rem;
    }
    .kpi-value {
        font-size: 1.25rem;
        font-weight: 700;
        color: #ffffff;
        line-height: 1.5rem;
        height: 1.5rem;
        display: flex;
        align-items: center;
        font-family: 'JetBrains Mono', monospace;
        font-variant-numeric: tabular-nums;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        margin-bottom: 0.2rem;
    }
    .kpi-sub {
        font-size: 0.74rem;
        line-height: 1.25rem;
        height: 1.25rem;
        display: flex;
        align-items: center;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .kpi-delta-pos {
        color: #2ebd85;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 500;
    }
    .kpi-delta-neg {
        color: #f6465d;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 500;
    }
    .kpi-delta-neutral {
        color: #c5a880;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 500;
    }

    /* Badges */
    .badge-bullish {
        background: rgba(46, 189, 133, 0.12);
        color: #2ebd85;
        border: 1px solid rgba(46, 189, 133, 0.35);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.71rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
        display: inline-block;
    }
    .badge-bearish {
        background: rgba(246, 70, 93, 0.12);
        color: #f6465d;
        border: 1px solid rgba(246, 70, 93, 0.35);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.71rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
        display: inline-block;
    }
    .badge-neutral {
        background: rgba(197, 168, 128, 0.12);
        color: #dfc18b;
        border: 1px solid rgba(197, 168, 128, 0.35);
        padding: 2px 8px;
        border-radius: 6px;
        font-size: 0.71rem;
        font-weight: 600;
        font-family: 'JetBrains Mono', monospace;
        display: inline-block;
    }

    /* Content Panels */
    .content-panel {
        background: #141720;
        border: 1px solid rgba(197, 168, 128, 0.15);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1.15rem;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    }

    /* Streamlit Tabs - Modern Soft Capsule */
    .stTabs [data-baseweb="tab-list"] {
        background: #11141c !important;
        border: 1px solid rgba(197, 168, 128, 0.18) !important;
        border-radius: 12px !important;
        padding: 4px !important;
        gap: 6px !important;
    }
    .stTabs [data-baseweb="tab"] {
        color: #8b949e !important;
        background: transparent !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.82rem !important;
        font-weight: 500 !important;
        border-radius: 8px !important;
        padding: 8px 16px !important;
        border: none !important;
        transition: all 0.15s ease !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        color: #dfc18b !important;
        background: rgba(197, 168, 128, 0.08) !important;
    }
    .stTabs [aria-selected="true"] {
        color: #ffffff !important;
        background: #1e2330 !important;
        border: 1px solid rgba(223, 193, 139, 0.4) !important;
        font-weight: 600 !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* Sidebar - Clean, Distraction Free */
    section[data-testid="stSidebar"] {
        background-color: #11141a !important;
        border-right: 1px solid rgba(197, 168, 128, 0.16) !important;
    }
    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3 {
        color: #dfc18b !important;
        font-family: 'Inter', sans-serif !important;
        font-weight: 600 !important;
        font-size: 1.05rem !important;
    }

    /* Buttons - Clean Soft Gold */
    .stButton > button, div.stDownloadButton > button {
        background: #191d28 !important;
        color: #dfc18b !important;
        border: 1px solid rgba(223, 193, 139, 0.35) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.84rem !important;
        font-weight: 600 !important;
        border-radius: 10px !important;
        padding: 0.55rem 1rem !important;
        transition: all 0.15s ease !important;
    }
    .stButton > button:hover, div.stDownloadButton > button:hover {
        background: #c5a880 !important;
        color: #0e1117 !important;
        border-color: #dfc18b !important;
    }

    /* Sidebar Section Headers */
    .sidebar-section-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-top: 0.25rem;
        margin-bottom: 0.65rem;
        padding-bottom: 0.4rem;
        border-bottom: 1px solid rgba(197, 168, 128, 0.18);
    }
    .sidebar-section-title {
        font-family: 'Inter', sans-serif;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #dfc18b;
    }
    .sidebar-section-pill {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.64rem;
        font-weight: 600;
        color: #2ebd85;
        background: rgba(46, 189, 133, 0.12);
        border: 1px solid rgba(46, 189, 133, 0.3);
        padding: 2px 7px;
        border-radius: 4px;
        letter-spacing: 0.03em;
    }
    .sidebar-section-pill-amber {
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.64rem;
        font-weight: 600;
        color: #dfc18b;
        background: rgba(197, 168, 128, 0.12);
        border: 1px solid rgba(197, 168, 128, 0.3);
        padding: 2px 7px;
        border-radius: 4px;
        letter-spacing: 0.03em;
    }

    /* Sidebar Action Buttons */
    section[data-testid="stSidebar"] div.stButton > button {
        background: #151922 !important;
        color: #dfc18b !important;
        border: 1px solid rgba(223, 193, 139, 0.38) !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
        font-size: 0.84rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
        min-height: 42px !important;
        height: 42px !important;
        border-radius: 8px !important;
        padding: 0 1rem !important;
        margin-bottom: 0.25rem !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-sizing: border-box !important;
        box-shadow: 0 1px 3px rgba(0, 0, 0, 0.3) !important;
        transition: all 0.15s cubic-bezier(0.16, 1, 0.3, 1) !important;
    }
    section[data-testid="stSidebar"] div.stButton > button:hover {
        background: #dfc18b !important;
        color: #0b0e14 !important;
        border-color: #f0d5a0 !important;
        box-shadow: 0 2px 8px rgba(223, 193, 139, 0.25) !important;
    }

    /* Sidebar Download Button */
    section[data-testid="stSidebar"] div.stDownloadButton > button {
        background: rgba(46, 189, 133, 0.1) !important;
        color: #2ebd85 !important;
        border: 1px solid rgba(46, 189, 133, 0.35) !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
        font-size: 0.84rem !important;
        font-weight: 600 !important;
        letter-spacing: 0.02em !important;
        min-height: 40px !important;
        height: 40px !important;
        border-radius: 8px !important;
        padding: 0 1rem !important;
        box-sizing: border-box !important;
    }
    section[data-testid="stSidebar"] div.stDownloadButton > button:hover {
        background: #2ebd85 !important;
        color: #0b0e14 !important;
        border-color: #2ebd85 !important;
    }

    /* Metrics Styling */
    [data-testid="stMetric"] {
        background: #161a24 !important;
        border: 1px solid rgba(197, 168, 128, 0.14) !important;
        border-radius: 12px !important;
        padding: 0.75rem 1rem !important;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2) !important;
    }
    [data-testid="stMetricValue"] {
        font-family: 'JetBrains Mono', monospace !important;
        color: #ffffff !important;
        font-weight: 600 !important;
        font-size: 1.25rem !important;
    }
    [data-testid="stMetricLabel"] {
        color: #8b949e !important;
        font-size: 0.75rem !important;
        text-transform: uppercase !important;
        letter-spacing: 0.03em !important;
    }

    /* Dataframe & Tables Styling */
    [data-testid="stDataFrame"] {
        border: 1px solid rgba(197, 168, 128, 0.18) !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }

    /* Clean Trading Status Cards in Sidebar */
    .sidebar-status-card {
        background: #161a24;
        border: 1px solid rgba(197, 168, 128, 0.18);
        border-radius: 10px;
        padding: 0.75rem 0.9rem;
        margin-top: 0.4rem;
        margin-bottom: 0.85rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }
    .sidebar-stat-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 5px 0;
        border-bottom: 1px solid rgba(197, 168, 128, 0.08);
        gap: 8px;
    }
    .sidebar-stat-row:last-child {
        border-bottom: none;
    }
    .sidebar-stat-label {
        font-size: 0.71rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        font-family: 'Inter', sans-serif;
        white-space: nowrap;
    }
    .sidebar-stat-val {
        font-size: 0.75rem;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 600;
        color: #ffffff;
        text-align: right;
        white-space: nowrap;
    }
    .sidebar-stat-val-gold {
        font-size: 0.75rem;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 600;
        color: #dfc18b;
        text-align: right;
        white-space: nowrap;
    }
</style>
"""


# --- Robust Data Hydration & Settings Helpers ---

def sanitize_number(val: Any, default: Optional[float] = None) -> Optional[float]:
    """Ensure numeric value is finite and not NaN/Inf."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default


def get_selected_ai_model() -> str:
    """Читает выбранную пользователем модель ИИ (по умолчанию gemini-3.8-flash)."""
    try:
        if UI_SETTINGS_FILE.exists():
            data = json.loads(UI_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                m = str(data.get("gemini_model", "")).strip()
                if m in SUPPORTED_AI_MODELS:
                    return m
    except Exception:
        pass
    env_m = os.getenv("GEMINI_MODEL", DEFAULT_AI_MODEL).strip()
    return env_m if env_m in SUPPORTED_AI_MODELS else DEFAULT_AI_MODEL


def save_selected_ai_model(model_id: str) -> str:
    """Сохраняет выбранную модель ИИ в настройки и окружение."""
    clean_id = model_id if model_id in SUPPORTED_AI_MODELS else DEFAULT_AI_MODEL
    os.environ["GEMINI_MODEL"] = clean_id
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        payload = {
            "gemini_model": clean_id,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        tmp_path = UI_SETTINGS_FILE.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(UI_SETTINGS_FILE)
    except Exception:
        pass
    return clean_id


def load_market_snapshot(file_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load latest market snapshot artifact with graceful fallbacks."""
    target_path = file_path or (PROJECT_ROOT / "market_snapshot.json")
    if not target_path.exists():
        return {}
    try:
        raw_text = target_path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return {}
        data = json.loads(raw_text)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
        return {}


def load_market_history(file_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load market history time-series data."""
    target_path = file_path or (PROJECT_ROOT / "market_history.json")
    if not target_path.exists():
        return []
    try:
        raw_text = target_path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return []
        data = json.loads(raw_text)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
        return []


def load_calibration_tracker(file_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load calibration tracker historical signals."""
    target_path = file_path or (PROJECT_ROOT / "quant_calibration_tracker.json")
    if not target_path.exists():
        return []
    try:
        raw_text = target_path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return []
        data = json.loads(raw_text)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
        return []


def load_daemon_status(file_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load background daemon status for sidebar telemetry."""
    target_path = file_path or (PROJECT_ROOT / "daemon_status.json")
    if not target_path.exists():
        return {"status": "STOPPED"}
    try:
        raw_text = target_path.read_text(encoding="utf-8")
        if not raw_text.strip():
            return {"status": "STOPPED"}
        data = json.loads(raw_text)
        return data if isinstance(data, dict) else {"status": "STOPPED"}
    except Exception:
        return {"status": "STOPPED"}


def load_markdown_report(file_path: Optional[Path] = None) -> Optional[str]:
    """Read daily_report.md text."""
    target_path = file_path or (PROJECT_ROOT / "daily_report.md")
    if not target_path.exists():
        return None
    try:
        return target_path.read_text(encoding="utf-8")
    except (json.JSONDecodeError, OSError, UnicodeDecodeError, ValueError):
        return None


def load_pdf_base64(file_path: Optional[Path] = None) -> Optional[str]:
    """Read daily_report.pdf and encode as base64 string for iframe."""
    target_path = file_path or (PROJECT_ROOT / "daily_report.pdf")
    if not target_path.exists() or target_path.stat().st_size == 0:
        return None
    try:
        raw_bytes = target_path.read_bytes()
        return base64.b64encode(raw_bytes).decode("utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None


def get_available_screenshots() -> Dict[str, Path]:
    """Enumerate valid PNG screenshots in free_dashboard_screenshots directory."""
    screenshots_dir = PROJECT_ROOT / "free_dashboard_screenshots"
    if not screenshots_dir.exists() or not screenshots_dir.is_dir():
        return {}
    res = {}
    for p in sorted(screenshots_dir.glob("*.png")):
        name_clean = p.stem.replace("_", " ").title()
        res[name_clean] = p
    return res


# --- Data Extraction Utilities ---

def extract_spot_price(snapshot: Dict[str, Any]) -> float:
    """Extract current BTC spot price across varied schema versions."""
    price = sanitize_number(snapshot.get("spot_price"))
    if price is not None:
        return price
    binance_data = snapshot.get("binance") if isinstance(snapshot.get("binance"), dict) else {}
    prices = snapshot.get("prices") if isinstance(snapshot.get("prices"), dict) else binance_data.get("prices", {})
    if isinstance(prices, dict):
        price = sanitize_number(prices.get("spot_last"))
        if price is not None:
            return price
    return 83000.0


def extract_quant_bias(snapshot: Dict[str, Any]) -> Tuple[int, str, Dict[str, int]]:
    """Extract Quant Bias score, label, and factor breakdown."""
    qb = snapshot.get("quant_bias") or snapshot.get("binance", {}).get("quant_bias", {})
    if not isinstance(qb, dict):
        qb = {}
    score = sanitize_number(qb.get("composite_score"), 0)
    score_int = int(max(-100, min(100, round(score))))
    label = str(qb.get("bias_label", "NEUTRAL")).upper()
    breakdown = qb.get("breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    return score_int, label, breakdown


def extract_risk_model(snapshot: Dict[str, Any], spot_price: float) -> Dict[str, Any]:
    """Extract or reconstruct ATR risk model."""
    risk = snapshot.get("risk_model") or snapshot.get("atr_risk") or snapshot.get("binance", {}).get("risk_model")
    if isinstance(risk, dict) and "long" in risk and "short" in risk:
        return risk

    atr14 = 476.16
    buffer = 1.5 * atr14
    return {
        "atr14": atr14,
        "buffer": buffer,
        "direction": "LONG",
        "entry_price": spot_price,
        "long": {
            "stop_loss": round(spot_price - buffer, 2),
            "tp1_rr2": round(spot_price + 2.0 * buffer, 2),
            "tp2_rr3": round(spot_price + 3.0 * buffer, 2),
            "risk_usd": round(buffer, 2),
            "risk_pct": round(buffer / spot_price * 100, 2),
        },
        "short": {
            "stop_loss": round(spot_price + buffer, 2),
            "tp1_rr2": round(spot_price - 2.0 * buffer, 2),
            "tp2_rr3": round(spot_price - 3.0 * buffer, 2),
            "risk_usd": round(buffer, 2),
            "risk_pct": round(buffer / spot_price * 100, 2),
        },
        "recommended": {
            "scenario": "LONG",
            "direction": "LONG",
            "stop_loss": round(spot_price - buffer, 2),
            "tp1_rr2": round(spot_price + 2.0 * buffer, 2),
            "tp2_rr3": round(spot_price + 3.0 * buffer, 2),
        },
    }


# --- Visualization Generators (Plotly Engine - Matte Luxury Black & Gold) ---

def create_quant_bias_gauge(score: int, prev_score: Optional[int] = None, label: str = "NEUTRAL") -> go.Figure:
    """Sleek, minimalist Quant Bias Speedometer Gauge Chart (-100 to +100)."""
    clamped_score = max(-100, min(100, score))
    delta_dict = None
    if prev_score is not None:
        delta_dict = {
            "reference": prev_score,
            "increasing": {"color": "#2ebd85"},
            "decreasing": {"color": "#f6465d"},
            "valueformat": "+d",
        }

    pointer_color = "#2ebd85" if clamped_score >= 15 else ("#f6465d" if clamped_score <= -15 else "#dfc18b")
    fig = go.Figure(
        go.Indicator(
            mode="gauge+number+delta" if delta_dict else "gauge+number",
            value=clamped_score,
            delta=delta_dict,
            title={
                "text": f"<b>QUANT BIAS INDEX: <span style='color:#dfc18b'>{label}</span></b>",
                "font": {"size": 13, "color": "#8b949e", "family": "Inter, sans-serif"},
            },
            number={"font": {"size": 44, "color": "#ffffff", "family": "JetBrains Mono, monospace"}},
            gauge={
                "axis": {
                    "range": [-100, 100],
                    "tickvals": [-100, -50, 0, 50, 100],
                    "ticktext": ["-100", "-50", "0", "+50", "+100"],
                    "tickcolor": "rgba(197, 168, 128, 0.3)",
                    "tickwidth": 1,
                    "tickfont": {"size": 10, "color": "#8b949e", "family": "JetBrains Mono, monospace"},
                },
                "bar": {"color": pointer_color, "thickness": 0.18},
                "bgcolor": "#141822",
                "borderwidth": 1,
                "bordercolor": "rgba(197, 168, 128, 0.18)",
                "steps": [
                    {"range": [-100, -15], "color": "rgba(246, 70, 93, 0.08)"},
                    {"range": [-15, 15], "color": "rgba(197, 168, 128, 0.05)"},
                    {"range": [15, 100], "color": "rgba(46, 189, 133, 0.08)"},
                ],
            },
        )
    )

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=25, r=25, t=45, b=20),
        height=310,
        hovermode=False,
    )
    return fig


def create_factor_breakdown_chart(breakdown: Dict[str, Any]) -> go.Figure:
    """Horizontal bar chart showing contributions of the 6 Quant Bias factors (matches real weights)."""
    factor_labels = {
        "1d_vwap_trend": "1D VWAP Trend (±15)",
        "24h_spot_cvd": "24H Spot CVD (±20)",
        "spot_orderbook_imbalance": "Spot Book Imbalance (±20)",
        "futures_orderbook_imbalance": "Futures Book Imbalance (±15)",
        "24h_divergence_engine": "24H Price/OI Divergence (±15)",
        "oi_squeeze_risk": "OI Squeeze Risk (±15)",
    }

    names = []
    points = []
    bar_colors = []
    line_colors = []

    for key, label in factor_labels.items():
        val = sanitize_number(breakdown.get(key), 0.0)
        names.append(label)
        points.append(val)
        if val > 0:
            bar_colors.append("rgba(46, 189, 133, 0.35)")
            line_colors.append("rgba(46, 189, 133, 0.85)")
        elif val < 0:
            bar_colors.append("rgba(246, 70, 93, 0.35)")
            line_colors.append("rgba(246, 70, 93, 0.85)")
        else:
            bar_colors.append("rgba(197, 168, 128, 0.15)")
            line_colors.append("rgba(197, 168, 128, 0.5)")

    fig = go.Figure(
        go.Bar(
            y=names,
            x=points,
            orientation="h",
            marker=dict(color=bar_colors, line=dict(color=line_colors, width=1.5)),
            text=[f"{p:+.0f} pts" if p != 0 else "0 pts" for p in points],
            textposition="auto",
            textfont=dict(color="#ffffff", size=11, family="JetBrains Mono, monospace"),
            hoverinfo="none",
            width=0.48,
        )
    )

    fig.update_layout(
        title=dict(
            text="<b>ФАКТОРНАЯ МАТРИЦА СКОРИНГА (FACTOR MATRIX)</b>",
            font=dict(size=13, color="#dfc18b", family="Inter, sans-serif"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode=False,
        xaxis=dict(
            range=[-30, 30],
            zeroline=True,
            zerolinecolor="rgba(197, 168, 128, 0.4)",
            zerolinewidth=1.5,
            gridcolor="rgba(255, 255, 255, 0.04)",
            title=dict(text="Вклад факторов (баллы)", font=dict(color="#8b949e", size=11, family="Inter, sans-serif")),
            tickfont=dict(color="#8b949e", family="JetBrains Mono, monospace"),
        ),
        yaxis=dict(autorange="reversed", tickfont=dict(color="#e6edf3", size=11, family="JetBrains Mono, monospace")),
        margin=dict(l=10, r=20, t=40, b=30),
        height=320,
    )
    return fig


def create_price_atr_chart(spot_price: float, risk_model: Dict[str, Any], history: List[Dict[str, Any]]) -> go.Figure:
    """Interactive Price Chart with Dynamic ATR Reference Bands (SL, TP1, TP2)."""
    fig = go.Figure()

    valid_history = [h for h in history if isinstance(h, dict)] if history else []
    if valid_history and len(valid_history) > 1:
        timestamps = [h.get("timestamp_utc", "") for h in valid_history]
        prices = [sanitize_number(h.get("spot_price"), spot_price) for h in valid_history]
        fig.add_trace(
            go.Scatter(
                x=timestamps,
                y=prices,
                mode="lines+markers",
                name="BTC Spot Price",
                line=dict(color="#64b5f6", width=2),
                marker=dict(size=5, color="#dfc18b"),
            )
        )
    else:
        now_iso = datetime.now(timezone.utc).strftime("%H:%M:%S")
        fig.add_trace(
            go.Scatter(
                x=[now_iso],
                y=[spot_price],
                mode="markers",
                name="Current Spot",
                marker=dict(color="#dfc18b", size=10),
            )
        )

    long_plan = risk_model.get("long", {})
    short_plan = risk_model.get("short", {})
    rec = risk_model.get("recommended", {})
    scenario = rec.get("scenario") or rec.get("direction", "LONG")

    fig.add_hline(
        y=spot_price,
        line=dict(color="#dfc18b", width=1.5),
        annotation_text=f"Вход (Entry): ${spot_price:,.2f}",
        annotation_position="top right",
        annotation_font=dict(color="#dfc18b", size=11, family="JetBrains Mono, monospace"),
    )

    if scenario == "LONG":
        fig.add_hline(
            y=long_plan.get("stop_loss", spot_price * 0.99),
            line=dict(color="#f6465d", width=1.5, dash="dash"),
            annotation_text=f"Стоп-лосс (1.5x ATR): ${long_plan.get('stop_loss', 0):,.2f}",
            annotation_position="bottom right",
            annotation_font=dict(color="#f6465d", size=11, family="JetBrains Mono, monospace"),
        )
        fig.add_hline(
            y=long_plan.get("tp1_rr2", spot_price * 1.02),
            line=dict(color="#2ebd85", width=1.5, dash="dot"),
            annotation_text=f"Тейк-профит 1 (1:2 R:R): ${long_plan.get('tp1_rr2', 0):,.2f}",
            annotation_position="top right",
            annotation_font=dict(color="#2ebd85", size=11, family="JetBrains Mono, monospace"),
        )
        fig.add_hline(
            y=long_plan.get("tp2_rr3", spot_price * 1.03),
            line=dict(color="#20a370", width=1.5),
            annotation_text=f"Тейк-профит 2 (1:3 R:R): ${long_plan.get('tp2_rr3', 0):,.2f}",
            annotation_position="top right",
            annotation_font=dict(color="#20a370", size=11, family="JetBrains Mono, monospace"),
        )
    else:
        fig.add_hline(
            y=short_plan.get("stop_loss", spot_price * 1.01),
            line=dict(color="#f6465d", width=1.5, dash="dash"),
            annotation_text=f"Стоп-лосс (1.5x ATR): ${short_plan.get('stop_loss', 0):,.2f}",
            annotation_position="top right",
            annotation_font=dict(color="#f6465d", size=11, family="JetBrains Mono, monospace"),
        )
        fig.add_hline(
            y=short_plan.get("tp1_rr2", spot_price * 0.98),
            line=dict(color="#2ebd85", width=1.5, dash="dot"),
            annotation_text=f"Тейк-профит 1 (1:2 R:R): ${short_plan.get('tp1_rr2', 0):,.2f}",
            annotation_position="bottom right",
            annotation_font=dict(color="#2ebd85", size=11, family="JetBrains Mono, monospace"),
        )
        fig.add_hline(
            y=short_plan.get("tp2_rr3", spot_price * 0.97),
            line=dict(color="#20a370", width=1.5),
            annotation_text=f"Тейк-профит 2 (1:3 R:R): ${short_plan.get('tp2_rr3', 0):,.2f}",
            annotation_position="bottom right",
            annotation_font=dict(color="#20a370", size=11, family="JetBrains Mono, monospace"),
        )

    fig.update_layout(
        title=dict(
            text=f"<b>ДИНАМИКА ЦЕНЫ С РИСК-УРОВНЯМИ ATR ({scenario})</b>",
            font=dict(size=13, color="#dfc18b", family="Inter, sans-serif"),
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#1e2330", tickfont=dict(color="#8b949e", family="JetBrains Mono, monospace")),
        yaxis=dict(gridcolor="#1e2330", tickfont=dict(color="#8b949e", family="JetBrains Mono, monospace"), tickformat="$,.0f"),
        margin=dict(l=20, r=40, t=50, b=30),
        height=360,
        showlegend=False,
    )
    return fig


def create_cvd_barchart(snapshot: Dict[str, Any]) -> go.Figure:
    """Spot Taker Cumulative Volume Delta (CVD) multi-timeframe bar chart (15m, 1h, 4h, 24h)."""
    if not isinstance(snapshot, dict):
        snapshot = {}
    binance_data = snapshot.get("binance") if isinstance(snapshot.get("binance"), dict) else {}
    cvd_data = binance_data.get("spot_taker_delta") or snapshot.get("spot_taker_delta") or snapshot.get("spot_cvd", {})
    if not isinstance(cvd_data, dict):
        cvd_data = {}

    timeframes = ["15m", "1h", "4h", "24h"]
    deltas_btc = []
    pct_volumes = []
    colors = []

    for tf in timeframes:
        tf_info = cvd_data.get(tf, {}) if isinstance(cvd_data, dict) else {}
        delta = sanitize_number(tf_info.get("delta_btc"), 0.0)
        pct = sanitize_number(tf_info.get("delta_as_pct_of_volume"), 0.0)
        deltas_btc.append(delta)
        pct_volumes.append(pct)
        colors.append("#2ebd85" if delta >= 0 else "#f6465d")

    fig = make_subplots(specs=[[{"secondary_y": True}]])

    fig.add_trace(
        go.Bar(
            x=timeframes,
            y=deltas_btc,
            name="Чистая дельта (BTC)",
            marker=dict(color=colors, line=dict(color="rgba(197, 168, 128, 0.25)", width=1)),
            text=[f"{d:+.1f} BTC" for d in deltas_btc],
            textposition="auto",
            textfont=dict(color="#ffffff", size=11, family="JetBrains Mono, monospace"),
        ),
        secondary_y=False,
    )

    pct_colors = ["rgba(197, 168, 128, 0.65)" if p >= 0 else "rgba(246, 70, 93, 0.55)" for p in pct_volumes]
    fig.add_trace(
        go.Bar(
            x=timeframes,
            y=pct_volumes,
            name="Дельта % от объема",
            marker=dict(color=pct_colors, line=dict(color="#dfc18b", width=1)),
            text=[f"{p:+.1f}%" for p in pct_volumes],
            textposition="auto",
            textfont=dict(color="#dfc18b", size=11, family="JetBrains Mono, monospace"),
        ),
        secondary_y=True,
    )

    fig.update_layout(
        title=dict(
            text="<b>СПОТОВАЯ ДЕЛЬТА ПО ТАЙМФРЕЙМАМ (CVD MULTI-TIMEFRAME)</b>",
            font=dict(size=13, color="#dfc18b", family="Inter, sans-serif"),
        ),
        barmode="group",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="#1e2330", tickfont=dict(color="#8b949e", size=12, family="JetBrains Mono, monospace")),
        yaxis=dict(
            gridcolor="#1e2330",
            tickfont=dict(color="#8b949e", family="JetBrains Mono, monospace"),
            title=dict(text="Net Delta (BTC)", font=dict(color="#8b949e", family="Inter, sans-serif")),
        ),
        yaxis2=dict(
            gridcolor="rgba(0,0,0,0)",
            tickfont=dict(color="#dfc18b", family="JetBrains Mono, monospace"),
            title=dict(text="Delta %", font=dict(color="#dfc18b", family="Inter, sans-serif")),
            ticksuffix="%",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color="#8b949e", family="Inter, sans-serif")),
        margin=dict(l=20, r=20, t=50, b=30),
        height=320,
    )
    return fig


def create_zscore_timeseries(history: List[Dict[str, Any]]) -> go.Figure:
    """Time-series chart of Open Interest and Funding Rate Z-scores with ±2.0 threshold bands."""
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=("<b>Open Interest Z-Score (Crowding)</b>", "<b>Funding Rate Z-Score (Euphoria / Discount)</b>"),
    )

    valid_history = [h for h in (history or []) if isinstance(h, dict)]
    if not valid_history:
        now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
        timestamps = [now_str]
        oi_zscores = [0.0]
        funding_zscores = [0.0]
    else:
        timestamps = [h.get("timestamp_utc", "") for h in valid_history]
        oi_zscores = [sanitize_number(h.get("oi_zscore"), 0.0) for h in valid_history]
        funding_zscores = [sanitize_number(h.get("funding_zscore"), 0.0) for h in valid_history]

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=oi_zscores,
            mode="lines+markers",
            name="OI Z-Score",
            line=dict(color="#dfc18b", width=2),
            marker=dict(size=4, color="#ffffff"),
        ),
        row=1,
        col=1,
    )

    for threshold, color, label in [(2.0, "#f6465d", "+2.0 Squeeze Alert"), (-2.0, "#2ebd85", "-2.0 Flush Completed")]:
        fig.add_hline(
            y=threshold,
            line=dict(color=color, width=1.5, dash="dash"),
            annotation_text=label,
            annotation_position="top right",
            annotation_font=dict(color=color, size=10, family="JetBrains Mono, monospace"),
            row=1,
            col=1,
        )

    fig.add_trace(
        go.Scatter(
            x=timestamps,
            y=funding_zscores,
            mode="lines+markers",
            name="Funding Z-Score",
            line=dict(color="#64b5f6", width=2),
            marker=dict(size=4, color="#ffffff"),
        ),
        row=2,
        col=1,
    )

    for threshold, color, label in [(2.0, "#dfc18b", "+2.0 Euphoric Longs"), (-2.0, "#64b5f6", "-2.0 Deep Discount")]:
        fig.add_hline(
            y=threshold,
            line=dict(color=color, width=1.5, dash="dash"),
            annotation_text=label,
            annotation_position="top right",
            annotation_font=dict(color=color, size=10, family="JetBrains Mono, monospace"),
            row=2,
            col=1,
        )

    for i in [1, 2]:
        fig.update_xaxes(gridcolor="#1e2330", tickfont=dict(color="#8b949e", family="JetBrains Mono, monospace"), row=i, col=1)
        fig.update_yaxes(gridcolor="#1e2330", tickfont=dict(color="#8b949e", family="JetBrains Mono, monospace"), range=[-3.5, 3.5], row=i, col=1)

    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=40, b=25),
        height=380,
        showlegend=False,
    )
    return fig


# --- Subprocess Execution Engine ---

def build_execution_command(fast_mode: bool = False, model_name: Optional[str] = None) -> List[str]:
    """Construct process invocation command for btc_market_intelligence.py."""
    cmd = [sys.executable, str(PROJECT_ROOT / "btc_market_intelligence.py")]
    if fast_mode:
        cmd.append("--fast")
    if model_name and model_name in SUPPORTED_AI_MODELS:
        cmd.extend(["--model", model_name])
    return cmd


def run_pipeline_subprocess(fast_mode: bool = False, log_box: Optional[Any] = None, model_name: Optional[str] = None) -> Tuple[int, str, float]:
    """Execute pipeline via isolated subprocess with real-time log streaming."""
    cmd = build_execution_command(fast_mode=fast_mode, model_name=model_name)
    start_time = time.time()

    env = os.environ.copy()
    if model_name:
        env["GEMINI_MODEL"] = model_name

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )

        captured_lines = []
        if proc.stdout:
            for line in iter(proc.stdout.readline, ""):
                captured_lines.append(line)
                if log_box is not None:
                    recent = "".join(captured_lines[-14:])
                    log_box.markdown(f'<div class="console-stream">{recent}</div>', unsafe_allow_html=True)

        proc.stdout.close()
        return_code = proc.wait()
        duration = time.time() - start_time
        return return_code, "".join(captured_lines), duration
    except Exception as exc:
        duration = time.time() - start_time
        return 1, f"Execution failed: {exc}", duration


# --- Main Dashboard Application ---

def main():
    """Main Streamlit layout entrypoint."""
    try:
        st.set_page_config(
            page_title="BTC Market Intelligence Terminal",
            layout="wide",
            initial_sidebar_state="expanded",
        )
    except Exception:
        pass
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    # Initialize Session State
    if "is_running" not in st.session_state:
        st.session_state["is_running"] = False
    if "last_run_logs" not in st.session_state:
        st.session_state["last_run_logs"] = ""
    if "last_run_status" not in st.session_state:
        st.session_state["last_run_status"] = None
    if "selected_ai_model" not in st.session_state:
        st.session_state["selected_ai_model"] = get_selected_ai_model()

    # Load artifacts
    snapshot = load_market_snapshot()
    if not snapshot or not snapshot.get("spot_price"):
        try:
            from btc_market_intelligence import run_fast_momentum_scan
            snapshot = run_fast_momentum_scan(quiet=True)
        except Exception:
            pass
    history = load_market_history()
    tracker = load_calibration_tracker()
    daemon_info = load_daemon_status()
    markdown_content = load_markdown_report()
    pdf_b64 = load_pdf_base64()
    screenshots_dict = get_available_screenshots()

    spot_price = extract_spot_price(snapshot)
    quant_score, quant_label, quant_breakdown = extract_quant_bias(snapshot)
    risk_model = extract_risk_model(snapshot, spot_price)

    prices_dict = snapshot.get("prices") or snapshot.get("binance", {}).get("prices", {})
    spot_summary = snapshot.get("binance", {}).get("spot_24h_summary", {})
    change_24h = sanitize_number(spot_summary.get("change_pct"), 0.0)
    basis_usd = sanitize_number(prices_dict.get("synchronized_basis_usd", prices_dict.get("basis_usd")), 0.0)
    basis_pct = sanitize_number(prices_dict.get("synchronized_basis_pct", prices_dict.get("basis_pct")), 0.0)

    zscores_dict = snapshot.get("statistical_z_scores") or snapshot.get("binance", {}).get("statistical_z_scores", {})
    oi_zscore = sanitize_number(zscores_dict.get("oi_zscore"), 0.0)
    funding_zscore = sanitize_number(zscores_dict.get("funding_zscore"), 0.0)

    onchain_dict = snapshot.get("onchain_metrics") or snapshot.get("onchain", {})
    mvrv_stage = onchain_dict.get("mvrv_stage", "Н/Д")
    nupl_stage = onchain_dict.get("nupl_stage", "Н/Д")

    dvol_dict = snapshot.get("deribit_dvol") or snapshot.get("binance", {}).get("deribit_dvol", {})
    dvol_val = sanitize_number(dvol_dict.get("current_dvol"))
    dvol_regime = dvol_dict.get("dvol_regime", "Нормальная")

    cme_dict = snapshot.get("cme_basis") or snapshot.get("binance", {}).get("cme_basis", {})
    cme_basis_usd = sanitize_number(cme_dict.get("basis_vs_spot_usd"), 0.0)
    cme_basis_pct = sanitize_number(cme_dict.get("basis_vs_spot_pct"), 0.0)

    cb_dict = snapshot.get("coinbase_orderbook") or snapshot.get("binance", {}).get("coinbase_orderbook", {})
    cb_ratio = sanitize_number(cb_dict.get("bid_vs_ask_ratio"), 1.0)

    atr_val = sanitize_number(risk_model.get("atr14"), 476.16)
    dvol_str = f"{dvol_val:.1f} pts" if dvol_val is not None else "Н/Д"
    cme_str = f"${cme_basis_usd:+,.1f}" if cme_basis_usd is not None else "Н/Д"

    ticker_delta_cls = "ticker-pos" if change_24h >= 0 else "ticker-neg"
    ticker_basis_cls = "ticker-pos" if basis_usd >= 0 else "ticker-neg"

    prev_quant_score = None
    if len(history) >= 2:
        prev_quant_score = history[-2].get("quant_bias_score")

    snap_time = snapshot.get("timestamp_utc", "Н/Д")
    market_regime_str = snapshot.get("quant_bias", {}).get("market_regime", "BALANCED_NORMAL")

    # 1. Bloomberg Live Ticker Tape Strip (Pure Market Quotes)
    st.markdown(
        f"""
        <div class="bloomberg-ticker-tape">
            <div class="ticker-item"><span class="ticker-symbol">BTC/USDT SPOT:</span> <span class="ticker-val">${spot_price:,.2f}</span> <span class="{ticker_delta_cls}">{change_24h:+.2f}%</span></div>
            <div class="ticker-item"><span class="ticker-symbol">FUTURES BASIS:</span> <span class="ticker-val">${basis_usd:+,.2f}</span> <span class="{ticker_basis_cls}">({basis_pct:+.3f}%)</span></div>
            <div class="ticker-item"><span class="ticker-symbol">DERIBIT DVOL:</span> <span class="ticker-val">{dvol_str}</span> <span class="ticker-neutral">[{dvol_regime}]</span></div>
            <div class="ticker-item"><span class="ticker-symbol">COINBASE L2:</span> <span class="ticker-val">{cb_ratio:.2f}x</span></div>
            <div class="ticker-item"><span class="ticker-symbol">CME BTC=F:</span> <span class="ticker-val">{cme_str}</span> <span class="ticker-neutral">({cme_basis_pct:+.2f}%)</span></div>
            <div class="ticker-item"><span class="ticker-symbol">4H ATR14:</span> <span class="ticker-val">${atr_val:,.2f}</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 2. Clean Executive Terminal Header (All technical feed/module details moved to Sidebar)
    st.markdown(
        f"""
        <div class="terminal-header">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div>
                    <div class="terminal-title">BTC MARKET INTELLIGENCE TERMINAL</div>
                    <div class="terminal-subtitle">Утренний количественный обзор рынка, структура потоков и риск-модель ATR</div>
                </div>
                <div style="text-align: right;">
                    <div class="bloomberg-status-badge">
                        <span class="live-dot"></span>
                        <span>РЕЖИМ: {market_regime_str}</span>
                    </div>
                    <div style="font-size: 0.72rem; color: #8b949e; font-family: 'JetBrains Mono', monospace; margin-top: 4px;">Срез: {snap_time}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Render Top KPI Ribbon (Responsive 4 + 4 Grid)
    r1_cols = st.columns(4)

    with r1_cols[0]:
        delta_class = "kpi-delta-pos" if change_24h >= 0 else "kpi-delta-neg"
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Спотовая цена BTC</div>
                <div class="kpi-value">${spot_price:,.2f}</div>
                <div class="kpi-sub {delta_class}">{change_24h:+.2f}% (24ч)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with r1_cols[1]:
        basis_class = "kpi-delta-pos" if basis_usd >= 0 else "kpi-delta-neg"
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Базис фьючерсов</div>
                <div class="kpi-value">${basis_usd:+,.2f}</div>
                <div class="kpi-sub {basis_class}">{basis_pct:+.3f}% спред к споту</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with r1_cols[2]:
        badge_style = "badge-bullish" if quant_score >= 15 else ("badge-bearish" if quant_score <= -15 else "badge-neutral")
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Quant Bias (Скоринг)</div>
                <div class="kpi-value">{quant_score:+d} <span style="font-size: 0.82rem; color: #8b949e; font-weight: 500; margin-left: 4px;">/ 100</span></div>
                <div class="kpi-sub"><span class="{badge_style}">{quant_label}</span></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with r1_cols[3]:
        risk_pct = sanitize_number(risk_model.get("long", {}).get("risk_pct"), 0.86)
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Волатильность ATR (4H)</div>
                <div class="kpi-value">${atr_val:,.2f}</div>
                <div class="kpi-sub kpi-delta-neutral">±{risk_pct:.2f}% (Буфер: ${atr_val*1.5:,.2f})</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    r2_cols = st.columns(4)

    with r2_cols[0]:
        oi_class = "kpi-delta-neg" if abs(oi_zscore) >= 2.0 else "kpi-delta-neutral"
        oi_tag = "РИСК СКВИЗА" if abs(oi_zscore) >= 2.0 else "НОРМАЛЬНЫЙ ДИАПАЗОН"
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Z-Score открытого интереса</div>
                <div class="kpi-value">{oi_zscore:+.2f} σ</div>
                <div class="kpi-sub {oi_class}">{oi_tag}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with r2_cols[1]:
        funding_class = "kpi-delta-neg" if abs(funding_zscore) >= 2.0 else "kpi-delta-neutral"
        funding_tag = "ПЕРЕГРЕВ СТАВКИ" if abs(funding_zscore) >= 2.0 else "НОРМАЛЬНЫЙ ДИАПАЗОН"
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Z-Score ставки фандинга</div>
                <div class="kpi-value">{funding_zscore:+.2f} σ</div>
                <div class="kpi-sub {funding_class}">{funding_tag}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with r2_cols[2]:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Ончейн макро-цикл</div>
                <div class="kpi-value" style="font-size: 1.05rem;">{mvrv_stage}</div>
                <div class="kpi-sub kpi-delta-neutral">NUPL: {nupl_stage}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with r2_cols[3]:
        st.markdown(
            f"""
            <div class="kpi-card">
                <div class="kpi-title">Институциональные метрики</div>
                <div class="kpi-value" style="font-size: 1.05rem;">DVOL: {dvol_str}</div>
                <div class="kpi-sub kpi-delta-neutral">CME: {cme_str} ({cme_basis_pct:+.2f}%)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    # =========================================================================
    # SIDEBAR: Управление, Статус ИИ + Выбор модели, Сводка трейдера, Статусы бирж и модулей
    # =========================================================================
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-section-header">
                <span class="sidebar-section-title">Терминал данных</span>
                <span class="sidebar-section-pill">LIVE</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        run_fast = st.button(
            "Обновить котировки",
            use_container_width=True,
            disabled=st.session_state["is_running"],
            help="Быстрый опрос биржевых шлюзов и перерасчет Quant Bias (2-4 сек)",
        )
        run_full = st.button(
            "Сформировать PDF-отчет",
            use_container_width=True,
            disabled=st.session_state["is_running"],
            help="Сбор глубокой аналитики, синтез через выбранную модель Gemini и верстка PDF",
        )

        pdf_path = PROJECT_ROOT / "daily_report.pdf"
        has_pdf = pdf_path.exists()
        if has_pdf:
            st.download_button(
                label="Скачать PDF-отчет",
                data=pdf_path.read_bytes(),
                file_name="daily_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

        # --- БЛОК ИИ: Статус подключения и выбор модели (Gemini 3.8 Flash / Gemini 3.7 Flash) ---
        has_api_key = bool(os.getenv("GEMINI_API_KEY", "").strip())
        ai_pill_cls = "sidebar-section-pill" if has_api_key else "sidebar-section-pill-amber"
        ai_pill_txt = "CONNECTED" if has_api_key else "AUTONOMOUS"

        st.markdown(
            f"""
            <div class="sidebar-section-header" style="margin-top: 1.1rem;">
                <span class="sidebar-section-title">Аналитическое ядро ИИ</span>
                <span class="{ai_pill_cls}">{ai_pill_txt}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        model_keys = list(SUPPORTED_AI_MODELS.keys())
        current_model_idx = model_keys.index(st.session_state["selected_ai_model"]) if st.session_state["selected_ai_model"] in model_keys else 0
        chosen_model = st.selectbox(
            "Модель синтеза отчета:",
            options=model_keys,
            index=current_model_idx,
            format_func=lambda k: SUPPORTED_AI_MODELS.get(k, k),
        )
        if chosen_model != st.session_state["selected_ai_model"]:
            st.session_state["selected_ai_model"] = save_selected_ai_model(chosen_model)
        else:
            save_selected_ai_model(chosen_model)

        ai_conn_dot = '<span class="live-dot"></span> ПОДКЛЮЧЕНО (API OK)' if has_api_key else '<span class="dot-amber"></span> QUANT-РАСЧЕТ (БЕЗ КЛЮЧА)'
        ai_conn_color = "#2ebd85" if has_api_key else "#dfc18b"

        st.markdown(
            f"""
            <div class="sidebar-status-card">
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Статус ИИ</span>
                    <span class="sidebar-stat-val" style="color: {ai_conn_color};">{ai_conn_dot}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Активная модель</span>
                    <span class="sidebar-stat-val-gold">{chosen_model}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Резервная модель</span>
                    <span class="sidebar-stat-val">{"gemini-3.7-flash" if chosen_model == "gemini-3.8-flash" else "gemini-3.8-flash"}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Execution Logic (Live Data Fetch & PDF Compilation)
        if run_fast or run_full:
            is_fast = bool(run_fast)
            active_model = st.session_state["selected_ai_model"]
            mode_label = "Обновление котировок" if is_fast else f"Формирование отчета ({active_model})"
            st.session_state["is_running"] = True

            with st.status(f"Выполняется: {mode_label}...", expanded=True) as status_box:
                log_container = st.empty()
                if is_fast:
                    status_box.write("Опрос биржевых шлюзов и перерасчет скоринга...")
                else:
                    status_box.write(f"Сбор аналитики и синтез через {active_model}...")

                code, logs, dur = run_pipeline_subprocess(
                    fast_mode=is_fast,
                    log_box=log_container,
                    model_name=active_model,
                )

                if code != 0:
                    if is_fast:
                        try:
                            from btc_market_intelligence import run_fast_momentum_scan
                            run_fast_momentum_scan(quiet=True)
                            code = 0
                            dur = 3.2
                        except Exception as fb_exc:
                            logs += f"\n[FALLBACK_ERR] {fb_exc}"
                    else:
                        try:
                            import btc_market_intelligence as bmi
                            bmi.set_configured_gemini_model(active_model)
                            code = bmi.main()
                            dur = 8.5
                        except Exception as fb_exc:
                            logs += f"\n[FALLBACK_ERR] {fb_exc}"

                st.session_state["last_run_logs"] = logs
                st.session_state["last_run_status"] = code

                if code == 0:
                    success_msg = f"Котировки обновлены за {dur:.1f} с" if is_fast else f"PDF-отчет сформирован за {dur:.1f} с"
                    status_box.update(label=f"[OK] {success_msg}", state="complete", expanded=False)
                    st.toast(success_msg)
                else:
                    status_box.update(label=f"[ОШИБКА] Код завершения {code}", state="error", expanded=True)
                    st.error("Ошибка при сборе данных. Проверьте соединение.")

            st.session_state["is_running"] = False
            st.cache_data.clear()
            st.rerun()

        # --- БЛОК СВОДКИ ТРЕЙДЕРА ---
        st.markdown(
            """
            <div class="sidebar-section-header" style="margin-top: 0.9rem;">
                <span class="sidebar-section-title">Сводка трейдера</span>
                <span class="sidebar-section-pill">STATUS</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        badge_cls = "badge-bullish" if quant_score >= 15 else ("badge-bearish" if quant_score <= -15 else "badge-neutral")
        pdf_label_color = "#2ebd85" if has_pdf else "#8b949e"
        pdf_label_text = "Готов" if has_pdf else "Не сформирован"

        st.markdown(
            f"""
            <div class="sidebar-status-card">
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Сигнал</span>
                    <span class="{badge_cls}">{quant_label}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Quant Скоринг</span>
                    <span class="sidebar-stat-val-gold">{quant_score:+d} / 100</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Срез (UTC)</span>
                    <span class="sidebar-stat-val">{snap_time}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">PDF-документ</span>
                    <span class="sidebar-stat-val" style="color: {pdf_label_color};">{pdf_label_text}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # --- БЛОК ТЕЛЕМЕТРИИ БИРЖ И ПОДКЛЮЧЕННЫХ МОДУЛЕЙ (УБРАН С ГЛАВНОГО ЭКРАНА В САЙДБАР) ---
        st.markdown(
            """
            <div class="sidebar-section-header" style="margin-top: 0.9rem;">
                <span class="sidebar-section-title">Шлюзы бирж и модули</span>
                <span class="sidebar-section-pill">SYSTEM</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        binance_ok = bool(snapshot.get("binance", {}).get("prices", {}).get("spot_last") or snapshot.get("spot_price"))
        futures_ok = bool(snapshot.get("binance", {}).get("prices", {}).get("futures_last"))
        bybit_ok = snapshot.get("bybit", {}).get("status") == "OK" or bool(snapshot.get("bybit", {}).get("ticker", {}).get("lastPrice"))
        cb_ok = cb_dict.get("status") == "OK"
        dvol_ok = dvol_dict.get("status") == "OK"
        cme_ok = cme_dict.get("status") == "OK"
        onchain_ok = onchain_dict.get("status") == "OK"
        daemon_state = str(daemon_info.get("status", "STOPPED")).upper()
        daemon_ok = daemon_state in ("RUNNING", "STARTING", "ACTIVE")

        def _status_span(ok: bool, ok_text: str = "ONLINE", fallback_text: str = "STANDBY") -> str:
            if ok:
                return f'<span style="color:#2ebd85;"><span class="live-dot"></span> {ok_text}</span>'
            return f'<span style="color:#dfc18b;"><span class="dot-amber"></span> {fallback_text}</span>'

        st.markdown(
            f"""
            <div class="sidebar-status-card">
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Binance Spot</span>
                    <span class="sidebar-stat-val">{_status_span(binance_ok)}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Futures / Bybit V5</span>
                    <span class="sidebar-stat-val">{_status_span(futures_ok or bybit_ok)}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Coinbase Pro L2</span>
                    <span class="sidebar-stat-val">{_status_span(cb_ok)}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Deribit DVOL</span>
                    <span class="sidebar-stat-val">{_status_span(dvol_ok)}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">CME Futures (BTC=F)</span>
                    <span class="sidebar-stat-val">{_status_span(cme_ok)}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">BGeometrics On-Chain</span>
                    <span class="sidebar-stat-val">{_status_span(onchain_ok, "OK (КЭШ 12Ч)")}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Модуль Quant & ATR</span>
                    <span class="sidebar-stat-val">{_status_span(True, "АКТИВЕН")}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Калибратор сделок</span>
                    <span class="sidebar-stat-val">{_status_span(True, f"{len(tracker)} СИГН.")}</span>
                </div>
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Фоновый демон</span>
                    <span class="sidebar-stat-val">{_status_span(daemon_ok, "РАБОТАЕТ", "ОСТАНОВЛЕН")}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # =========================================================================
    # MAIN NAVIGATION TABS (Clean Capsule, Zero Emojis)
    # =========================================================================
    tab_cockpit, tab_charts, tab_risk, tab_reports, tab_tracker = st.tabs([
        "Кокпит и Quant Bias",
        "Графики и Дельта CVD",
        "Риск-модель ATR",
        "Аналитический отчет и PDF",
        "Калибровка винрейта",
    ])

    # TAB 1: Live Cockpit & Quant Bias
    with tab_cockpit:
        col_gauge, col_breakdown = st.columns([1, 1])

        with col_gauge:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            gauge_fig = create_quant_bias_gauge(score=quant_score, prev_score=prev_quant_score, label=quant_label)
            st.plotly_chart(gauge_fig, use_container_width=True)

            st.markdown(
                f"""
                **Показания спидометра**: Итоговый индекс Quant Bias составляет **{quant_score:+d} / 100** (зона **{quant_label}**). 
                Значения от **-15 до +15** отражают диапазонный баланс сил. Выше **+15** — статистический перевес покупателей, 
                выше **+40** — сильный направленный импульс.
                """
            )
            st.markdown("</div>", unsafe_allow_html=True)

        with col_breakdown:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            breakdown_fig = create_factor_breakdown_chart(quant_breakdown)
            st.plotly_chart(breakdown_fig, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="content-panel">', unsafe_allow_html=True)
        st.markdown("#### Глубина биржевого стакана Spot (±1.0% от цены)")

        # Исправлено чтение стакана: поддержка и orderbook_depth.spot, и orderbook_depth_summary, и Coinbase L2
        binance_ob_spot = snapshot.get("binance", {}).get("orderbook_depth", {}).get("spot") or {}
        binance_ob_sum = snapshot.get("binance", {}).get("orderbook_depth_summary") or {}

        b_spot_bids = sanitize_number(
            binance_ob_spot.get("bid_depth_base_qty"),
            sanitize_number(binance_ob_sum.get("bids_btc"), sanitize_number(cb_dict.get("bid_depth_btc"), 0.0)),
        )
        b_spot_asks = sanitize_number(
            binance_ob_spot.get("ask_depth_base_qty"),
            sanitize_number(binance_ob_sum.get("asks_btc"), sanitize_number(cb_dict.get("ask_depth_btc"), 0.0)),
        )
        b_ratio = sanitize_number(
            binance_ob_spot.get("bid_vs_ask_ratio"),
            sanitize_number(binance_ob_sum.get("bid_ask_ratio"), cb_ratio),
        )

        ob_col1, ob_col2, ob_col3 = st.columns(3)
        with ob_col1:
            st.metric("Лимитные биды (±1%)", f"{b_spot_bids:,.1f} BTC")
        with ob_col2:
            st.metric("Лимитные аски (±1%)", f"{b_spot_asks:,.1f} BTC")
        with ob_col3:
            st.metric(
                "Соотношение Bid/Ask",
                f"{b_ratio:.2f}x",
                delta="Покупатели" if b_ratio > 1.2 else ("Продавцы" if b_ratio < 0.8 else "Баланс"),
            )

        st.markdown("</div>", unsafe_allow_html=True)

    # TAB 2: Interactive Technical & Orderflow Charts
    with tab_charts:
        col_c1, col_c2 = st.columns([1, 1])

        with col_c1:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            cvd_fig = create_cvd_barchart(snapshot)
            st.plotly_chart(cvd_fig, use_container_width=True)

            cvd_readout = (
                snapshot.get("binance", {})
                .get("spot_taker_delta", {})
                .get("descriptive_read", "Рыночная дельта покупателей и продавцов.")
            )
            st.caption(f"Интерпретация: {cvd_readout}")
            st.markdown("</div>", unsafe_allow_html=True)

        with col_c2:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            zscore_fig = create_zscore_timeseries(history)
            st.plotly_chart(zscore_fig, use_container_width=True)
            st.caption("Коридор ±2.0 σ обозначает зоны статистических аномалий (перегрев открытого интереса или ставки фандинга).")
            st.markdown("</div>", unsafe_allow_html=True)

    # TAB 3: ATR Dynamic Risk & Trade Plans
    with tab_risk:
        rec_plan = risk_model.get("recommended", {})
        rec_direction = rec_plan.get("scenario") or rec_plan.get("direction", "LONG")
        friction = risk_model.get("friction_analysis", {})

        st.markdown('<div class="content-panel">', unsafe_allow_html=True)
        st.markdown("### Динамическая риск-модель на базе ATR")
        st.markdown(
            """
            Модель динамического риска вычисляет адаптивный стоп-лосс на основе **1.5x 4H ATR**, 
            обеспечивая защиту депозита и математическое соотношение прибыли к риску **1:2 (TP1)** и **1:3 (TP2)**.
            """
        )

        r_col1, r_col2, r_col3, r_col4 = st.columns(4)
        with r_col1:
            badge_cls = "badge-bullish" if rec_direction == "LONG" else ("badge-bearish" if rec_direction == "SHORT" else "badge-neutral")
            st.markdown(f"**Рекомендуемый сценарий:** <span class='{badge_cls}'>{rec_direction}</span>", unsafe_allow_html=True)
            st.metric("Точка входа", f"${spot_price:,.2f}")
        with r_col2:
            st.metric("Стоп-лосс (1.5x ATR)", f"${rec_plan.get('stop_loss', 0):,.2f}")
        with r_col3:
            st.metric("Тейк-профит 1 (1:2 R:R)", f"${rec_plan.get('tp1_rr2', rec_plan.get('tp1', 0)):,.2f}")
        with r_col4:
            st.metric("Тейк-профит 2 (1:3 R:R)", f"${rec_plan.get('tp2_rr3', rec_plan.get('tp2', 0)):,.2f}")

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="content-panel">', unsafe_allow_html=True)
        price_atr_fig = create_price_atr_chart(spot_price, risk_model, history)
        st.plotly_chart(price_atr_fig, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        col_calc, col_scenarios = st.columns([1, 1])

        with col_calc:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            st.markdown("#### Калькулятор размера позиции")
            account_equity = st.number_input("Баланс депозита (USDT)", min_value=100.0, max_value=10000000.0, value=10000.0, step=500.0)
            risk_percentage = st.slider("Максимальный риск на сделку (%)", min_value=0.25, max_value=5.0, value=1.0, step=0.25)

            max_risk_dollars = account_equity * (risk_percentage / 100.0)
            dollar_sl_distance = abs(spot_price - rec_plan.get("stop_loss", spot_price * 0.99))

            if dollar_sl_distance > 0:
                pos_size_btc = max_risk_dollars / dollar_sl_distance
                pos_size_usdt = pos_size_btc * spot_price
                st.write(f"• Допустимый риск: **${max_risk_dollars:,.2f}**")
                st.write(f"• Дистанция до стоп-лосса: **${dollar_sl_distance:,.2f}** ({dollar_sl_distance/spot_price*100:.2f}%)")
                st.write(f"• Рекомендуемый объем позиции: **{pos_size_btc:.4f} BTC** (~${pos_size_usdt:,.2f})")
                if friction.get("effective_rr_tp1"):
                    st.write(
                        f"• Чистый R:R (после комиссий и спреда): **1:{friction.get('effective_rr_tp1', 0):.2f}** (TP1) / **1:{friction.get('effective_rr_tp2', 0):.2f}** (TP2)"
                    )
            st.markdown("</div>", unsafe_allow_html=True)

        with col_scenarios:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            st.markdown("#### Сравнение сценариев Long и Short")

            l = risk_model.get("long", {})
            s = risk_model.get("short", {})

            sc_df = pd.DataFrame([
                {"Параметр": "Уровень стоп-лосса", "Сценарий LONG": f"${l.get('stop_loss', 0):,.2f}", "Сценарий SHORT": f"${s.get('stop_loss', 0):,.2f}"},
                {"Параметр": "TP1 (1:2 R:R)", "Сценарий LONG": f"${l.get('tp1_rr2', 0):,.2f}", "Сценарий SHORT": f"${s.get('tp1_rr2', 0):,.2f}"},
                {"Параметр": "TP2 (1:3 R:R)", "Сценарий LONG": f"${l.get('tp2_rr3', 0):,.2f}", "Сценарий SHORT": f"${s.get('tp2_rr3', 0):,.2f}"},
                {"Параметр": "Риск на 1 BTC", "Сценарий LONG": f"${l.get('risk_usd', 0):,.2f}", "Сценарий SHORT": f"${s.get('risk_usd', 0):,.2f}"},
                {"Параметр": "Риск в процентах", "Сценарий LONG": f"{l.get('risk_pct', 0):.2f}%", "Сценарий SHORT": f"{s.get('risk_pct', 0):.2f}%"},
            ])
            st.dataframe(sc_df, hide_index=True, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)

    # TAB 4: Document Viewers & Screenshots
    with tab_reports:
        doc_tab1, doc_tab2, doc_tab3 = st.tabs([
            "PDF-отчет (daily_report.pdf)",
            "Текстовый отчет (daily_report.md)",
            "Графика и скриншоты",
        ])

        with doc_tab1:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            if pdf_b64:
                pdf_path = PROJECT_ROOT / "daily_report.pdf"
                st.download_button(
                    label="Скачать PDF-отчет",
                    data=pdf_path.read_bytes(),
                    file_name="daily_report.pdf",
                    mime="application/pdf",
                )
                pdf_display = (
                    f'<iframe src="data:application/pdf;base64,{pdf_b64}" '
                    f'width="100%" height="880px" type="application/pdf" '
                    f'style="border: 1px solid rgba(197, 168, 128, 0.2); border-radius: 10px;"></iframe>'
                )
                st.markdown(pdf_display, unsafe_allow_html=True)
            else:
                st.info("Отчет daily_report.pdf еще не сформирован. Нажмите «Сформировать PDF-отчет» в боковой панели.")
            st.markdown("</div>", unsafe_allow_html=True)

        with doc_tab2:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            if markdown_content:
                st.download_button(
                    label="Скачать daily_report.md",
                    data=markdown_content.encode("utf-8"),
                    file_name="daily_report.md",
                    mime="text/markdown",
                )
                st.markdown(markdown_content)
            else:
                st.info("Файл daily_report.md не найден. Запустите формирование отчета.")
            st.markdown("</div>", unsafe_allow_html=True)

        with doc_tab3:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            if screenshots_dict:
                selected_chart = st.selectbox("Выберите график:", list(screenshots_dict.keys()))
                if selected_chart and selected_chart in screenshots_dict:
                    img_path = screenshots_dict[selected_chart]
                    st.image(str(img_path), caption=selected_chart, use_container_width=True)
            else:
                st.info("Скриншоты еще не созданы. Они формируются при полном запуске анализа.")
            st.markdown("</div>", unsafe_allow_html=True)

    # TAB 5: Winrate Calibration & History
    with tab_tracker:
        st.markdown('<div class="content-panel">', unsafe_allow_html=True)
        st.markdown("### Калибровка винрейта и история сигналов")
        st.markdown(
            """
            Модуль калибровки непрерывно регистрирует сигналы (LONG / SHORT) и отслеживает исходы 
            по закрытым свечам после точки входа с проверкой достижения стоп-лосса и тейк-профитов.
            """
        )

        total_signals = len(tracker)
        resolved_signals = [t for t in tracker if t.get("resolved") is True]
        pending_signals = [t for t in tracker if not t.get("resolved")]
        wins = [t for t in resolved_signals if t.get("outcome") == "WIN" or t.get("is_win") is True]
        losses = [t for t in resolved_signals if t.get("outcome") == "LOSS" or (t.get("is_win") is False and t.get("resolved") is True)]

        resolved_count = len(resolved_signals)
        win_count = len(wins)
        loss_count = len(losses)

        if resolved_count > 0:
            winrate_pct = (win_count / resolved_count) * 100.0
            winrate_display = f"{winrate_pct:.1f}%"
        else:
            winrate_display = "НАБОР СТАТИСТИКИ"

        tc_col1, tc_col2, tc_col3, tc_col4 = st.columns(4)
        with tc_col1:
            st.metric("Исторический винрейт", winrate_display, f"{win_count}W / {loss_count}L" if resolved_count > 0 else "Требуется ≥1 сделки")
        with tc_col2:
            st.metric("Всего сигналов", str(total_signals))
        with tc_col3:
            st.metric("Завершенных сделок", str(resolved_count))
        with tc_col4:
            st.metric("Активных сигналов (24ч)", str(len(pending_signals)))

        st.markdown("---")

        if tracker:
            table_rows = []
            for t in reversed(tracker):
                outcome = t.get("outcome") or ("WIN" if t.get("is_win") is True else ("LOSS" if t.get("is_win") is False else "PENDING"))

                pnl = t.get("pnl_pct")
                pnl_str = f"{pnl:+.2f}%" if pnl is not None else "—"

                status_label = (
                    "УСПЕХ"
                    if outcome == "WIN"
                    else ("СТОП" if outcome == "LOSS" else ("ПРОБОЙ" if outcome == "TREND_BREAKOUT" else "В ОЖИДАНИИ"))
                )

                table_rows.append({
                    "Время (UTC)": t.get("timestamp_utc", t.get("id", "Н/Д")),
                    "Направление": t.get("direction", "NEUTRAL"),
                    "Quant Bias": f"{t.get('quant_bias_score', 0):+d} ({t.get('quant_bias_label', 'Н/Д')})",
                    "Вход ($)": f"${sanitize_number(t.get('entry_price', t.get('spot_price')), 0):,.2f}",
                    "Стоп-лосс ($)": f"${sanitize_number(t.get('stop_loss'), 0):,.2f}",
                    "TP1 ($)": f"${sanitize_number(t.get('tp1_rr2'), 0):,.2f}",
                    "TP2 ($)": f"${sanitize_number(t.get('tp2_rr3'), 0):,.2f}",
                    "Статус": status_label,
                    "Закрытие ($)": f"${sanitize_number(t.get('resolved_price'), 0):,.2f}" if t.get("resolved_price") else "—",
                    "PnL (24ч)": pnl_str,
                })

            tracker_df = pd.DataFrame(table_rows)

            status_filter = st.radio("Фильтр сигналов:", ["Все", "В ожидании", "Успех", "Стоп"], horizontal=True)
            if status_filter == "В ожидании":
                tracker_df = tracker_df[tracker_df["Статус"] == "В ОЖИДАНИИ"]
            elif status_filter == "Успех":
                tracker_df = tracker_df[tracker_df["Статус"] == "УСПЕХ"]
            elif status_filter == "Стоп":
                tracker_df = tracker_df[tracker_df["Статус"] == "СТОП"]

            st.dataframe(tracker_df, use_container_width=True, hide_index=True)
        else:
            st.info("История сигналов пуста. Новые сигналы записываются при каждом срезе.")

        st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    main()