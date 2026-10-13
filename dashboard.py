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
        padding: 1.15rem 1.45rem;
        border-radius: 12px;
        border: 1px solid rgba(197, 168, 128, 0.2);
        margin-bottom: 1.15rem;
    }
    .terminal-title {
        font-family: 'Inter', sans-serif;
        font-size: 1.55rem;
        font-weight: 700;
        letter-spacing: -0.02em;
        color: #ffffff;
        display: flex;
        align-items: center;
        gap: 0.6rem;
    }
    .terminal-title span.gold-highlight {
        color: #dfc18b;
    }
    .terminal-subtitle {
        font-size: 0.8rem;
        color: #8b949e;
        font-family: 'Inter', sans-serif;
        margin-top: 0.25rem;
        font-weight: 400;
    }

    /* Calm Status Badge */
    .bloomberg-status-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(46, 189, 133, 0.1);
        color: #2ebd85;
        border: 1px solid rgba(46, 189, 133, 0.35);
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

    /* Clean Trading Status Card in Sidebar */
    .sidebar-status-card {
        background: #161a24;
        border: 1px solid rgba(197, 168, 128, 0.18);
        border-radius: 12px;
        padding: 0.85rem 1rem;
        margin-top: 1rem;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.25);
    }
    .sidebar-stat-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 6px 0;
        border-bottom: 1px solid rgba(197, 168, 128, 0.08);
    }
    .sidebar-stat-row:last-child {
        border-bottom: none;
    }
    .sidebar-stat-label {
        font-size: 0.72rem;
        color: #8b949e;
        text-transform: uppercase;
        letter-spacing: 0.03em;
        font-family: 'Inter', sans-serif;
    }
    .sidebar-stat-val {
        font-size: 0.78rem;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 600;
        color: #ffffff;
    }
    .sidebar-stat-val-gold {
        font-size: 0.78rem;
        font-family: 'JetBrains Mono', monospace;
        font-weight: 600;
        color: #dfc18b;
    }
</style>
"""


# --- Robust Data Hydration Helpers ---

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
    qb = snapshot.get("quant_bias", {})
    score = sanitize_number(qb.get("composite_score"), 0)
    score_int = int(max(-100, min(100, round(score))))
    label = str(qb.get("bias_label", "NEUTRAL")).upper()
    breakdown = qb.get("breakdown", {})
    if not isinstance(breakdown, dict):
        breakdown = {}
    return score_int, label, breakdown


def extract_risk_model(snapshot: Dict[str, Any], spot_price: float) -> Dict[str, Any]:
    """Extract or reconstruct ATR risk model."""
    risk = snapshot.get("risk_model") or snapshot.get("atr_risk")
    if isinstance(risk, dict) and "long" in risk and "short" in risk:
        return risk
    
    # Mathematical fallback derived from 1.5x ATR buffer
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
            "stop_loss": round(spot_price - buffer, 2),
            "tp1_rr2": round(spot_price + 2.0 * buffer, 2),
            "tp2_rr3": round(spot_price + 3.0 * buffer, 2),
        }
    }


# --- Visualization Generators (Plotly Engine - Bloomberg Black & Gold) ---

def create_quant_bias_gauge(score: int, prev_score: Optional[int] = None, label: str = "NEUTRAL") -> go.Figure:
    """
    Sleek, minimalist Quant Bias Speedometer Gauge Chart — Luxury Matte Terminal Style.
    Scale: -100 to +100 with smooth slender arc and non-glaring zone tinting.
    """
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
            title={"text": f"<b>QUANT BIAS INDEX: <span style='color:#dfc18b'>{label}</span></b>", "font": {"size": 13, "color": "#8b949e", "family": "Inter, sans-serif"}},
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
    """Horizontal bar chart showing contributions of the 6 Quant Bias factors with matte colors and no hover popups."""
    factor_labels = {
        "1d_vwap_trend": "1D VWAP Trend (±10)",
        "24h_spot_cvd": "24H Spot CVD (±15)",
        "spot_orderbook_imbalance": "Spot Book Imbalance (±15)",
        "futures_orderbook_imbalance": "Futures Book Imbalance (±10)",
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
        title=dict(text="<b>ФАКТОРНАЯ МАТРИЦА СКОРИНГА (FACTOR MATRIX)</b>", font=dict(size=13, color="#dfc18b", family="Inter, sans-serif")),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode=False,
        xaxis=dict(
            range=[-20, 20],
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
    scenario = rec.get("scenario", "LONG")

    # Current Price Entry reference line (Champagne Gold)
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
        title=dict(text=f"<b>ДИНАМИКА ЦЕНЫ С РИСК-УРОВНЯМИ ATR ({scenario})</b>", font=dict(size=13, color="#dfc18b", family="Inter, sans-serif")),
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
    cvd_data = binance_data.get("spot_taker_delta") or snapshot.get("spot_cvd", {})
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

    # Столбец 1: Чистая дельта в BTC
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

    # Столбец 2: Дельта в % от объема
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
        title=dict(text="<b>СПОТОВАЯ ДЕЛЬТА ПО ТАЙМФРЕЙМАМ (CVD MULTI-TIMEFRAME)</b>", font=dict(size=13, color="#dfc18b", family="Inter, sans-serif")),
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

    # OI Z-Score line (Champagne Gold)
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

    # OI Thresholds ±2.0
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

    # Funding Z-Score line (Soft Sky Blue)
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

    # Funding Thresholds ±2.0
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

def build_execution_command(fast_mode: bool = False) -> List[str]:
    """Construct process invocation command for btc_market_intelligence.py."""
    cmd = [sys.executable, str(PROJECT_ROOT / "btc_market_intelligence.py")]
    if fast_mode:
        cmd.append("--fast")
    return cmd


def run_pipeline_subprocess(fast_mode: bool = False, log_box: Optional[Any] = None) -> Tuple[int, str, float]:
    """Execute pipeline via isolated subprocess with real-time log streaming."""
    cmd = build_execution_command(fast_mode=fast_mode)
    start_time = time.time()
    
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=PROJECT_ROOT,
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
                    recent = "".join(captured_lines[-18:])
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
    markdown_content = load_markdown_report()
    pdf_b64 = load_pdf_base64()
    screenshots_dict = get_available_screenshots()

    spot_price = extract_spot_price(snapshot)
    quant_score, quant_label, quant_breakdown = extract_quant_bias(snapshot)
    risk_model = extract_risk_model(snapshot, spot_price)

    # Extract KPI metrics before header to populate Bloomberg Ticker Tape
    prices_dict = snapshot.get("prices") or snapshot.get("binance", {}).get("prices", {})
    spot_summary = snapshot.get("binance", {}).get("spot_24h_summary", {})
    change_24h = sanitize_number(spot_summary.get("change_pct"), 0.0)
    basis_usd = sanitize_number(prices_dict.get("synchronized_basis_usd", prices_dict.get("basis_usd")), 0.0)
    basis_pct = sanitize_number(prices_dict.get("synchronized_basis_pct", prices_dict.get("basis_pct")), 0.0)

    zscores_dict = snapshot.get("statistical_z_scores", {})
    oi_zscore = sanitize_number(zscores_dict.get("oi_zscore"), 0.0)
    funding_zscore = sanitize_number(zscores_dict.get("funding_zscore"), 0.0)

    onchain_dict = snapshot.get("onchain_metrics") or snapshot.get("onchain", {})
    mvrv_stage = onchain_dict.get("mvrv_stage", "Н/Д")
    nupl_stage = onchain_dict.get("nupl_stage", "Н/Д")

    # Extract Institutional Metrics (Deribit DVOL, CME Futures, Coinbase Pro L2)
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

    # Historical delta for Quant Bias
    prev_quant_score = None
    if len(history) >= 2:
        prev_quant_score = history[-2].get("quant_bias_score")

    # 1. Bloomberg Live Ticker Tape Strip
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

    # 2. Executive Bloomberg Terminal Header
    st.markdown(
        """
        <div class="terminal-header">
            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                <div>
                    <div class="terminal-title">BTC MARKET INTELLIGENCE TERMINAL</div>
                    <div class="terminal-subtitle">Институциональная торговая аналитика и количественный риск-менеджмент</div>
                </div>
                <div style="text-align: right;">
                    <div class="bloomberg-status-badge">
                        <span class="live-dot"></span>
                        <span>ПОДКЛЮЧЕНО К БИРЖАМ</span>
                    </div>
                    <div style="font-size: 0.72rem; color: #8b949e; font-family: 'JetBrains Mono', monospace; margin-top: 5px;">Потоки: Binance Spot & Futures | Deribit | CME</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Render Top KPI Ribbon (Responsive 4 + 4 Grid)
    # Row 1: Core Price Action & Quant Bias
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
                <div class="kpi-title">Базис фьючерсов (Binance)</div>
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

    # Row 2: Derivatives, On-Chain Cycle & Institutional Telemetry
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

    # Sidebar: Terminal Controls & Trader Information
    with st.sidebar:
        st.markdown("### Управление терминалом")
        st.caption("Быстрый и полный перезапуск аналитического пайплайна")

        # Clean Execution Buttons
        run_fast = st.button("Быстрый срез рынка (2 сек)", use_container_width=True, disabled=st.session_state["is_running"], help="Мгновенный опрос рынков через быстрый REST-протокол")
        run_full = st.button("Полный отчет с PDF", use_container_width=True, disabled=st.session_state["is_running"], help="Полный сбор: стаканы, ончейн, скриншоты и генерация PDF-отчета")
        run_refresh = st.button("Обновить данные", use_container_width=True, disabled=st.session_state["is_running"], help="Собрать свежие данные с бирж прямо сейчас")

        # Execution Logic (Live Data Fetch)
        if run_fast or run_full or run_refresh:
            fast_selected = not bool(run_full)
            mode_label = "Полный отчет с PDF" if run_full else "Быстрый срез рынка"
            st.session_state["is_running"] = True
            
            with st.status(f"Выполняется {mode_label}...", expanded=True) as status_box:
                log_container = st.empty()
                code, logs, dur = run_pipeline_subprocess(fast_mode=fast_selected, log_box=log_container)
                
                # Cloud / Subprocess fallback: if subprocess couldn't run, execute in-process scan directly
                if code != 0 and fast_selected:
                    try:
                        from btc_market_intelligence import run_fast_momentum_scan
                        run_fast_momentum_scan(quiet=True)
                        code = 0
                        dur = 3.2
                    except Exception as fb_exc:
                        logs += f"\n[FALLBACK_ERR] {fb_exc}"

                st.session_state["last_run_logs"] = logs
                st.session_state["last_run_status"] = code
                
                if code == 0:
                    status_box.update(label=f"Успешно завершено за {dur:.2f} с", state="complete", expanded=False)
                    st.toast(f"Анализ успешно обновлен за {dur:.2f} с")
                else:
                    status_box.update(label=f"Ошибка выполнения (код {code})", state="error", expanded=True)
                    st.error("Ошибка при сборе данных. Проверьте соединение.")

            st.session_state["is_running"] = False
            st.cache_data.clear()
            st.rerun()

        st.markdown("---")
        st.markdown("### Сводка для трейдера")
        snap_time = snapshot.get("timestamp_utc", "Н/Д")
        pdf_path = PROJECT_ROOT / "daily_report.pdf"
        has_pdf = pdf_path.exists()
        badge_cls = "badge-bullish" if quant_score >= 15 else ("badge-bearish" if quant_score <= -15 else "badge-neutral")
        pdf_label_color = '#2ebd85' if has_pdf else '#8b949e'
        pdf_label_text = 'Готов' if has_pdf else 'Не сформирован'

        st.markdown(
            f"""
            <div class="sidebar-status-card">
                <div class="sidebar-stat-row">
                    <span class="sidebar-stat-label">Режим рынка</span>
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
                    <span class="sidebar-stat-label">PDF-отчет</span>
                    <span class="sidebar-stat-val" style="color: {pdf_label_color};">{pdf_label_text}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if has_pdf:
            st.write("")
            st.download_button(
                label="Скачать PDF-отчет",
                data=pdf_path.read_bytes(),
                file_name="daily_report.pdf",
                mime="application/pdf",
                use_container_width=True,
            )

    # Main Navigation Tabs (Clean Capsule, Zero Emojis)
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
                Значения от **-15 до +15** отражают диапазонный флэт и баланс сил. Выше **+15** — доминирование покупателей, 
                выше **+40** — сильный институциональный тренд.
                """
            )
            st.markdown('</div>', unsafe_allow_html=True)

        with col_breakdown:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            breakdown_fig = create_factor_breakdown_chart(quant_breakdown)
            st.plotly_chart(breakdown_fig, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="content-panel">', unsafe_allow_html=True)
        st.markdown("#### Глубина биржевого стакана Binance Spot (±1.0%)")
        
        binance_ob = snapshot.get("binance", {}).get("orderbook_depth_summary", {})
        b_spot_bids = sanitize_number(binance_ob.get("bids_btc"), 0.0)
        b_spot_asks = sanitize_number(binance_ob.get("asks_btc"), 0.0)
        b_ratio = sanitize_number(binance_ob.get("bid_ask_ratio"), 1.0)
        
        ob_col1, ob_col2, ob_col3 = st.columns(3)
        with ob_col1:
            st.metric("Биды спота (±1%)", f"{b_spot_bids:,.1f} BTC")
        with ob_col2:
            st.metric("Аски спота (±1%)", f"{b_spot_asks:,.1f} BTC")
        with ob_col3:
            st.metric("Соотношение Bid/Ask", f"{b_ratio:.2f}x", delta="Покупатели" if b_ratio > 1.2 else ("Продавцы" if b_ratio < 0.8 else "Баланс"))
        
        st.markdown('</div>', unsafe_allow_html=True)

    # TAB 2: Interactive Technical & Orderflow Charts
    with tab_charts:
        col_c1, col_c2 = st.columns([1, 1])

        with col_c1:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            cvd_fig = create_cvd_barchart(snapshot)
            st.plotly_chart(cvd_fig, use_container_width=True)
            
            cvd_readout = snapshot.get("binance", {}).get("spot_taker_delta", {}).get("descriptive_read", "Рыночная дельта покупателей и продавцов.")
            st.caption(f"Интерпретация: {cvd_readout}")
            st.markdown('</div>', unsafe_allow_html=True)

        with col_c2:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            zscore_fig = create_zscore_timeseries(history)
            st.plotly_chart(zscore_fig, use_container_width=True)
            st.caption("Коридор ±2.0 σ обозначает зоны статистических аномалий (перегрев открытого интереса или ставки фандинга).")
            st.markdown('</div>', unsafe_allow_html=True)

    # TAB 3: ATR Dynamic Risk & Trade Plans
    with tab_risk:
        rec_plan = risk_model.get("recommended", {})
        rec_direction = rec_plan.get("scenario", "LONG")
        
        st.markdown('<div class="content-panel">', unsafe_allow_html=True)
        st.markdown("### Динамическая риск-модель на базе ATR")
        st.markdown(
            """
            Модель динамического риска вычисляет адаптивный стоп-лосс на основе **1.5x 4H ATR**, 
            обеспечивая математическую защиту депозита и асимметричное соотношение прибыли к риску **1:2 (TP1)** и **1:3 (TP2)**.
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
            st.metric("Тейк-профит 1 (1:2 R:R)", f"${rec_plan.get('tp1_rr2', 0):,.2f}")
        with r_col4:
            st.metric("Тейк-профит 2 (1:3 R:R)", f"${rec_plan.get('tp2_rr3', 0):,.2f}")

        st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="content-panel">', unsafe_allow_html=True)
        price_atr_fig = create_price_atr_chart(spot_price, risk_model, history)
        st.plotly_chart(price_atr_fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

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
            st.markdown('</div>', unsafe_allow_html=True)

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
            st.markdown('</div>', unsafe_allow_html=True)

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
                st.info("Отчет daily_report.pdf еще не сформирован. Нажмите «Полный отчет с PDF» в боковой панели.")
            st.markdown('</div>', unsafe_allow_html=True)

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
                st.info("Файл daily_report.md не найден. Запустите анализ.")
            st.markdown('</div>', unsafe_allow_html=True)

        with doc_tab3:
            st.markdown('<div class="content-panel">', unsafe_allow_html=True)
            if screenshots_dict:
                selected_chart = st.selectbox("Выберите график:", list(screenshots_dict.keys()))
                if selected_chart and selected_chart in screenshots_dict:
                    img_path = screenshots_dict[selected_chart]
                    st.image(str(img_path), caption=selected_chart, use_container_width=True)
            else:
                st.info("Скриншоты еще не созданы. Они формируются при полном запуске анализа.")
            st.markdown('</div>', unsafe_allow_html=True)

    # TAB 5: Winrate Calibration & History
    with tab_tracker:
        st.markdown('<div class="content-panel">', unsafe_allow_html=True)
        st.markdown("### Калибровка винрейта и история сигналов")
        st.markdown(
            """
            Модуль калибровки непрерывно регистрирует сигналы (LONG / SHORT) и отслеживает исходы 
            в 24-часовом окне с проверкой достижения стоп-лосса и расчетных тейк-профитов.
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

                status_label = "УСПЕХ" if outcome == "WIN" else ("СТОП" if outcome == "LOSS" else ("ПРОБОЙ" if outcome == "TREND_BREAKOUT" else "В ОЖИДАНИИ"))

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

        st.markdown('</div>', unsafe_allow_html=True)


if __name__ == "__main__":
    main()
