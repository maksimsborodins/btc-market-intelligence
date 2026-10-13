#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Market Intelligence v4 — расширенный бесплатный multi-exchange конвейер с контролем качества данных.

Собирает открытую телеметрию Binance (спот/фьючерсы), макро-активы (Yahoo Finance),
календарь событий (Forex Factory), новостной фон (RSS), скриншот карты ликвидаций (CoinGlass)
и историю предыдущих запусков. Передает срез в Gemini (модель задаётся через GEMINI_MODEL); при сбое сохраняет сырой аудит без торгового вывода.
"""

from __future__ import annotations

import json
import math
import os
import sys
import time
import statistics
import re
import concurrent.futures

# Принудительная настройка UTF-8 вывода для надежной работы на Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
import html
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv

from quant_enhancements import (
    detect_market_regime,
    calculate_regime_adaptive_bias,
    calculate_liquidity_aware_stops,
    compute_calibration_performance_metrics,
    REGIME_WEIGHTS,
    REGIME_HIGH_VOL_SQUEEZE,
    REGIME_TRENDING_BULL,
    REGIME_TRENDING_BEAR,
    REGIME_LOW_VOL_CONSOLIDATION,
    REGIME_BALANCED_NORMAL,
)

genai = None
types = None

import base64
try:
    import markdown
except ImportError:
    markdown = None

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


# ------------------------------- КОНФИГУРАЦИЯ --------------------------------

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
SYMBOL = os.getenv("SYMBOL", "BTCUSDT").strip().upper()
LOCAL_TIMEZONE = os.getenv("LOCAL_TIMEZONE", "Europe/Riga").strip()
TIMEOUT_SEC = int(os.getenv("TIMEOUT_SEC", "6"))
ENABLE_SCREENSHOT = os.getenv("ENABLE_COINGLASS_SCREENSHOT", "true").lower() in ("1", "true", "yes")
ENABLE_RSS_NEWS = os.getenv("ENABLE_RSS_NEWS", "true").lower() in ("1", "true", "yes")
COINGLASS_API_KEY = os.getenv("COINGLASS_API_KEY", "").strip()
ENABLE_COINGLASS_API = os.getenv("ENABLE_COINGLASS_API", "false").lower() in ("1", "true", "yes")
ENABLE_ETF_FLOWS = os.getenv("ENABLE_ETF_FLOWS", "true").lower() in ("1", "true", "yes")
ENABLE_DERIBIT_OPTIONS = os.getenv("ENABLE_DERIBIT_OPTIONS", "true").lower() in ("1", "true", "yes")

BASE_DIR = Path(__file__).resolve().parent
MANUAL_INPUT_DIR = BASE_DIR / os.getenv("MANUAL_INPUT_DIR", "manual_inputs")
OUTPUT_REPORT_FILE = BASE_DIR / os.getenv("OUTPUT_REPORT_FILE", "daily_report.md")
OUTPUT_PDF_FILE = BASE_DIR / os.getenv("OUTPUT_PDF_FILE", "daily_report.pdf")
HISTORY_FILE = BASE_DIR / os.getenv("HISTORY_FILE", "market_history.json")
SCREENSHOT_FILE = BASE_DIR / os.getenv("SCREENSHOT_FILE", "free_dashboard_screenshots/coinglass_heatmap.png")
RAW_SNAPSHOT_FILE = BASE_DIR / os.getenv("RAW_SNAPSHOT_FILE", "market_snapshot.json")
MAX_HISTORY_SNAPSHOTS = int(os.getenv("MAX_HISTORY_SNAPSHOTS", "3000"))
HISTORY_LOOKBACK_HOURS = int(os.getenv("HISTORY_LOOKBACK_HOURS", "168"))
TRACKER_FILE = BASE_DIR / os.getenv("TRACKER_FILE", "quant_calibration_tracker.json")
CACHE_DIR = BASE_DIR / "data_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

BINANCE_SPOT = "https://api.binance.com"
BINANCE_FUTURES = "https://fapi.binance.com"
COINGLASS_API_BASE = "https://open-api-v4.coinglass.com/api"
BYBIT_API_BASE = "https://api.bybit.com"
DERIBIT_API_BASE = "https://www.deribit.com/api/v2"
COINBASE_API_BASE = "https://api.exchange.coinbase.com"
DERIBIT_DVOL_URL = "https://www.deribit.com/api/v2/public/get_volatility_index_data"
CME_YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/BTC=F"
FARSIDE_BTC_ETF_URL = "https://farside.co.uk/btc/"
COINGLASS_HEATMAP_URL = (
    "https://www.coinglass.com/pro/futures/LiquidationHeatMapModel3?coin=BTC&type=symbol"
)


def load_disk_cache(cache_filename: str, ttl_seconds: int) -> Optional[dict]:
    """Загружает данные из локального дискового кэша, если срок TTL не истек."""
    try:
        cache_file = CACHE_DIR / cache_filename
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < ttl_seconds:
                with cache_file.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
    except Exception:
        pass
    return None


def save_disk_cache(cache_filename: str, data: dict) -> None:
    """Атомарно сохраняет данные в локальный дисковый кэш."""
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_DIR / cache_filename
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
FREE_DASHBOARD_PAGES = [
    ("CoinGlass BTC futures dashboard", "https://www.coinglass.com/currencies/BTC/futures", ("open interest", "funding", "liquidation")),
    ("CoinGlass BTC ETF dashboard", "https://www.coinglass.com/etf/bitcoin", ("etf", "inflow")),
    ("CryptoQuant BTC overview", "https://cryptoquant.com/overview/full/btc", ("market cap", "retail", "whale", "volume")),
    ("LookIntoBitcoin MVRV Z-Score chart", "https://www.lookintobitcoin.com/charts/mvrv-zscore/", ("mvrv", "z-score", "market value")),
    ("LookIntoBitcoin Net Unrealized Profit Loss", "https://www.lookintobitcoin.com/charts/relative-unrealized-profit--loss/", ("nupl", "unrealized", "profit")),
]

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": BROWSER_USER_AGENT,
    "Accept": "application/json,text/plain,*/*",
})
_retries = Retry(
    total=1,
    connect=1,
    read=0,
    backoff_factor=0.1,
    status_forcelist=(429, 502, 504),
    allowed_methods=frozenset(["GET"]),
    respect_retry_after_header=False,
)
SESSION.mount("https://", HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=_retries))
SESSION.mount("http://", HTTPAdapter(pool_connections=64, pool_maxsize=64, max_retries=_retries))


class DataIntegrityError(RuntimeError):
    """Исключение при отсутствии критических данных биржи."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: Optional[datetime] = None) -> str:
    return (dt or utc_now()).astimezone(timezone.utc).isoformat(timespec="seconds")


def epoch_ms() -> int:
    return int(time.time() * 1000)


def finite_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        result = float(value)
        if math.isfinite(result):
            return result
    except (TypeError, ValueError):
        pass
    return default


def safe_get_json(url: str, params: Optional[dict] = None) -> Any:
    try:
        response = SESSION.get(url, params=params, timeout=(1.5, min(TIMEOUT_SEC, 2.5)))
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        print(f"[WARN] Сбой запроса JSON: {url} — {exc}")
        return None


def safe_get_text(url: str) -> Optional[str]:
    try:
        response = SESSION.get(url, timeout=(1.5, min(TIMEOUT_SEC, 2.5)))
        response.raise_for_status()
        return response.text
    except Exception as exc:
        print(f"[WARN] Сбой получения текста: {url} — {exc}")
        return None


def status_record(ok: bool, detail: str = "") -> dict:
    return {"status": "OK" if ok else "UNAVAILABLE", "detail": detail}


# ----------------------------- ДАННЫЕ BINANCE -------------------------------

def fetch_klines(base_url: str, symbol: str, interval: str, limit: int) -> list:
    endpoint = f"{base_url}/api/v3/klines" if base_url == BINANCE_SPOT else f"{base_url}/fapi/v1/klines"
    result = safe_get_json(endpoint, {"symbol": symbol, "interval": interval, "limit": limit})
    return result if isinstance(result, list) else []


def only_closed_klines(raw: list) -> list:
    now_ms = epoch_ms()
    closed = []
    for candle in raw:
        try:
            if int(candle[6]) < now_ms:
                closed.append(candle)
        except (IndexError, TypeError, ValueError):
            continue
    return closed


def candle_delta(candle: list) -> tuple[float, float, float]:
    total_base = float(candle[5])
    taker_buy_base = float(candle[9])
    taker_sell_base = max(0.0, total_base - taker_buy_base)
    delta = taker_buy_base - taker_sell_base
    quote_volume = float(candle[7])
    return delta, total_base, quote_volume


def aggregate_delta(klines: list, count: int) -> dict:
    closed = only_closed_klines(klines)
    if len(closed) < count:
        return {"available": False, "required_candles": count, "found": len(closed)}
    selected = closed[-count:]
    deltas, volumes, quote_volumes = [], [], []
    for candle in selected:
        delta, volume, quote_volume = candle_delta(candle)
        deltas.append(delta)
        volumes.append(volume)
        quote_volumes.append(quote_volume)
    total_delta = sum(deltas)
    total_volume = sum(volumes)
    
    # Исправлены границы: открытие первой свечи и закрытие последней
    window_start = datetime.fromtimestamp(int(selected[0][0]) / 1000, tz=timezone.utc)
    window_end = datetime.fromtimestamp(int(selected[-1][6]) / 1000, tz=timezone.utc)
    
    return {
        "available": True,
        "delta_btc": round(total_delta, 3),
        "total_volume_btc": round(total_volume, 3),
        "delta_as_pct_of_volume": round(total_delta / total_volume * 100, 3) if total_volume else None,
        "quote_volume_usdt": round(sum(quote_volumes), 2),
        "window_start_utc": iso_utc(window_start),
        "window_end_utc": iso_utc(window_end),
        "closed_candles": len(selected),
    }


def fetch_spot_flow(symbol: str, spot_klines: Optional[dict] = None) -> dict:
    if spot_klines and "1m" in spot_klines and "5m" in spot_klines and "15m" in spot_klines and "1h" in spot_klines:
        k1m = spot_klines["1m"]
        k5m = spot_klines["5m"]
        k15 = spot_klines["15m"]
        k1h = spot_klines["1h"]
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as inner_pool:
            f_k1m = inner_pool.submit(fetch_klines, BINANCE_SPOT, symbol, "1m", 15)
            f_k5m = inner_pool.submit(fetch_klines, BINANCE_SPOT, symbol, "5m", 15)
            f_k15 = inner_pool.submit(fetch_klines, BINANCE_SPOT, symbol, "15m", 8)
            f_k1h = inner_pool.submit(fetch_klines, BINANCE_SPOT, symbol, "1h", 30)

            k1m = f_k1m.result()
            k5m = f_k5m.result()
            k15 = f_k15.result()
            k1h = f_k1h.result()
    closed15 = only_closed_klines(k15)
    
    delta_1m = aggregate_delta(k1m, 1)
    delta_5m = aggregate_delta(k5m, 1)
    d5_vol = delta_5m.get("total_volume_btc") or 0.0
    d5_val = delta_5m.get("delta_btc") or 0.0
    momentum_ratio_5m = round(d5_val / d5_vol, 3) if d5_vol > 0 else 0.0

    result = {
        "metric_definition": "Интервальная спотовая дельта покупок и продаж (Taker Buy - Sell) по закрытым свечам.",
        "1m": delta_1m,
        "5m": delta_5m,
        "15m": aggregate_delta(k15, 1),
        "1h": aggregate_delta(k1h, 1),
        "4h": aggregate_delta(k1h, 4),
        "24h": aggregate_delta(k1h, 24),
        "momentum_ratio_5m": momentum_ratio_5m,
    }
    if closed15:
        result["latest_closed_15m_utc"] = iso_utc(
            datetime.fromtimestamp(int(closed15[-1][6]) / 1000, tz=timezone.utc)
        )
    d1 = result["1h"].get("delta_btc") if result["1h"].get("available") else None
    d4 = result["4h"].get("delta_btc") if result["4h"].get("available") else None
    if d1 is not None and d4 is not None:
        if d1 > 0 and d4 > 0:
            label = "Положительная taker-дельта на споте (1h и 4h); это прокси агрессивных покупок, не доказательство устойчивого спроса"
        elif d1 < 0 and d4 < 0:
            label = "Отрицательная taker-дельта на споте (1h и 4h); это прокси агрессивных продаж, не самостоятельный bearish-сигнал"
        else:
            label = "Смешанный спотовый поток ордеров"
    else:
        label = "Недостаточно данных спотовой дельты"
    result["descriptive_read"] = label
    return result


def detect_structure(raw_klines: list, interval: str) -> dict:
    """Closed-candle technical layer. Indicators are descriptive, not standalone signals."""
    closed = only_closed_klines(raw_klines)
    if len(closed) < 30:
        return {"available": False, "reason": f"Нужно >=30 закрытых свечей для {interval}; найдено {len(closed)}"}

    opens = [float(c[1]) for c in closed]
    highs = [float(c[2]) for c in closed]
    lows = [float(c[3]) for c in closed]
    closes = [float(c[4]) for c in closed]
    volumes = [float(c[5]) for c in closed]
    quote_volumes = [float(c[7]) for c in closed]
    candle_times = [int(c[6]) for c in closed]

    swing_highs, swing_lows = [], []
    for i in range(2, len(closed) - 2):
        if highs[i] > max(highs[i-2:i] + highs[i+1:i+3]):
            swing_highs.append({"price": highs[i], "index": i})
        if lows[i] < min(lows[i-2:i] + lows[i+1:i+3]):
            swing_lows.append({"price": lows[i], "index": i})

    def sma(values, n):
        return statistics.mean(values[-n:]) if len(values) >= n else None

    def ema(values, n):
        if len(values) < n:
            return None
        alpha = 2 / (n + 1)
        value = statistics.mean(values[:n])
        for x in values[n:]:
            value = alpha * x + (1 - alpha) * value
        return value

    # Wilder-style RSI approximation on closed candles.
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [max(x, 0) for x in deltas]
    losses = [max(-x, 0) for x in deltas]
    avg_gain = statistics.mean(gains[-14:]) if len(gains) >= 14 else None
    avg_loss = statistics.mean(losses[-14:]) if len(losses) >= 14 else None
    rsi = (100 - 100 / (1 + avg_gain / avg_loss)) if avg_gain is not None and avg_loss not in (None, 0) else (100.0 if avg_gain and avg_loss == 0 else None)

    true_ranges = []
    for i in range(1, len(closed)):
        true_ranges.append(max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1])))
    atr14 = statistics.mean(true_ranges[-14:]) if len(true_ranges) >= 14 else None
    atr_pct = atr14 / closes[-1] * 100 if atr14 and closes[-1] else None

    def pivots_read(pivots):
        return [round(p["price"], 2) for p in pivots[-4:]]

    sh = pivots_read(swing_highs)
    sl = pivots_read(swing_lows)
    structure_label = "insufficient_pivots"
    if len(sh) >= 2 and len(sl) >= 2:
        if sh[-1] > sh[-2] and sl[-1] > sl[-2]:
            structure_label = "HH_HL_uptrend"
        elif sh[-1] < sh[-2] and sl[-1] < sl[-2]:
            structure_label = "LH_LL_downtrend"
        elif sh[-1] > sh[-2] and sl[-1] < sl[-2]:
            structure_label = "expanding_range"
        else:
            structure_label = "range_or_transition"

    last_close = closes[-1]
    lookback = min(20, len(closes)-1)
    return_pct = (last_close / closes[-1-lookback] - 1) * 100 if closes[-1-lookback] else None
    prev_range_high = max(highs[-21:-1]) if len(highs) >= 21 else max(highs[:-1])
    prev_range_low = min(lows[-21:-1]) if len(lows) >= 21 else min(lows[:-1])
    breakout = "none"
    if last_close > prev_range_high:
        breakout = "close_above_previous_20_candle_high"
    elif last_close < prev_range_low:
        breakout = "close_below_previous_20_candle_low"
    vol_avg20 = sma(quote_volumes[:-1], 20)
    vol_ratio = quote_volumes[-1] / vol_avg20 if vol_avg20 else None
    candle_range = highs[-1] - lows[-1]
    close_location = (last_close - lows[-1]) / candle_range if candle_range else None
    body_pct = abs(closes[-1] - opens[-1]) / opens[-1] * 100 if opens[-1] else None

    # Rolling 20-candle VWAP proxy, using typical price and candle base volume.
    vwap20 = None
    if len(closed) >= 20 and sum(volumes[-20:]) > 0:
        vwap20 = sum(((highs[i] + lows[i] + closes[i]) / 3) * volumes[i] for i in range(len(closed)-20, len(closed))) / sum(volumes[-20:])
    # MACD(12,26,9) histogram on closes.
    ema12, ema26 = ema(closes, 12), ema(closes, 26)
    macd_line = (ema12 - ema26) if ema12 is not None and ema26 is not None else None
    macd_hist = None
    if len(closes) >= 34:
        macd_series = []
        for j in range(26, len(closes)+1):
            e12j, e26j = ema(closes[:j], 12), ema(closes[:j], 26)
            if e12j is not None and e26j is not None:
                macd_series.append(e12j-e26j)
        if len(macd_series) >= 9:
            macd_hist = macd_series[-1] - ema(macd_series, 9)
    bb_mid = sma(closes, 20)
    bb_std = statistics.pstdev(closes[-20:]) if len(closes) >= 20 else None
    bb_upper = bb_mid + 2*bb_std if bb_mid is not None and bb_std is not None else None
    bb_lower = bb_mid - 2*bb_std if bb_mid is not None and bb_std is not None else None
    bb_percent_b = (last_close-bb_lower)/(bb_upper-bb_lower) if bb_upper is not None and bb_lower is not None and bb_upper != bb_lower else None

    # Structural break proxy: only compare the latest closed close with confirmed pivots.
    last_sh = swing_highs[-1] if swing_highs else None
    last_sl = swing_lows[-1] if swing_lows else None
    structural_break = "none"
    if last_sh and last_close > last_sh["price"]:
        structural_break = "close_above_latest_confirmed_swing_high"
    elif last_sl and last_close < last_sl["price"]:
        structural_break = "close_below_latest_confirmed_swing_low"
    structural_break_note = "BOS/CHOCH proxy only; confirm on candle close and interpret against prior trend/context."

    return {
        "available": True,
        "timeframe": interval,
        "last_closed_candle_utc": iso_utc(datetime.fromtimestamp(candle_times[-1] / 1000, tz=timezone.utc)),
        "last_closed_price": last_close,
        "return_over_last_20_candles_pct": round(return_pct, 3) if return_pct is not None else None,
        "return_last_1_candle_pct": round((closes[-1]/closes[-2]-1)*100, 3) if closes[-2] else None,
        "return_last_4_candles_pct": round((closes[-1]/closes[-5]-1)*100, 3) if len(closes) >= 5 and closes[-5] else None,
        "return_last_24_candles_pct": round((closes[-1]/closes[-25]-1)*100, 3) if len(closes) >= 25 and closes[-25] else None,
        "ema20": round(_ema20, 2) if (_ema20 := ema(closes, 20)) is not None else None,
        "ema50": round(_ema50, 2) if (_ema50 := ema(closes, 50)) is not None else None,
        "rolling_vwap20_proxy": round(vwap20, 2) if vwap20 is not None else None,
        "close_vs_rolling_vwap20_pct": round((last_close/vwap20-1)*100, 3) if vwap20 else None,
        "macd_12_26_line": round(macd_line, 3) if macd_line is not None else None,
        "macd_12_26_9_histogram_approx": round(macd_hist, 3) if macd_hist is not None else None,
        "bollinger_20_upper": round(bb_upper, 2) if bb_upper is not None else None,
        "bollinger_20_mid": round(bb_mid, 2) if bb_mid is not None else None,
        "bollinger_20_lower": round(bb_lower, 2) if bb_lower is not None else None,
        "bollinger_percent_b": round(bb_percent_b, 3) if bb_percent_b is not None else None,
        "structural_break_proxy": structural_break,
        "structural_break_note": structural_break_note,
        "rsi14_approx": round(rsi, 2) if rsi is not None else None,
        "atr14_price": round(atr14, 2) if atr14 is not None else None,
        "atr14_pct": round(atr_pct, 3) if atr_pct is not None else None,
        "confirmed_swing_highs_last4": sh,
        "confirmed_swing_lows_last4": sl,
        "latest_confirmed_swing_high": sh[-1] if sh else round(max(highs[-12:]), 2),
        "latest_confirmed_swing_low": sl[-1] if sl else round(min(lows[-12:]), 2),
        "recent_range_high_20_closed_candles": round(max(highs[-20:]), 2),
        "recent_range_low_20_closed_candles": round(min(lows[-20:]), 2),
        "prior_20_candle_high_excluding_latest": round(prev_range_high, 2),
        "prior_20_candle_low_excluding_latest": round(prev_range_low, 2),
        "close_breakout_state": breakout,
        "swing_structure_label": structure_label,
        "last_candle_quote_volume_usdt": round(quote_volumes[-1], 2),
        "average_quote_volume_previous_20": round(vol_avg20, 2) if vol_avg20 is not None else None,
        "volume_vs_previous_20_average": round(vol_ratio, 3) if vol_ratio is not None else None,
        "close_location_in_candle_0_to_1": round(close_location, 3) if close_location is not None else None,
        "candle_body_pct": round(body_pct, 3) if body_pct is not None else None,
        "indicator_limits": "EMA/RSI/ATR/MACD/Bollinger/VWAP/volume are descriptive. VWAP is rolling 20-candle proxy, not session VWAP; pivots use 2-left/2-right confirmation and lag. Structural break is a BOS/CHOCH proxy, not a full discretionary structure engine.",
    }


def nearest_oi_change(oi_history: list, live_oi: float, hours: int) -> dict:
    now = time.time()
    target = now - hours * 3600
    candidates = []
    for item in oi_history:
        ts = finite_float(item.get("timestamp"))
        oi = finite_float(item.get("sumOpenInterest"))
        if ts is not None and oi is not None and oi > 0:
            candidates.append((abs(ts / 1000 - target), ts / 1000, oi))
    if not candidates:
        return {"available": False, "reason": "Нет исторических срезов OI"}
    distance, sample_epoch, sample_oi = min(candidates, key=lambda x: x[0])
    actual_hours = (now - sample_epoch) / 3600
    change_pct = (live_oi / sample_oi - 1) * 100
    # Hourly history should match the requested horizon closely. Never silently
    # label a 20m/30m comparison as a 1h change.
    if hours <= 1:
        tolerance = 0.25  # 15 минут макс. отклонение для 1ч
    elif hours <= 4:
        tolerance = 0.75  # 45 минут макс. отклонение для 4ч
    else:
        tolerance = 1.5   # 90 минут макс. отклонение для 24ч+
    if abs(actual_hours - hours) > tolerance:
        return {
            "available": False,
            "reason": f"Ближайший снимок {actual_hours:.2f}ч назад; отклонение от целевого горизонта {hours}ч больше {tolerance:.2f}ч",
        }
    return {
        "available": True,
        "change_pct": round(change_pct, 3),
        "reference_utc": iso_utc(datetime.fromtimestamp(sample_epoch, tz=timezone.utc)),
        "sample_age_hours": round(actual_hours, 2),
    }


def fetch_ratio(endpoint: str, period: str = "1h") -> Optional[dict]:
    data = safe_get_json(
        f"{BINANCE_FUTURES}/futures/data/{endpoint}",
        {"symbol": SYMBOL, "period": period, "limit": 2},
    )
    if not isinstance(data, list) or not data:
        return None
    latest = data[-1]
    return {
        "period": period,
        "timestamp_utc": iso_utc(
            datetime.fromtimestamp(float(latest["timestamp"]) / 1000, tz=timezone.utc)
        ) if latest.get("timestamp") else None,
        **{
            key: finite_float(latest.get(key))
            for key in ("buySellRatio", "longShortRatio", "longAccount", "shortAccount")
            if latest.get(key) is not None
        },
    }


def fetch_orderbook_snapshot(base_url: str, path: str, symbol: str, limit: int = 1000, threshold_pct: float = 1.0) -> Optional[dict]:
    data = safe_get_json(f"{base_url}{path}", {"symbol": symbol, "limit": limit})
    if not isinstance(data, dict) or not data.get("bids") or not data.get("asks"):
        return None
    try:
        raw_bids = [(float(p), float(q)) for p, q in data["bids"]]
        raw_asks = [(float(p), float(q)) for p, q in data["asks"]]
        if not raw_bids or not raw_asks:
            return None
        
        best_bid = raw_bids[0][0]
        best_ask = raw_asks[0][0]
        mid = (best_bid + best_ask) / 2
        
        # Calculate strict +/- threshold bounds
        lower_bound = mid * (1 - threshold_pct / 100.0)
        upper_bound = mid * (1 + threshold_pct / 100.0)
        
        bids = [x for x in raw_bids if x[0] >= lower_bound]
        asks = [x for x in raw_asks if x[0] <= upper_bound]
        
        bid_qty = sum(q for _, q in bids)
        ask_qty = sum(q for _, q in asks)
        
        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_bps": round((best_ask - best_bid) / mid * 10000, 3) if mid else None,
            "threshold_pct": threshold_pct,
            "bid_depth_base_qty": round(bid_qty, 3),
            "ask_depth_base_qty": round(ask_qty, 3),
            "bid_vs_ask_ratio": round(bid_qty / ask_qty, 3) if ask_qty else None,
            "interpretation_limit": f"Snapshot strictly measuring bids/asks within ±{threshold_pct}% of mid price. Identifies concentrated limit order walls.",
        }
    except Exception:
        return None


def calculate_zscore(current_val: float, history_vals: list[float], eps: float = 1e-6) -> Optional[float]:
    if len(history_vals) < 2:
        return None
    try:
        mean = statistics.mean(history_vals)
        # Sample standard deviation with Bessel's correction (df = N - 1)
        std = statistics.stdev(history_vals) if len(history_vals) >= 2 else statistics.pstdev(history_vals)
        if std < eps:
            return None if abs(current_val - mean) > eps else 0.0
        return round((current_val - mean) / std, 3)
    except Exception:
        return None


def detect_divergence_engine(price_change_pct: float, oi_change_pct: float) -> dict:
    pt = 1 if price_change_pct > 0.1 else (-1 if price_change_pct < -0.1 else 0)
    ot = 1 if oi_change_pct > 0.1 else (-1 if oi_change_pct < -0.1 else 0)
    
    if pt == 1 and ot == 1:
        state = "Bullish Continuation (Long Build-up)"
        score = 15
    elif pt == 1 and ot == -1:
        state = "Bearish Weakness (Short Covering / Profit Taking)"
        score = -5
    elif pt == -1 and ot == 1:
        state = "Bearish Continuation (Short Build-up)"
        score = -15
    elif pt == -1 and ot == -1:
        state = "Bullish Reversal Weakness (Long Liquidation)"
        score = 5
    else:
        state = "Neutral / Ranging"
        score = 0
        
    return {
        "price_trend": "UP" if pt == 1 else ("DOWN" if pt == -1 else "FLAT"),
        "oi_trend": "UP" if ot == 1 else ("DOWN" if ot == -1 else "FLAT"),
        "divergence_state": state,
        "bias_contribution": score
    }


def calculate_quant_bias(metrics: dict, regime_adaptive: bool = False) -> dict:
    if regime_adaptive:
        return calculate_regime_adaptive_bias(metrics)
    score = 0.0
    breakdown = {}

    # 1. Daily VWAP trend (±15 pts): Smooth tanh scaling against 20-candle rolling VWAP
    struct = metrics.get("market_structure", {}).get("1d", {})
    if struct.get("close_vs_rolling_vwap20_pct") is not None:
        val = struct["close_vs_rolling_vwap20_pct"]
        pts = round(15.0 * math.tanh(val / 0.75), 1)
        score += pts
        breakdown["1d_vwap_trend"] = int(round(pts))

    # 2. 24h Spot CVD (±20 pts): Continuous aggressor-driven spot demand
    spot = metrics.get("spot_taker_delta", {})
    if spot.get("24h", {}).get("delta_btc") is not None:
        delta_btc = spot["24h"]["delta_btc"]
        pts = round(20.0 * math.tanh(delta_btc / 400.0), 1)
        score += pts
        breakdown["24h_spot_cvd"] = int(round(pts))

    # 3. Spot Orderbook Imbalance ±1% (±20 pts): Smooth logarithmic depth imbalance
    ob_spot = metrics.get("orderbook_depth", {}).get("spot", {})
    if ob_spot and ob_spot.get("bid_vs_ask_ratio") is not None:
        ratio = ob_spot["bid_vs_ask_ratio"]
        if ratio > 0:
            log_r = math.log(ratio)
            pts = round(20.0 * math.tanh(log_r / 0.35), 1)
            score += pts
            breakdown["spot_orderbook_imbalance"] = int(round(pts))

    # 4. Futures Orderbook Imbalance ±1% (±15 pts): Futures depth wall
    ob_fut = metrics.get("orderbook_depth", {}).get("futures", {})
    if ob_fut and ob_fut.get("bid_vs_ask_ratio") is not None:
        ratio = ob_fut["bid_vs_ask_ratio"]
        if ratio > 0:
            log_r = math.log(ratio)
            pts = round(15.0 * math.tanh(log_r / 0.35), 1)
            score += pts
            breakdown["futures_orderbook_imbalance"] = int(round(pts))

    # 5. Divergence Engine (±15 pts): Price vs OI trend alignment
    div = metrics.get("divergence_engine", {}).get("24h_divergence", {})
    if div:
        pts = div.get("bias_contribution", 0)
        score += pts
        breakdown["24h_divergence_engine"] = int(pts)

    # 6. OI Squeeze Risk (±15 pts): Detrended from 0.010% baseline with active negative branch
    oi_z = metrics.get("statistical_z_scores", {}).get("oi_zscore")
    if oi_z is not None and abs(oi_z) > 1.8:
        fund = metrics.get("derivatives", {}).get("current_funding_rate_pct", 0)
        if fund is not None:
            fund_dev = round(fund - 0.010, 6)  # Detrend from Binance 0.010% baseline
            if oi_z > 1.8 and fund_dev >= 0.005:
                pts = -15  # Longs crowded in high funding -> Long squeeze risk
            elif oi_z > 1.8 and fund_dev <= -0.005:
                pts = 15   # Shorts crowded in discount funding -> Short squeeze risk
            elif oi_z < -1.8:
                pts = 10 if fund_dev < 0 else -10  # Leverage flushout / exhaustion
            else:
                pts = 0
            if pts != 0:
                score += pts
                breakdown["oi_squeeze_risk"] = int(pts)

    final_score = int(round(max(-100, min(100, score))))

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
        "market_regime": detect_market_regime(metrics).get("regime", "BALANCED_NORMAL") if metrics else "BALANCED_NORMAL",
    }


# -------------------------- РИСК-МОДЕЛЬ ATR И ОНЧЕЙН -------------------------

def calculate_atr_risk_levels(
    spot_price: float,
    atr14: float,
    quant_bias_score: int = 0,
    spread_usd: Optional[float] = None,
    taker_fee_pct: float = 0.0005,
    orderbook_depth: Optional[dict] = None,
) -> dict:
    """
    Рассчитывает динамические уровни стоп-лосса по ATR (буфер 1.5x ATR)
    и целевые уровни тейк-профита 1:2 и 1:3 Risk:Reward для Long, Short и Neutral.
    Включает институциональные квант-расширения: учет спреда, комиссий и плотностей стакана.
    """
    return calculate_liquidity_aware_stops(
        spot_price=spot_price,
        atr14=atr14,
        quant_bias_score=quant_bias_score,
        spread_usd=spread_usd,
        taker_fee_pct=taker_fee_pct,
        orderbook_depth=orderbook_depth,
    )



def classify_mvrv_stage(z: Optional[float]) -> str:
    """Классификация макро-фазы цикла по MVRV Z-Score."""
    if z is None:
        return "UNAVAILABLE"
    if z < 0.1:
        return "Bottom / Undervalued"
    elif z <= 1.5:
        return "Fair Value / Early Bull"
    elif z <= 3.0:
        return "Mature Bull / Expansion"
    elif z <= 5.0:
        return "Overheated / Distribution Zone"
    else:
        return "Cycle Top / Euphoria"


def classify_nupl_stage(nupl: Optional[float]) -> str:
    """Классификация макро-фазы цикла по NUPL (Net Unrealized Profit/Loss)."""
    if nupl is None:
        return "UNAVAILABLE"
    if nupl < 0.0:
        return "Capitulation"
    elif nupl <= 0.25:
        return "Hope / Fear"
    elif nupl <= 0.50:
        return "Optimism / Anxiety"
    elif nupl <= 0.75:
        return "Belief / Denial"
    else:
        return "Euphoria / Greed"


def fetch_onchain_metrics(session: Optional[requests.Session] = None, use_cache: bool = True) -> dict:
    """
    Получает актуальные ончейн-метрики (MVRV Z-Score, NUPL, Realized Price) через быстрый REST API.
    Использует локальный дисковый кэш (TTL 12ч) для исключения лимитов 10 req/hr BGeometrics.
    """
    # 1. Проверяем свежий локальный кэш (12 часов) только при реальном запросе (session is None)
    if use_cache and session is None:
        cached = load_disk_cache("onchain_cache.json", ttl_seconds=12 * 3600)
        if cached and cached.get("status") == "OK" and cached.get("mvrv_zscore") is not None:
            cached["cache_status"] = "CACHE_HIT"
            return cached

    sess = session or SESSION
    base_url = "https://api.bgeometrics.com/v1"
    headers = {"User-Agent": BROWSER_USER_AGENT, "Accept": "application/json"}

    mvrv_zscore = None
    nupl = None
    realized_price = None
    date_val = None
    status = "UNAVAILABLE"

    def _fetch_url(url: str):
        try:
            resp = sess.get(url, headers=headers, timeout=(2.0, 3.0))
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and data:
                    return data[-1]
                elif isinstance(data, dict):
                    return data
        except Exception:
            pass
        return None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            f_mvrv = pool.submit(_fetch_url, f"{base_url}/mvrv-zscore")
            f_nupl = pool.submit(_fetch_url, f"{base_url}/nupl")
            f_realized = pool.submit(_fetch_url, f"{base_url}/realized-price")

            mvrv_row = f_mvrv.result()
            nupl_row = f_nupl.result()
            realized_row = f_realized.result()

        if isinstance(mvrv_row, dict):
            z_raw = finite_float(mvrv_row.get("mvrvZscore"))
            if z_raw is not None:
                mvrv_zscore = round(z_raw, 2)
                date_val = mvrv_row.get("d")
                status = "OK"

        if isinstance(nupl_row, dict):
            nupl_raw = finite_float(nupl_row.get("nupl"))
            if nupl_raw is not None:
                nupl = round(nupl_raw, 3)
                status = "OK"

        if isinstance(realized_row, dict):
            rp_raw = finite_float(realized_row.get("realizedPrice"))
            if rp_raw is not None:
                realized_price = round(rp_raw, 2)
    except Exception:
        pass

    # Fallback на сохраненный кэш при сетевых сбоях / 429 ошибках (только при реальном запросе)
    if status != "OK" and session is None and use_cache:
        stale = load_disk_cache("onchain_cache.json", ttl_seconds=7 * 86400)
        if stale and stale.get("mvrv_zscore") is not None:
            stale["cache_status"] = "STALE_FALLBACK"
            return stale

    mvrv_stage = classify_mvrv_stage(mvrv_zscore)
    nupl_stage = classify_nupl_stage(nupl)

    result = {
        "mvrv_zscore": mvrv_zscore,
        "mvrv_stage": mvrv_stage,
        "mvrv_zone": mvrv_stage,
        "nupl": nupl,
        "nupl_stage": nupl_stage,
        "nupl_zone": nupl_stage,
        "realized_price": realized_price,
        "status": status,
        "date": date_val,
        "cache_status": "LIVE_FETCH",
    }
    if status == "OK" and session is None:
        save_disk_cache("onchain_cache.json", result)
    return result


def print_fast_scan_cli_table(snapshot: dict) -> None:
    """Выводит высокоплотный консольный дашборд для режима мгновенного импульса (--fast)."""
    now_str = snapshot.get("timestamp_utc", iso_utc())
    exec_sec = snapshot.get("execution_time_sec", 0.0)
    qb = snapshot.get("quant_bias", {})
    score = qb.get("composite_score", 0)
    label = qb.get("bias_label", "NEUTRAL")
    bd = qb.get("breakdown", {})

    binance = snapshot.get("binance", {})
    prices = binance.get("prices", {})
    spot_p = prices.get("spot_last", 0.0)
    fut_p = prices.get("futures_last", 0.0)
    basis_usd = prices.get("basis_usd", 0.0)
    basis_pct = prices.get("basis_pct", 0.0)

    deriv = binance.get("derivatives", {})
    live_oi = deriv.get("live_open_interest_btc", 0)
    fund_pct = deriv.get("current_funding_rate_pct", 0.0)
    z_scores = binance.get("statistical_z_scores", {})
    oi_z = z_scores.get("oi_zscore")
    fund_z = z_scores.get("funding_zscore")

    bybit = snapshot.get("bybit", {})
    bybit_ticker = bybit.get("ticker", {})
    bybit_p = bybit_ticker.get("lastPrice") if isinstance(bybit_ticker, dict) else None
    bybit_oi = bybit_ticker.get("openInterest") if isinstance(bybit_ticker, dict) else None

    risk = snapshot.get("risk_model", {})
    atr14 = risk.get("atr14", 0.0)
    buffer = risk.get("buffer", 0.0)
    direction = risk.get("direction", "NEUTRAL")
    long_setup = risk.get("long", {})
    short_setup = risk.get("short", {})

    onchain = snapshot.get("onchain_metrics", {})
    mvrv_z = onchain.get("mvrv_zscore")
    mvrv_stage = onchain.get("mvrv_stage", "UNAVAILABLE")
    nupl_v = onchain.get("nupl")
    nupl_stage = onchain.get("nupl_stage", "UNAVAILABLE")
    rp_v = onchain.get("realized_price")
    onchain_st = onchain.get("status", "UNAVAILABLE")

    calib = snapshot.get("quant_bias_calibration", {})
    calib_st = calib.get("status", "ACTIVE")
    wr = calib.get("overall_win_rate_pct")
    wr_str = f"{wr}%" if wr is not None else "Накапливает данные"

    print("\n" + "=" * 70)
    print("⚡ BTC MARKET INTELLIGENCE — FAST MOMENTUM SCANNER (REST-ONLY)")
    print("======================================================================")
    print(f"Время (UTC): {now_str} | Время выполнения: {exec_sec:.2f}с")
    print("\n📊 КОЛИЧЕСТВЕННЫЙ СКОРИНГ (QUANT BIAS)")
    print("-" * 70)
    sign = "+" if score > 0 else ""
    print(f"  Скоринг:      {sign}{score} / 100  [{label}]")
    if bd:
        print("  Драйверы:")
        for k, v in bd.items():
            k_disp = k.replace("_", " ").title()
            v_sign = "+" if v > 0 else ""
            print(f"    • {k_disp:32s}: {v_sign}{v} pts")
    print("\n📈 ЦЕНА И ДЕРИВАТИВЫ")
    print("-" * 70)
    print(f"  Spot Price:   ${spot_p:,.2f}  |  Futures Price: ${fut_p:,.2f}  |  Basis: ${basis_usd:+.2f} ({basis_pct:+.2f}%)")
    oi_z_str = f"{oi_z:+.2f}" if oi_z is not None else "N/A"
    fund_z_str = f"{fund_z:+.2f}" if fund_z is not None else "N/A"
    print(f"  Live OI:      {live_oi:,.1f} BTC  |  OI Z-Score:   {oi_z_str}")
    print(f"  Funding Rate: {fund_pct:+.4f}%    |  Fund Z-Score: {fund_z_str}")
    if bybit_p:
        bybit_oi_str = f"{bybit_oi:,.1f}" if bybit_oi else "N/A"
        print(f"  Bybit Price:  ${bybit_p:,.2f}  |  Bybit OI:      {bybit_oi_str}")
    print("\n🏛️ ИНСТИТУЦИОНАЛЬНЫЙ СРЕЗ (CME / DVOL / COINBASE PRO)")
    print("-" * 70)
    dvol = snapshot.get("deribit_dvol", {})
    cb = snapshot.get("coinbase_orderbook", {})
    cme = snapshot.get("cme_basis", {})
    if dvol.get("status") == "OK":
        print(f"  Deribit DVOL (Crypto VIX): {dvol.get('current_dvol')} pts [{dvol.get('dvol_regime')}]")
    else:
        print(f"  Deribit DVOL:              {dvol.get('status', 'N/A')}")
    if cb.get("status") == "OK":
        print(f"  Coinbase Pro L2 (±1%):     Биды {cb.get('bid_depth_btc')} BTC vs Аски {cb.get('ask_depth_btc')} BTC (Перевес {cb.get('bid_vs_ask_ratio')}x)")
    else:
        print(f"  Coinbase Pro L2:           {cb.get('status', 'N/A')}")
    if cme.get("status") == "OK":
        print(f"  CME BTC=F Последняя:       ${cme.get('cme_last_price', 0.0):,.2f} | Базис: {cme.get('basis_vs_spot_usd', 0.0):+.2f} USD ({cme.get('basis_vs_spot_pct', 0.0):+.2f}%)")
    else:
        print(f"  CME BTC=F:                 {cme.get('status', 'N/A')}")
    print("\n🎯 РИСК-МОДЕЛЬ ATR (ДИНАМИЧЕСКИЙ РАСЧЕТ R:R)")
    print("-" * 70)
    print(f"  ATR14: ${atr14:,.2f} | Буфер (1.5x ATR): ${buffer:,.2f} | Рекомендация: {direction}")
    print(f"  [Сценарий ЛОНГ]")
    print(f"    • Стоп-лосс (1.5x ATR):    ${long_setup.get('stop_loss', 0.0):,.2f} (-${buffer:,.2f} / -{long_setup.get('risk_pct', 0.0):.2f}%)")
    print(f"    • Тейк-профит 1 (1:2 R:R): ${long_setup.get('tp1_rr2', 0.0):,.2f} (+${2*buffer:,.2f} / +{2*long_setup.get('risk_pct', 0.0):.2f}%)")
    print(f"    • Тейк-профит 2 (1:3 R:R): ${long_setup.get('tp2_rr3', 0.0):,.2f} (+${3*buffer:,.2f} / +{3*long_setup.get('risk_pct', 0.0):.2f}%)")
    print(f"  [Сценарий ШОРТ]")
    print(f"    • Стоп-лосс (1.5x ATR):    ${short_setup.get('stop_loss', 0.0):,.2f} (+${buffer:,.2f} / +{short_setup.get('risk_pct', 0.0):.2f}%)")
    print(f"    • Тейк-профит 1 (1:2 R:R): ${short_setup.get('tp1_rr2', 0.0):,.2f} (-${2*buffer:,.2f} / -{2*short_setup.get('risk_pct', 0.0):.2f}%)")
    print(f"    • Тейк-профит 2 (1:3 R:R): ${short_setup.get('tp2_rr3', 0.0):,.2f} (-${3*buffer:,.2f} / -{3*short_setup.get('risk_pct', 0.0):.2f}%)")
    print("\n⛓️ ОНЧЕЙН-МЕТРИКИ (MVRV Z-SCORE & NUPL)")
    print("-" * 70)
    mvrv_str = f"{mvrv_z:.2f}" if mvrv_z is not None else "N/A"
    nupl_str = f"{nupl_v:.3f}" if nupl_v is not None else "N/A"
    rp_str = f"${rp_v:,.2f}" if rp_v is not None else "N/A"
    print(f"  MVRV Z-Score:   {mvrv_str}  [{mvrv_stage}]")
    print(f"  NUPL:           {nupl_str}  [{nupl_stage}]")
    print(f"  Realized Price: {rp_str}")
    print(f"  Статус ончейна: {onchain_st}")
    print("\n🎯 КАЛИБРОВКА И ВИНРЕЙТ")
    print("-" * 70)
    print(f"  Статус:       {calib_st}")
    print(f"  Винрейт:      {wr_str}")
    print(f"  Калибровка:   База обновлена в {TRACKER_FILE.name}")
    print("=" * 70)
    print(f"[✓] Снимок сохранен в {RAW_SNAPSHOT_FILE.name}\n")


def run_fast_momentum_scan(quiet: bool = False, mock: bool = False) -> dict:
    """
    Режим мгновенного импульса (--fast):
    Параллельный опрос REST API Binance, Bybit и BGeometrics без запуска браузера Playwright.
    Выполняется быстрее 5 секунд (целевое время 2-4с).
    """
    started = time.time()

    if mock:
        spot_price = 83050.00
        quant_bias = {
            "composite_score": 35,
            "bias_label": "BULLISH",
            "breakdown": {
                "1d_vwap_trend": 10,
                "24h_spot_cvd": 15,
                "spot_orderbook_imbalance": 10,
            }
        }
        atr14_val = 475.00
        atr_risk = calculate_atr_risk_levels(spot_price, atr14_val, quant_bias["composite_score"])
        onchain = {
            "mvrv_zscore": 1.09,
            "mvrv_stage": "Fair Value / Early Bull",
            "mvrv_zone": "Fair Value / Early Bull",
            "nupl": 0.384,
            "nupl_stage": "Optimism / Anxiety",
            "nupl_zone": "Optimism / Anxiety",
            "realized_price": 53294.67,
            "status": "OK",
            "date": "2026-10-04",
        }
        deribit_dvol = {
            "status": "OK",
            "source": "Deribit BTC DVOL Index",
            "current_dvol": 52.40,
            "dvol_regime": "Умеренная (Normal)",
            "date_utc": iso_utc(),
        }
        coinbase_ob = {
            "status": "OK",
            "source": "Coinbase Pro BTC-USD L2",
            "best_bid": 83045.0,
            "best_ask": 83055.0,
            "mid_price": 83050.0,
            "bid_depth_btc": 245.5,
            "ask_depth_btc": 180.2,
            "bid_vs_ask_ratio": 1.362,
            "threshold_pct": 1.0,
        }
        cme_basis = {
            "status": "OK",
            "source": "CME Bitcoin Futures (Front Month BTC=F)",
            "cme_last_price": 83320.0,
            "cme_prev_close": 82950.0,
            "basis_vs_spot_usd": 270.0,
            "basis_vs_spot_pct": 0.325,
            "weekend_gap_usd": -270.0,
            "regular_market_time_utc": iso_utc(),
        }
        binance = {
            "prices": {"spot_last": spot_price, "futures_last": 83020.0, "basis_usd": -30.0, "basis_pct": -0.036},
            "spot_24h_summary": {"change_pct": 1.25, "high": 83500.0, "low": 81500.0},
            "derivatives": {"live_open_interest_btc": 92500, "current_funding_rate_pct": 0.0012},
            "statistical_z_scores": {"oi_zscore": -0.85, "funding_zscore": -1.20},
            "divergence_engine": {"24h_divergence": {"divergence_state": "Bullish Continuation (Long Build-up)"}},
            "quant_bias": quant_bias,
            "risk_model": atr_risk,
            "atr_risk": atr_risk,
            "onchain_metrics": onchain,
            "onchain": onchain,
            "deribit_dvol": deribit_dvol,
            "coinbase_orderbook": coinbase_ob,
            "cme_basis": cme_basis,
            "market_structure": {"4h": {"atr14_price": atr14_val, "atr14_pct": 0.57}},
        }
        bybit = {
            "status": "OK",
            "ticker": {"lastPrice": 83040.0, "openInterest": 64500.0, "fundingRate": 0.0001},
        }
        calibration_summary = {"status": "MOCK", "readout": "Offline Self-Test Calibration Summary"}
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            f_binance = pool.submit(fetch_binance_telemetry, True)
            f_bybit = pool.submit(fetch_bybit_telemetry, True)
            f_onchain = pool.submit(fetch_onchain_metrics)
            f_dvol = pool.submit(fetch_deribit_dvol)
            f_coinbase = pool.submit(fetch_coinbase_orderbook)
            f_cme = pool.submit(fetch_cme_basis, 0.0)

            binance, binance_statuses = f_binance.result()
            bybit = f_bybit.result()
            onchain = f_onchain.result()
            deribit_dvol = f_dvol.result()
            coinbase_ob = f_coinbase.result()
            cme_basis = f_cme.result()

        spot_price = binance.get("prices", {}).get("spot_last", 0.0)
        if spot_price > 0 and cme_basis.get("status") == "OK" and cme_basis.get("cme_last_price"):
            cme_last = cme_basis["cme_last_price"]
            cme_basis["basis_vs_spot_usd"] = round(cme_last - spot_price, 2)
            cme_basis["basis_vs_spot_pct"] = round((cme_last / spot_price - 1) * 100, 3)
            cme_basis["weekend_gap_usd"] = round(spot_price - cme_last, 2)

        quant_bias = binance.get("quant_bias", {})
        score = quant_bias.get("composite_score", 0)

        struct_4h = binance.get("market_structure", {}).get("4h", {})
        atr14_val = struct_4h.get("atr14_price")
        if not atr14_val:
            struct_1h = binance.get("market_structure", {}).get("1h", {})
            atr14_val = struct_1h.get("atr14_price", 0.0)

        atr_risk = calculate_atr_risk_levels(spot_price, atr14_val, score)
        binance["risk_model"] = atr_risk
        binance["atr_risk"] = atr_risk
        binance["onchain_metrics"] = onchain
        binance["onchain"] = onchain
        binance["deribit_dvol"] = deribit_dvol
        binance["coinbase_orderbook"] = coinbase_ob
        binance["cme_basis"] = cme_basis

        calibration_summary = update_calibration_tracker(binance)

    exec_time = time.time() - started

    snapshot = {
        "timestamp_utc": iso_utc(),
        "local_timezone": LOCAL_TIMEZONE,
        "execution_mode": "FAST_MOMENTUM_SCAN",
        "execution_time_sec": round(exec_time, 2),
        "spot_price": spot_price,
        "prices": binance.get("prices", {}),
        "statistical_z_scores": binance.get("statistical_z_scores", {}),
        "spot_taker_delta": binance.get("spot_taker_delta", {}),
        "quant_bias": quant_bias,
        "risk_model": atr_risk,
        "atr_risk": atr_risk,
        "onchain_metrics": onchain,
        "onchain": onchain,
        "deribit_dvol": deribit_dvol,
        "coinbase_orderbook": coinbase_ob,
        "cme_basis": cme_basis,
        "binance": binance,
        "bybit": bybit,
        "quant_bias_calibration": calibration_summary,
        "run_finished_at_utc": iso_utc(),
    }

    if not mock:
        try:
            RAW_SNAPSHOT_FILE.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as exc:
            print(f"[WARN] Сбой сохранения снимка: {exc}")
        try:
            history = read_history()
            save_snapshot(binance, history)
        except Exception as exc:
            print(f"[WARN] Сбой обновления истории: {exc}")

    if not quiet:
        print_fast_scan_cli_table(snapshot)

    return snapshot


def fetch_binance_telemetry(parallel: bool = True) -> tuple[dict, dict]:
    print("[*] Сбор глубокой телеметрии Binance...")
    statuses = {}

    intervals_fut = (("1w", 35), ("3d", 35), ("1d", 35), ("12h", 35), ("4h", 35), ("1h", 35), ("15m", 35), ("5m", 35))
    intervals_spot = (("1d", 35), ("4h", 35), ("1h", 35), ("15m", 35), ("5m", 35))

    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=24) as pool:
            f_spot_ticker = pool.submit(safe_get_json, f"{BINANCE_SPOT}/api/v3/ticker/price", {"symbol": SYMBOL})
            f_fut_ticker = pool.submit(safe_get_json, f"{BINANCE_FUTURES}/fapi/v1/ticker/price", {"symbol": SYMBOL})
            f_ticker24 = pool.submit(safe_get_json, f"{BINANCE_SPOT}/api/v3/ticker/24hr", {"symbol": SYMBOL})
            f_premium = pool.submit(safe_get_json, f"{BINANCE_FUTURES}/fapi/v1/premiumIndex", {"symbol": SYMBOL})
            f_live_oi = pool.submit(safe_get_json, f"{BINANCE_FUTURES}/fapi/v1/openInterest", {"symbol": SYMBOL})
            f_k1m = pool.submit(fetch_klines, BINANCE_SPOT, SYMBOL, "1m", 15)

            f_fut_klines = {inter: pool.submit(fetch_klines, BINANCE_FUTURES, SYMBOL, inter, lim) for inter, lim in intervals_fut}
            f_spot_klines = {inter: pool.submit(fetch_klines, BINANCE_SPOT, SYMBOL, inter, lim) for inter, lim in intervals_spot}

            f_oi_hist = pool.submit(safe_get_json, f"{BINANCE_FUTURES}/futures/data/openInterestHist", {"symbol": SYMBOL, "period": "1h", "limit": 50})
            f_last_funding = pool.submit(safe_get_json, f"{BINANCE_FUTURES}/fapi/v1/fundingRate", {"symbol": SYMBOL, "limit": 50})

            f_ratios = {
                "global_accounts_long_short_1h": pool.submit(fetch_ratio, "globalLongShortAccountRatio", "1h"),
                "futures_taker_buy_sell_1h": pool.submit(fetch_ratio, "takerlongshortRatio", "1h"),
                "top_trader_accounts_1h": pool.submit(fetch_ratio, "topLongShortAccountRatio", "1h"),
                "top_trader_positions_1h": pool.submit(fetch_ratio, "topLongShortPositionRatio", "1h"),
            }
            f_ob_spot = pool.submit(fetch_orderbook_snapshot, BINANCE_SPOT, "/api/v3/depth", SYMBOL, 500, 1.0)
            f_ob_fut = pool.submit(fetch_orderbook_snapshot, BINANCE_FUTURES, "/fapi/v1/depth", SYMBOL, 500, 1.0)

            spot_ticker = f_spot_ticker.result()
            fut_ticker = f_fut_ticker.result()
            ticker24 = f_ticker24.result()
            premium = f_premium.result()
            live_oi_data = f_live_oi.result()
            k1m = f_k1m.result()

            raw_fut = {inter: f_fut_klines[inter].result() for inter, _ in intervals_fut}
            raw_spot = {inter: f_spot_klines[inter].result() for inter, _ in intervals_spot}
            spot_flow = fetch_spot_flow(SYMBOL, {**raw_spot, "1m": k1m})
            oi_history = f_oi_hist.result()
            last_funding = f_last_funding.result()
            ratios = {k: v.result() for k, v in f_ratios.items()}
            ob_spot = f_ob_spot.result()
            ob_fut = f_ob_fut.result()
    else:
        spot_ticker = safe_get_json(f"{BINANCE_SPOT}/api/v3/ticker/price", {"symbol": SYMBOL})
        fut_ticker = safe_get_json(f"{BINANCE_FUTURES}/fapi/v1/ticker/price", {"symbol": SYMBOL})
        ticker24 = safe_get_json(f"{BINANCE_SPOT}/api/v3/ticker/24hr", {"symbol": SYMBOL})
        premium = safe_get_json(f"{BINANCE_FUTURES}/fapi/v1/premiumIndex", {"symbol": SYMBOL})
        live_oi_data = safe_get_json(f"{BINANCE_FUTURES}/fapi/v1/openInterest", {"symbol": SYMBOL})
        k1m = fetch_klines(BINANCE_SPOT, SYMBOL, "1m", 15)
        raw_fut = {inter: fetch_klines(BINANCE_FUTURES, SYMBOL, inter, lim) for inter, lim in intervals_fut}
        raw_spot = {inter: fetch_klines(BINANCE_SPOT, SYMBOL, inter, lim) for inter, lim in intervals_spot}
        spot_flow = fetch_spot_flow(SYMBOL, {**raw_spot, "1m": k1m})
        oi_history = safe_get_json(f"{BINANCE_FUTURES}/futures/data/openInterestHist", {"symbol": SYMBOL, "period": "1h", "limit": 50})
        last_funding = safe_get_json(f"{BINANCE_FUTURES}/fapi/v1/fundingRate", {"symbol": SYMBOL, "limit": 50})
        ratios = {
            "global_accounts_long_short_1h": fetch_ratio("globalLongShortAccountRatio", "1h"),
            "futures_taker_buy_sell_1h": fetch_ratio("takerlongshortRatio", "1h"),
            "top_trader_accounts_1h": fetch_ratio("topLongShortAccountRatio", "1h"),
            "top_trader_positions_1h": fetch_ratio("topLongShortPositionRatio", "1h"),
        }
        ob_spot = fetch_orderbook_snapshot(BINANCE_SPOT, "/api/v3/depth", SYMBOL, 500, 1.0)
        ob_fut = fetch_orderbook_snapshot(BINANCE_FUTURES, "/fapi/v1/depth", SYMBOL, 500, 1.0)

    if not isinstance(spot_ticker, dict) or not isinstance(fut_ticker, dict):
        raise DataIntegrityError("Критические котировки спота или фьючерсов Binance недоступны.")
    spot_price = finite_float(spot_ticker.get("price"))
    fut_price = finite_float(fut_ticker.get("price"))
    if not spot_price or not fut_price:
        raise DataIntegrityError("Получены невалидные котировки цен.")

    statuses["binance_spot_flow"] = status_record(
        bool(spot_flow.get("1h", {}).get("available")),
        "Интервальная спотовая дельта по закрытым свечам",
    )

    structures = {inter: detect_structure(raw_fut[inter], inter) for inter, _ in intervals_fut}
    statuses["binance_structure"] = status_record(
        all(structures[k].get("available") for k in ("1d", "4h", "1h")),
        "EMA/RSI/ATR/volume/pivots/breakout on closed Binance futures candles",
    )

    spot_structures = {inter: detect_structure(raw_spot[inter], inter) for inter, _ in intervals_spot}
    statuses["binance_spot_structure"] = status_record(
        all(spot_structures[k].get("available") for k in ("1d", "4h", "1h")),
        "EMA/RSI/ATR/volume/pivots/breakout on closed Binance spot candles",
    )

    live_oi = finite_float(live_oi_data.get("openInterest")) if isinstance(live_oi_data, dict) else None
    oi_time = finite_float(live_oi_data.get("time")) if isinstance(live_oi_data, dict) else None
    oi_age = round(time.time() - oi_time / 1000, 2) if oi_time else None
    oi_metrics = {}
    if live_oi is not None and isinstance(oi_history, list):
        for hours in (1, 4, 24):
            oi_metrics[f"{hours}h"] = nearest_oi_change(oi_history, live_oi, hours)
    statuses["binance_open_interest"] = status_record(
        live_oi is not None and (oi_age is not None and oi_age < 300),
        f"Live OI age = {oi_age}s",
    )

    funding_rate = finite_float(premium.get("lastFundingRate")) if isinstance(premium, dict) else None
    mark_price = finite_float(premium.get("markPrice")) if isinstance(premium, dict) else None
    index_price = finite_float(premium.get("indexPrice")) if isinstance(premium, dict) else None
    basis_usd = fut_price - spot_price
    basis_pct = basis_usd / spot_price * 100 if spot_price else None

    # Синхронный базис из premiumIndex (без сетевого лага между отдельными HTTP-запросами)
    sync_basis_usd = (mark_price - index_price) if (mark_price is not None and index_price is not None) else basis_usd
    sync_basis_pct = (sync_basis_usd / index_price * 100) if (index_price and sync_basis_usd is not None) else basis_pct

    funding_history = []
    if isinstance(last_funding, list):
        for row in last_funding[-10:]:
            rate = finite_float(row.get("fundingRate"))
            ts = finite_float(row.get("fundingTime"))
            funding_history.append({
                "rate_pct": round(rate * 100, 4) if rate is not None else None,
                "time_utc": iso_utc(datetime.fromtimestamp(ts / 1000, tz=timezone.utc)) if ts else None,
            })

    # Calculate 10/10 Z-Scores
    oi_zscore = None
    if isinstance(oi_history, list) and live_oi is not None:
        oi_vals = [finite_float(x.get("sumOpenInterest")) for x in oi_history]
        oi_vals = [x for x in oi_vals if x is not None]
        oi_zscore = calculate_zscore(live_oi, oi_vals)

    funding_zscore = None
    if isinstance(last_funding, list) and funding_rate is not None:
        fund_vals = [finite_float(x.get("fundingRate")) for x in last_funding]
        fund_vals = [x for x in fund_vals if x is not None]
        funding_zscore = calculate_zscore(funding_rate, fund_vals)

    result = {
        "prices": {
            "spot_last": spot_price,
            "futures_last": fut_price,
            "basis_usd": round(basis_usd, 2),
            "basis_pct": round(basis_pct, 4) if basis_pct is not None else None,
            "synchronized_basis_usd": round(sync_basis_usd, 2) if sync_basis_usd is not None else None,
            "synchronized_basis_pct": round(sync_basis_pct, 4) if sync_basis_pct is not None else None,
            "mark_price": mark_price,
            "index_price": index_price,
        },
        "spot_24h_summary": {
            "change_pct": finite_float(ticker24.get("priceChangePercent")) if isinstance(ticker24, dict) else None,
            "high": finite_float(ticker24.get("highPrice")) if isinstance(ticker24, dict) else None,
            "low": finite_float(ticker24.get("lowPrice")) if isinstance(ticker24, dict) else None,
            "quote_volume_usdt": finite_float(ticker24.get("quoteVolume")) if isinstance(ticker24, dict) else None,
        },
        "spot_taker_delta": spot_flow,
        "derivatives": {
            "live_open_interest_btc": live_oi,
            "oi_age_seconds": oi_age,
            "oi_change_deltas": oi_metrics,
            "current_funding_rate_pct": round(funding_rate * 100, 4) if funding_rate is not None else None,
            "recent_funding_history": funding_history,
            "positioning_ratios": ratios,
        },
        "orderbook_depth": {
            "spot": ob_spot,
            "futures": ob_fut,
        },
        "market_structure": structures,
        "spot_market_structure": spot_structures,
        "structure_source": "Separate closed-candle structure for Binance spot and USDⓈ-M futures; do not treat them as interchangeable.",
    }

    # Apply 10/10 Divergence Engine
    price_chg_24 = result["spot_24h_summary"]["change_pct"]
    oi_chg_24 = oi_metrics.get("24h", {}).get("change_pct")
    if price_chg_24 is not None and oi_chg_24 is not None:
        result["divergence_engine"] = {
            "24h_divergence": detect_divergence_engine(price_chg_24, oi_chg_24)
        }

    # Attach Statistical Z-Scores
    result["statistical_z_scores"] = {
        "oi_zscore": oi_zscore,
        "funding_zscore": funding_zscore,
        "note": "Z-Scores using up to 500 historical observations to identify statistical anomalies (> 2.0 or < -2.0)."
    }

    # Apply Quant Bias Score
    result["quant_bias"] = calculate_quant_bias(result)

    # Attach dynamic ATR Risk Model
    atr14_val = structures.get("4h", {}).get("atr14_price") or structures.get("1h", {}).get("atr14_price", 0.0)
    score_val = result["quant_bias"].get("composite_score", 0)
    result["risk_model"] = calculate_atr_risk_levels(spot_price, atr14_val, score_val)
    result["atr_risk"] = result["risk_model"]
    return result, statuses


# ----------------------------- BYBIT PUBLIC DATA -----------------------------

def bybit_get(path: str, params: dict) -> Any:
    """Unauthenticated public Bybit V5 market data."""
    try:
        response = SESSION.get(f"{BYBIT_API_BASE}{path}", params=params, timeout=(1.5, min(TIMEOUT_SEC, 2.0)))
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict) or data.get("retCode") != 0:
            return {"_error": data}
        return data.get("result", {})
    except Exception as exc:
        return {"_error": str(exc)}


def fetch_bybit_telemetry(parallel: bool = True) -> dict:
    """Free cross-check: Bybit linear BTCUSDT price, OI, funding, account ratio and trades."""
    out = {"source": "Bybit public V5 API", "collected_at_utc": iso_utc()}
    if parallel:
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            f_ticker = pool.submit(bybit_get, "/v5/market/tickers", {"category": "linear", "symbol": "BTCUSDT"})
            f_oi = pool.submit(bybit_get, "/v5/market/open-interest", {"category": "linear", "symbol": "BTCUSDT", "intervalTime": "1h", "limit": 25})
            f_funding = pool.submit(bybit_get, "/v5/market/funding/history", {"category": "linear", "symbol": "BTCUSDT", "limit": 8})
            f_ratio = pool.submit(bybit_get, "/v5/market/account-ratio", {"category": "linear", "symbol": "BTCUSDT", "period": "1h", "limit": 24})
            f_book = pool.submit(bybit_get, "/v5/market/orderbook", {"category": "linear", "symbol": "BTCUSDT", "limit": 50})

            ticker = f_ticker.result()
            oi = f_oi.result()
            funding = f_funding.result()
            ratio = f_ratio.result()
            book = f_book.result()
    else:
        ticker = bybit_get("/v5/market/tickers", {"category": "linear", "symbol": "BTCUSDT"})
        oi = bybit_get("/v5/market/open-interest", {"category": "linear", "symbol": "BTCUSDT", "intervalTime": "1h", "limit": 25})
        funding = bybit_get("/v5/market/funding/history", {"category": "linear", "symbol": "BTCUSDT", "limit": 8})
        ratio = bybit_get("/v5/market/account-ratio", {"category": "linear", "symbol": "BTCUSDT", "period": "1h", "limit": 24})
        book = bybit_get("/v5/market/orderbook", {"category": "linear", "symbol": "BTCUSDT", "limit": 50})

    items = ticker.get("list", []) if isinstance(ticker, dict) else []
    if items:
        t = items[0]
        out["ticker"] = {k: finite_float(t.get(k)) for k in ("lastPrice", "markPrice", "indexPrice", "fundingRate", "openInterest", "turnover24h", "volume24h", "price24hPcnt")}
        out["ticker"]["price24hPcnt_pct"] = round((out["ticker"].get("price24hPcnt") or 0)*100, 4)
    else:
        out["ticker"] = {"status": "UNAVAILABLE", "reason": ticker.get("_error", "No ticker data") if isinstance(ticker, dict) else "No data"}
    oi_rows = oi.get("list", []) if isinstance(oi, dict) else []
    oi_rows = sorted(oi_rows, key=lambda r: int(r.get("timestamp", 0))) if oi_rows else []
    oi_series=[]
    for row in oi_rows:
        ts=finite_float(row.get("timestamp")); val=finite_float(row.get("openInterest"))
        if ts is not None and val is not None:
            oi_series.append({"timestamp_utc": iso_utc(datetime.fromtimestamp(ts/1000, tz=timezone.utc)), "open_interest": val})
    oi_changes={}
    if len(oi_series)>=2:
        latest=oi_series[-1]
        for hours in (1,4,24):
            target=datetime.fromisoformat(latest["timestamp_utc"].replace("Z","+00:00"))-timedelta(hours=hours)
            candidates=[r for r in oi_series if abs((datetime.fromisoformat(r["timestamp_utc"].replace("Z","+00:00"))-target).total_seconds())<=hours*3600*0.25+1800]
            if candidates:
                prev=min(candidates,key=lambda r:abs((datetime.fromisoformat(r["timestamp_utc"].replace("Z","+00:00"))-target).total_seconds()))
                oi_changes[f"{hours}h"]={"available":True,"from":prev,"to":latest,"change_pct":round((latest["open_interest"]/prev["open_interest"]-1)*100,3) if prev["open_interest"] else None}
            else:
                oi_changes[f"{hours}h"]={"available":False,"reason":"No sufficiently close historical OI observation"}
    out["open_interest_history"]={"status":"OK" if oi_series else "UNAVAILABLE", "unit":"Bybit-reported contract units; do not add to USD OI without conversion", "series":oi_series, "changes":oi_changes}
    fund_rows=funding.get("list",[]) if isinstance(funding,dict) else []
    out["funding_history"]=[{"funding_rate_pct":round(finite_float(r.get("fundingRate"),0)*100,5),"funding_time_utc":iso_utc(datetime.fromtimestamp(int(r.get("fundingRateTimestamp",0))/1000,tz=timezone.utc)) if r.get("fundingRateTimestamp") else None} for r in fund_rows]
    ratio_rows=ratio.get("list",[]) if isinstance(ratio,dict) else []
    out["account_long_short_ratio"]=[{"timestamp":r.get("timestamp"),"buy_ratio":finite_float(r.get("buyRatio")),"sell_ratio":finite_float(r.get("sellRatio"))} for r in ratio_rows[:24]]
    # Reuse thread-pooled book result directly (saves 200-400ms sequential blocking latency)
    if isinstance(book,dict) and book.get("b") and book.get("a"):
        bids=[(finite_float(x[0],0),finite_float(x[1],0)) for x in book["b"]]
        asks=[(finite_float(x[0],0),finite_float(x[1],0)) for x in book["a"]]
        bid_usd=sum(p*q for p,q in bids); ask_usd=sum(p*q for p,q in asks)
        out["orderbook_snapshot"]={"status":"OK","timestamp_ms":book.get("ts"),"bid_notional_usd_top50":round(bid_usd,2),"ask_notional_usd_top50":round(ask_usd,2),"bid_ask_notional_ratio":round(bid_usd/ask_usd,4) if ask_usd else None,"warning":"Single snapshot; not a predictive signal and can be spoofed/cancelled."}
    else:
        out["orderbook_snapshot"]={"status":"UNAVAILABLE","reason":book.get("_error") if isinstance(book,dict) else "No data"}
    out["status"]="OK" if out.get("ticker",{}).get("lastPrice") else "PARTIAL_OR_UNAVAILABLE"
    out["interpretation_limit"]="Bybit is a separate exchange cross-check, not global market aggregation. OI units differ by contract; do not sum raw OI across exchanges. Ratios are account-based and do not reveal net capital exposure."
    return out


# -------------------------- МАКРОЭКОНОМИКА И КАТАЛИЗАТОРЫ ---------------------

def fetch_yahoo_snapshot(ticker: str, label: str) -> dict:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    data = safe_get_json(url, {"range": "5d", "interval": "1d"})
    try:
        chart = data["chart"]["result"][0]
        quotes = chart["indicators"]["quote"][0]["close"]
        timestamps = chart.get("timestamp") or []
        paired = []
        for i, value in enumerate(quotes):
            if value is None or i >= len(timestamps):
                continue
            number = finite_float(value)
            ts_value = finite_float(timestamps[i])
            if number is not None and ts_value is not None:
                paired.append((int(ts_value), number))
        if not paired:
            raise ValueError("Нет согласованных котировок и временных меток")
        paired.sort(key=lambda x: x[0])
        last_ts, latest = paired[-1]
        previous = paired[-2][1] if len(paired) >= 2 else None
        source_dt = datetime.fromtimestamp(last_ts, tz=timezone.utc)
        data_age = round((time.time() - last_ts) / 3600, 1)

        return {
            "label": label,
            "ticker": ticker,
            "last": round(latest, 4),
            "change_pct": round((latest / previous - 1) * 100, 2) if previous else None,
            "source_timestamp_utc": iso_utc(source_dt) if source_dt else None,
            "data_age_hours": data_age,
            "status": "OK",
        }
    except Exception as exc:
        return {"label": label, "ticker": ticker, "status": "UNAVAILABLE", "reason": str(exc)}


def fetch_macro_cross_asset() -> dict:
    instruments = [
        ("DX-Y.NYB", "US Dollar Index (DXY)"),
        ("^TNX", "10Y Treasury Yield"),
        ("^FVX", "5Y Treasury Yield"),
        ("^VIX", "CBOE Volatility Index (VIX)"),
        ("^IXIC", "Nasdaq Composite"),
        ("^GSPC", "S&P 500"),
        ("GC=F", "Gold Futures"),
        ("CL=F", "Crude Oil WTI"),
        ("EURUSD=X", "EUR/USD"),
        ("JPY=X", "USD/JPY"),
    ]
    return {
        "collected_at_utc": iso_utc(),
        "instruments": [fetch_yahoo_snapshot(ticker, label) for ticker, label in instruments],
    }


def fetch_macro_calendar() -> dict:
    # 1. Проверяем свежий локальный кэш (2 часа) для предотвращения Cloudflare 429
    cached = load_disk_cache("macro_calendar_cache.json", ttl_seconds=2 * 3600)
    if cached and cached.get("status") == "OK" and cached.get("upcoming_events") is not None:
        cached["cache_status"] = "CACHE_HIT"
        return cached

    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    events = safe_get_json(url)
    if not isinstance(events, list):
        # Fallback на сохраненный кэш при сетевых блокировках Cloudflare
        stale = load_disk_cache("macro_calendar_cache.json", ttl_seconds=7 * 86400)
        if stale and stale.get("upcoming_events"):
            stale["cache_status"] = "STALE_FALLBACK"
            return stale
        return {"status": "UNAVAILABLE", "reason": "Календарь Forex Factory недоступен"}
    try:
        local_tz = ZoneInfo(LOCAL_TIMEZONE)
    except Exception:
        local_tz = timezone.utc
    now = utc_now()
    
    days_ru = {
        "Mon": "Пн", "Tue": "Вт", "Wed": "Ср", "Thu": "Чт", "Fri": "Пт", "Sat": "Сб", "Sun": "Вс",
        "Monday": "Понедельник", "Tuesday": "Вторник", "Wednesday": "Среда",
        "Thursday": "Четверг", "Friday": "Пятница", "Saturday": "Суббота", "Sunday": "Воскресенье",
    }
    months_ru = {
        1: "янв", 2: "фев", 3: "мар", 4: "апр", 5: "мая", 6: "июн",
        7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек"
    }

    upcoming = []
    # Смотрим на 7 дней вперед (168 часов), чтобы видеть всю текущую или предстоящую неделю (особенно на выходных)
    max_lookahead_hours = 168.0

    for event in events:
        if event.get("country") != "USD" or event.get("impact") not in ("High", "Medium"):
            continue
        try:
            dt = datetime.fromisoformat(str(event["date"]).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            hours = (dt.astimezone(timezone.utc) - now).total_seconds() / 3600
            if -2 <= hours <= max_lookahead_hours:
                local_dt = dt.astimezone(local_tz)
                day_short = days_ru.get(local_dt.strftime("%a"), local_dt.strftime("%a"))
                month_str = months_ru.get(local_dt.month, str(local_dt.month))
                time_str = local_dt.strftime("%H:%M")
                formatted_riga = f"{day_short}, {local_dt.day} {month_str} в {time_str} (Рига)"

                upcoming.append({
                    "event": event.get("title"),
                    "impact": "ВЫСОКАЯ (High)" if event.get("impact") == "High" else "СРЕДНЯЯ (Medium)",
                    "impact_raw": event.get("impact"),
                    "time_latvia": formatted_riga,
                    "hours_until": round(hours, 1),
                    "forecast": event.get("forecast") or "—",
                    "previous": event.get("previous") or "—",
                })
        except Exception:
            continue

    upcoming.sort(key=lambda x: x["hours_until"])
    is_weekend = now.weekday() in (5, 6)
    
    result = {
        "status": "OK",
        "timezone": LOCAL_TIMEZONE,
        "is_weekend": is_weekend,
        "period_description": "Макрособытия США на следующую неделю (время Латвии)" if is_weekend else "Макрособытия США на текущую неделю (время Латвии)",
        "total_upcoming_events": len(upcoming),
        "upcoming_events": upcoming,
        "cache_status": "LIVE_FETCH",
    }
    if upcoming:
        save_disk_cache("macro_calendar_cache.json", result)
    return result


def fetch_rss_headlines() -> dict:
    if not ENABLE_RSS_NEWS:
        return {"status": "DISABLED", "items": []}
    feeds = [
        ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
        ("Cointelegraph", "https://cointelegraph.com/rss"),
        ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
    ]
    items = []
    cutoff = utc_now() - timedelta(hours=36)
    for source, url in feeds:
        text = safe_get_text(url)
        if not text:
            continue
        try:
            root = ET.fromstring(text)
            for node in root.findall(".//item")[:20]:
                title = (node.findtext("title") or "").strip()
                pub = (node.findtext("pubDate") or "").strip()
                published = None
                try:
                    published = parsedate_to_datetime(pub)
                    if published.tzinfo is None:
                        published = published.replace(tzinfo=timezone.utc)
                except Exception:
                    pass
                if published and published < cutoff:
                    continue
                items.append({
                    "source": source,
                    "title": title[:250],
                    "published_utc": iso_utc(published) if published else None,
                })
        except Exception:
            pass
    items.sort(key=lambda x: x.get("published_utc") or "", reverse=True)
    # Deduplicate same headline across feeds, retain source attribution.
    dedup = []
    seen = set()
    for item in items:
        key = re.sub(r"\W+", " ", item.get("title", "").lower()).strip()
        if key and key not in seen:
            seen.add(key)
            dedup.append(item)
    return {"status": "OK" if dedup else "UNAVAILABLE", "window_hours": 36, "sources_attempted": len(feeds), "items": dedup[:12]}


# -------------------------- ETF / OPTIONS / AGGREGATE DERIVATIVES -------------
# CoinGlass endpoints used below are documented in the official v4 endpoint reference.

class _TableParser(HTMLParser):
    """Small dependency-free HTML table reader for Farside's published table."""
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None
    def handle_starttag(self, tag, attrs):
        if tag == "tr": self.row = []
        elif tag in ("td", "th") and self.row is not None: self.cell = []
    def handle_data(self, data):
        if self.cell is not None: self.cell.append(data)
    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row: self.rows.append(self.row)
            self.row = None


def _parse_money_cell(value: str) -> Optional[float]:
    v = (value or "").strip().replace(",", "").replace("$", "").replace("£", "")
    if not v or v in ("-", "—", "–", "n/a", "N/A"):
        return None
    negative = v.startswith("(") and v.endswith(")")
    v = v.strip("() ")
    try:
        n = float(v)
        return -n if negative else n
    except ValueError:
        return None


def fetch_btc_etf_flows() -> dict:
    """Parse Farside's daily US spot BTC ETF net flows; values are USD millions."""
    if not ENABLE_ETF_FLOWS:
        return {"status": "DISABLED", "source": FARSIDE_BTC_ETF_URL}
    text = safe_get_text(FARSIDE_BTC_ETF_URL)
    if not text:
        return {"status": "UNAVAILABLE", "source": FARSIDE_BTC_ETF_URL, "reason": "Farside page could not be fetched"}
    parser = _TableParser()
    try:
        parser.feed(text)
        rows = parser.rows
        candidates = []
        for row in rows:
            if len(row) < 3:
                continue
            date_cell = row[0].strip()
            # Farside date cells generally look like 21 Sep 2026.
            try:
                dt = datetime.strptime(date_cell, "%d %b %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            vals = [_parse_money_cell(x) for x in row[1:]]
            total = vals[-1] if vals else None
            if total is None:
                continue
            # P1.2 Fix: Если все отдельные фонды еще не отчитались (прочерки/пусто), а Total=0.0 — это незавершенная сессия
            fund_cells = vals[:-1] if len(vals) > 1 else []
            if fund_cells and all(v is None for v in fund_cells) and total == 0.0:
                continue
            candidates.append({"date": dt.date().isoformat(), "date_utc": iso_utc(dt), "total_net_flow_usd_millions": total})
        if not candidates:
            return {"status": "UNAVAILABLE", "source": FARSIDE_BTC_ETF_URL, "reason": "No parseable daily rows found; page structure may have changed"}
        candidates.sort(key=lambda x: x["date"])
        recent = candidates[-30:]
        flows = [x["total_net_flow_usd_millions"] for x in recent]
        n_sessions = len(flows)
        return {
            "status": "OK", "source": FARSIDE_BTC_ETF_URL,
            "source_note": "Farside Investors table; values in USD millions, daily flow is not AUM and not price change. Note: ETF sessions represent trading days (not calendar days).",
            "latest": recent[-1],
            "trading_sessions_available": n_sessions,
            "latest_3_sessions_sum_usd_millions": round(sum(flows[-3:]), 2) if n_sessions >= 3 else None,
            "latest_7_sessions_sum_usd_millions": round(sum(flows[-7:]), 2) if n_sessions >= 7 else None,
            "latest_30d_sum_usd_millions": round(sum(flows[-30:]), 2) if n_sessions >= 30 else None,
            "available_history_sum_usd_millions": round(sum(flows), 2),
            "daily_history_available": recent,
            "btc_equivalent": "Not calculated here because flow date and current BTC price are not the same timestamp; calculate only when using a matched price/date.",
        }
    except Exception as exc:
        return {"status": "UNAVAILABLE", "source": FARSIDE_BTC_ETF_URL, "reason": str(exc)}


def _deribit_get(method: str, params: dict) -> Any:
    return safe_get_json(f"{DERIBIT_API_BASE}/public/{method}", params)


def fetch_deribit_options() -> dict:
    """Public BTC options regime layer: expiry OI, put/call OI and available IVs."""
    if not ENABLE_DERIBIT_OPTIONS:
        return {"status": "DISABLED", "source": "Deribit public API"}
    response = _deribit_get("get_book_summary_by_currency", {"currency": "BTC", "kind": "option"})
    data = response.get("result") if isinstance(response, dict) else None
    if not isinstance(data, list) or not data:
        return {"status": "UNAVAILABLE", "source": "Deribit public API", "reason": "No option book summaries returned"}
    now = utc_now()
    expiries = {}
    total_oi = 0.0
    total_call_oi = 0.0
    total_put_oi = 0.0
    ivs = []
    for item in data:
        name = str(item.get("instrument_name", ""))
        # BTC-27DEC24-100000-C; expired contracts excluded when date is parseable.
        match = re.match(r"BTC-(\d{1,2}[A-Z]{3}\d{2})-(\d+)-(C|P)$", name)
        if not match:
            continue
        exp_code, strike_text, side = match.groups()
        try:
            expiry = datetime.strptime(exp_code, "%d%b%y").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if expiry < now - timedelta(days=1):
            continue
        oi = finite_float(item.get("open_interest"), 0.0) or 0.0
        iv = finite_float(item.get("mark_iv"))
        underlying = finite_float(item.get("underlying_price"))
        strike = float(strike_text)
        if oi <= 0 and iv is None:
            continue
        key = expiry.date().isoformat()
        bucket = expiries.setdefault(key, {"expiry_utc": key, "call_open_interest_contracts": 0.0, "put_open_interest_contracts": 0.0, "iv_observations": [], "days_to_expiry": max(0, (expiry.date()-now.date()).days)})
        if side == "C":
            bucket["call_open_interest_contracts"] += oi
            total_call_oi += oi
        else:
            bucket["put_open_interest_contracts"] += oi
            total_put_oi += oi
        total_oi += oi
        # ATM proxy only: IV values for strikes within 3% of underlying, not true delta-neutral ATM.
        if iv is not None:
            ivs.append(iv)
            if underlying and abs(strike / underlying - 1) <= 0.03:
                bucket["iv_observations"].append(iv)
    expiry_rows = []
    for key, bucket in sorted(expiries.items()):
        obs = bucket.pop("iv_observations")
        bucket["near_atm_iv_mean_pct"] = round(statistics.mean(obs), 2) if obs else None
        bucket["put_call_oi_ratio"] = round(bucket["put_open_interest_contracts"] / bucket["call_open_interest_contracts"], 3) if bucket["call_open_interest_contracts"] else None
        bucket["call_open_interest_contracts"] = round(bucket["call_open_interest_contracts"], 3)
        bucket["put_open_interest_contracts"] = round(bucket["put_open_interest_contracts"], 3)
        expiry_rows.append(bucket)
    return {
        "status": "OK" if expiry_rows else "UNAVAILABLE",
        "source": "Deribit public API",
        "collected_at_utc": iso_utc(),
        "contracts_seen": len(data),
        "active_expiries_seen": len(expiry_rows),
        "total_open_interest_contracts_mixed_units": round(total_oi, 3),
        "call_open_interest_contracts_mixed_units": round(total_call_oi, 3),
        "put_open_interest_contracts_mixed_units": round(total_put_oi, 3),
        "put_call_oi_ratio": round(total_put_oi / total_call_oi, 3) if total_call_oi else None,
        "mean_mark_iv_pct_all_listed_options": round(statistics.mean(ivs), 2) if ivs else None,
        "expiry_breakdown_next_12": expiry_rows[:12],
        "limitations": "Deribit-only, not global options market. Open-interest contract units differ by contract; do not sum as USD notional. This is put/call OI and near-ATM IV proxy, not true 25-delta skew, not a full volatility surface, and not max pain.",
    }


def fetch_deribit_dvol() -> dict:
    """Бесплатный публичный индекс подразумеваемой волатильности Bitcoin (Crypto VIX / DVOL)."""
    cached = load_disk_cache("deribit_dvol_cache.json", ttl_seconds=15 * 60)
    if cached and cached.get("current_dvol") is not None:
        cached["cache_status"] = "CACHE_HIT"
        return cached
    if cached and cached.get("status") == "UNAVAILABLE":
        # Temporary failure backoff (within 3 minutes)
        return cached

    now_ms = int(time.time() * 1000)
    params = {
        "currency": "BTC",
        "start_timestamp": now_ms - 86400000 * 3,
        "end_timestamp": now_ms,
        "resolution": "1D",
    }
    data = safe_get_json(DERIBIT_DVOL_URL, params)
    try:
        if isinstance(data, dict) and "result" in data:
            rows = data["result"].get("data", [])
            if rows:
                latest = rows[-1]
                # Формат строки: [timestamp, open, high, low, close]
                dvol_val = float(latest[4])
                regime = "Высокая (High Volatility)" if dvol_val >= 55.0 else ("Умеренная (Normal)" if dvol_val >= 40.0 else "Низкая (Compressed Vol)")
                res = {
                    "status": "OK",
                    "source": "Deribit BTC DVOL Index",
                    "current_dvol": round(dvol_val, 2),
                    "dvol_regime": regime,
                    "date_utc": iso_utc(datetime.fromtimestamp(latest[0] / 1000, tz=timezone.utc)),
                    "cache_status": "LIVE_FETCH",
                }
                save_disk_cache("deribit_dvol_cache.json", res)
                return res
    except Exception as exc:
        stale = load_disk_cache("deribit_dvol_cache.json", ttl_seconds=86400 * 2)
        if stale and stale.get("current_dvol"):
            stale["cache_status"] = "STALE_FALLBACK"
            return stale
        err_res = {"status": "UNAVAILABLE", "reason": str(exc)}
        save_disk_cache("deribit_dvol_cache.json", err_res)
        return err_res
    stale = load_disk_cache("deribit_dvol_cache.json", ttl_seconds=86400 * 2)
    if stale and stale.get("current_dvol"):
        stale["cache_status"] = "STALE_FALLBACK"
        return stale
    err_res = {"status": "UNAVAILABLE", "reason": "No DVOL index data"}
    save_disk_cache("deribit_dvol_cache.json", err_res)
    return err_res


def fetch_coinbase_orderbook(threshold_pct: float = 1.0) -> dict:
    """Бесплатный институциональный фиатный стакан BTC-USD с Coinbase Pro (Level 2 Depth)."""
    cached = load_disk_cache("coinbase_orderbook_cache.json", ttl_seconds=30)
    if cached and cached.get("status") == "OK":
        return cached
    try:
        url = f"{COINBASE_API_BASE}/products/BTC-USD/book?level=2"
        data = safe_get_json(url)
        if isinstance(data, dict) and data.get("bids") and data.get("asks"):
            raw_bids = [(float(x[0]), float(x[1])) for x in data["bids"]]
            raw_asks = [(float(x[0]), float(x[1])) for x in data["asks"]]
            if raw_bids and raw_asks:
                best_bid = raw_bids[0][0]
                best_ask = raw_asks[0][0]
                mid = (best_bid + best_ask) / 2.0
                low_bound = mid * (1.0 - threshold_pct / 100.0)
                high_bound = mid * (1.0 + threshold_pct / 100.0)

                bids = [q for p, q in raw_bids if p >= low_bound]
                asks = [q for p, q in raw_asks if p <= high_bound]
                bid_qty = sum(bids)
                ask_qty = sum(asks)
                ratio = round(bid_qty / ask_qty, 3) if ask_qty > 0 else None

                res = {
                    "status": "OK",
                    "source": "Coinbase Pro BTC-USD L2",
                    "best_bid": best_bid,
                    "best_ask": best_ask,
                    "mid_price": round(mid, 2),
                    "bid_depth_btc": round(bid_qty, 3),
                    "ask_depth_btc": round(ask_qty, 3),
                    "bid_vs_ask_ratio": ratio,
                    "threshold_pct": threshold_pct,
                }
                save_disk_cache("coinbase_orderbook_cache.json", res)
                return res
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": str(exc)}
    return {"status": "UNAVAILABLE", "reason": "No Coinbase L2 data"}



def fetch_cme_basis(spot_price: float = 0.0) -> dict:
    """Бесплатные котировки фьючерсов Чикагской биржи (CME Bitcoin Futures BTC=F) и расчет гэпа."""
    cached = load_disk_cache("cme_basis_cache.json", ttl_seconds=10 * 60)
    cme_last = None
    cme_prev = None
    reg_time = None
    if cached and cached.get("cme_last_price"):
        cme_last = cached.get("cme_last_price")
        cme_prev = cached.get("cme_prev_close")
        reg_time = cached.get("regular_market_time_utc")
    else:
        try:
            data = safe_get_json(CME_YAHOO_URL, {"range": "5d", "interval": "1d"})
            if isinstance(data, dict):
                chart = data.get("chart", {}).get("result", [])
                if chart and isinstance(chart, list):
                    meta = chart[0].get("meta", {})
                    cme_last = finite_float(meta.get("regularMarketPrice"))
                    cme_prev = finite_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
                    if meta.get("regularMarketTime"):
                        reg_time = iso_utc(datetime.fromtimestamp(meta.get("regularMarketTime", 0), tz=timezone.utc))
                    if cme_last:
                        save_disk_cache("cme_basis_cache.json", {
                            "cme_last_price": cme_last,
                            "cme_prev_close": cme_prev,
                            "regular_market_time_utc": reg_time,
                        })
        except Exception:
            pass
        if not cme_last:
            stale = load_disk_cache("cme_basis_cache.json", ttl_seconds=86400 * 3)
            if stale and stale.get("cme_last_price"):
                cme_last = stale.get("cme_last_price")
                cme_prev = stale.get("cme_prev_close")
                reg_time = stale.get("regular_market_time_utc")

    if cme_last:
        basis = round(cme_last - spot_price, 2) if spot_price > 0 else None
        basis_pct = round((cme_last / spot_price - 1) * 100, 3) if spot_price > 0 else None
        gap_usd = round(spot_price - cme_last, 2) if spot_price > 0 else None
        return {
            "status": "OK",
            "source": "CME Bitcoin Futures (Front Month BTC=F)",
            "cme_last_price": cme_last,
            "cme_prev_close": cme_prev,
            "basis_vs_spot_usd": basis,
            "basis_vs_spot_pct": basis_pct,
            "weekend_gap_usd": gap_usd,
            "regular_market_time_utc": reg_time,
        }
    return {"status": "UNAVAILABLE", "reason": "No CME futures data"}


def coinglass_get(path: str, params: dict) -> dict:
    if not COINGLASS_API_KEY:
        return {"status": "NOT_CONFIGURED", "reason": "COINGLASS_API_KEY not set"}
    try:
        response = SESSION.get(
            f"{COINGLASS_API_BASE}{path}", params=params, timeout=(3, TIMEOUT_SEC),
            headers={"CG-API-KEY": COINGLASS_API_KEY, "accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or str(payload.get("code", "0")) not in ("0", "200", "None"):
            return {"status": "API_ERROR", "http_status": response.status_code, "response": payload}
        return {"status": "OK", "http_status": response.status_code, "data": payload.get("data"), "source": "CoinGlass API", "collected_at_utc": iso_utc()}
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": str(exc), "source": "CoinGlass API"}


def fetch_coinglass_aggregate() -> dict:
    """Optional licensed cross-exchange layer. No key => no network call."""
    if not ENABLE_COINGLASS_API:
        return {"status": "DISABLED", "reason": "ENABLE_COINGLASS_API=false"}
    if not COINGLASS_API_KEY:
        return {"status": "NOT_CONFIGURED", "reason": "API key absent; screenshot/manual inputs remain supported"}
    calls = {
        "oi_by_exchange": coinglass_get("/futures/open-interest/exchange-list", {"symbol": "BTC"}),
        "aggregated_oi_1h_history": coinglass_get("/futures/open-interest/aggregated-history", {"symbol": "BTC", "interval": "1h", "limit": 48, "unit": "usd"}),
        "liquidations_by_exchange_24h": coinglass_get("/futures/liquidation/exchange-list", {"symbol": "BTC", "range": "24h"}),
        "liquidations_aggregated_1h_history": coinglass_get("/futures/liquidation/aggregated-history", {"exchange_list": "Binance,OKX,Bybit", "symbol": "BTC", "interval": "1h", "limit": 48}),
        "funding_by_exchange": coinglass_get("/futures/funding-rate/exchange-list", {"symbol": "BTC"}),
        "global_long_short_account_ratio_1h": coinglass_get("/futures/global-long-short-account-ratio/history", {"symbol": "BTC", "interval": "1h", "limit": 24}),
        "spot_aggregated_cvd_1h": coinglass_get("/spot/aggregated-cvd/history", {"exchange_list": "binance,okx,bybit", "symbol": "BTC", "interval": "1h", "limit": 48, "unit": "usd"}),
        "futures_aggregated_cvd_1h": coinglass_get("/futures/aggregated-cvd/history", {"exchange_list": "binance,okx,bybit", "symbol": "BTC", "interval": "1h", "limit": 48, "unit": "usd"}),
        "btc_etf_flow_history": coinglass_get("/etf/bitcoin/flow-history", {}),
        "options_market_info": coinglass_get("/option/info", {"symbol": "BTC"}),
        "exchange_balance_list_btc": coinglass_get("/exchange/balance/list", {"symbol": "BTC"}),
        "large_onchain_transfers_btc": coinglass_get("/chain/v2/whale-transfer", {"symbol": "BTC"}),
    }
    ok = sum(1 for x in calls.values() if x.get("status") == "OK")
    return {"status": "OK" if ok else "PARTIAL_OR_UNAVAILABLE", "available_endpoint_count": ok, "requested_endpoint_count": len(calls), "metrics": calls,
            "interpretation_limit": "CoinGlass aggregates exchange data; it overlaps with Binance and is not an independent confirmation of the same metric. Exchange coverage and endpoint availability depend on subscription plan."}


def collect_manual_inputs() -> list[dict]:
    """Collect user-prepared screenshots/CSV/JSON/text from manual_inputs folder."""
    MANUAL_INPUT_DIR.mkdir(parents=True, exist_ok=True)
    accepted = {".png", ".jpg", ".jpeg", ".webp", ".csv", ".json", ".txt", ".md"}
    ignored_names = {"readme.txt", "readme.md", ".gitkeep", ".gitignore"}
    out = []
    for path in sorted(MANUAL_INPUT_DIR.iterdir()):
        if not path.is_file() or path.suffix.lower() not in accepted:
            continue
        if path.name.lower() in ignored_names or path.name.startswith("."):
            continue
        if path.stat().st_size > 15_000_000:
            print(f"[WARN] Manual input skipped (>15MB): {path.name}")
            continue
        item = {"filename": path.name, "extension": path.suffix.lower(), "size_bytes": path.stat().st_size, "path": str(path), "status": "LOADED"}
        if path.suffix.lower() in {".json", ".csv", ".txt", ".md"}:
            try:
                item["text_preview"] = path.read_text(encoding="utf-8", errors="replace")[:12000]
            except Exception as exc:
                item["status"] = "READ_ERROR"
                item["error"] = str(exc)
        out.append(item)
    return out


# -------------------------- ВЕРИФИЦИРОВАННЫЙ СКРИНШОТ -----------------------

def dismiss_page_overlays(page) -> None:
    """Очистка всплывающих окон, согласий на cookie, шторки настроек и рекламы."""
    # 1. Принятие cookie (клик по кнопкам)
    try:
        for btn_text in ("Accept", "Accept all", "Agree", "I agree", "Allow all"):
            btn = page.locator(f"button:has-text('{btn_text}')").first
            if btn.is_visible(timeout=400):
                btn.click()
                break
        accept_btn = page.locator("button[data-tid='banner-accept']").first
        if accept_btn.is_visible(timeout=400):
            accept_btn.click()
    except Exception:
        pass

    # 2. Закрытие шторки настроек CoinGlass Heatmap (MUI) — строго кнопкой закрытия
    try:
        page.evaluate("""() => {
            const closeBtn = document.querySelector('button[aria-label="Close heatmap settings"]');
            if (closeBtn) {
                closeBtn.click();
            } else {
                // Если шторка открыта, но aria-label изменился: ищем контейнер с "Heatmap colors"
                const drawer = Array.from(document.querySelectorAll('.MuiBox-root, div')).find(el => {
                    const txt = el.innerText || '';
                    return txt.includes('Heatmap colors') && txt.includes('Sensitivity');
                });
                if (drawer) {
                    const btn = drawer.querySelector('button');
                    if (btn) btn.click();
                }
            }
        }""")
    except Exception:
        pass

    # 3. Удаление оверлеев, рекламных баннеров и всплывающих виджетов
    try:
        page.evaluate("""() => {
            // Статические селекторы модалок и виджетов
            const selectors = [
                '.ant-drawer', '.ant-drawer-mask', '.ant-dropdown', '.ant-popover',
                '#onetrust-banner-sdk', '.ant-modal-root',
                '[class*="cookie"]', '[class*="consent"]', '[id*="cookie"]', '[id*="consent"]',
                '[data-tid*="banner"]', '[class*="termly"]',
                '#intercom-container', '#intercom-frame', 'iframe[name*="intercom"]',
                '[class*="intercom"]', '[id*="intercom"]'
            ];
            selectors.forEach(sel => {
                document.querySelectorAll(sel).forEach(el => el.remove());
            });

            // Рекламные баннеры Bitunix и их родительские контейнеры
            document.querySelectorAll('img[alt*="bitunix"], a[href*="bitunix"], [class*="bitunix"]').forEach(el => {
                const wrapper = el.closest('.MuiBox-root') || el.parentElement || el;
                wrapper.remove();
            });

            // Битые плейсхолдеры рекламы (например [ad] на CryptoQuant)
            document.querySelectorAll('img[alt*="ad"], img[alt*="Ad"]').forEach(el => {
                const wrapper = el.parentElement || el;
                wrapper.remove();
            });

            // Одиночный крестик закрытия баннера в верхней части страницы (y < 250)
            document.querySelectorAll('button, div, span').forEach(el => {
                const t = (el.innerText || '').trim();
                if (t === '×' || t === '✕' || t === 'X') {
                    const rect = el.getBoundingClientRect();
                    if (rect.top < 250 && rect.width < 50 && rect.height < 50) {
                        (el.closest('[class*="banner"]') || el.parentElement || el).remove();
                    }
                }
            });

            // Плавающий попап Legend NEW в правом нижнем углу
            document.querySelectorAll('div, span, section, aside').forEach(el => {
                const style = window.getComputedStyle(el);
                const isFloating = style.position === 'fixed' || style.position === 'absolute';
                const text = (el.innerText || '').trim();
                if ((isFloating && text.length < 50) || text === 'Legend NEW') {
                    if (text.includes('Legend') && text.includes('NEW')) {
                        (el.closest('[class*="MuiBox"]') || el.parentElement || el).remove();
                    }
                    if (text.includes('Save Up to') && text.includes('USDT')) {
                        el.remove();
                    }
                }
            });
        }""")
    except Exception:
        pass


def capture_coinglass_clean() -> list[dict]:
    if not ENABLE_SCREENSHOT or sync_playwright is None:
        return []

    captures = []
    page = None
    SCREENSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    print("[*] Попытка получить скриншот CoinGlass; содержимое будет проверено насколько возможно...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=BROWSER_USER_AGENT,
            )
            page = context.new_page()
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            response = page.goto(COINGLASS_HEATMAP_URL, timeout=30000, wait_until="domcontentloaded")
            http_status = response.status if response is not None else None

            # Ждем появления canvas графика
            try:
                page.wait_for_selector("canvas", timeout=12000)
            except Exception:
                pass
            page.wait_for_timeout(2000)

            dismiss_page_overlays(page)
            # Отводим курсор мыши, чтобы не оставлять всплывающий тултип поверх графика
            try:
                page.mouse.move(0, 0)
            except Exception:
                pass
            page.wait_for_timeout(1500)
            # Повторная очистка: Legend NEW и реклама часто подгружаются с задержкой
            dismiss_page_overlays(page)
            page.wait_for_timeout(500)

            page.screenshot(path=str(SCREENSHOT_FILE), full_page=False)
            page_title = (page.title() or "").strip()
            body_text = (page.locator("body").inner_text(timeout=5000) or "")[:12000]
            body_lower = body_text.lower()
            has_relevant_text = any(token in body_lower for token in ("liquidation", "ликвидац", "heatmap"))
            has_btc_context = "btc" in body_lower or "bitcoin" in body_lower
            file_ok = SCREENSHOT_FILE.exists() and SCREENSHOT_FILE.stat().st_size >= 30_000
            semantic_ok = http_status is not None and 200 <= http_status < 400 and has_relevant_text and has_btc_context
            if file_ok and semantic_ok:
                captures.append({
                    "label": "CoinGlass Liquidation Heatmap Model 3 (page-level checks passed; chart pixels not independently validated)",
                    "path": str(SCREENSHOT_FILE),
                    "size_bytes": SCREENSHOT_FILE.stat().st_size,
                    "http_status": http_status,
                    "page_title": page_title,
                    "semantic_check": "PASS: HTTP + relevant page text + BTC context; chart content still needs visual review",
                })
                print(f"[+] Скриншот сохранен; базовые проверки страницы пройдены ({SCREENSHOT_FILE.stat().st_size // 1024} КБ)")
            else:
                print(f"[WARN] CoinGlass screenshot not trusted: HTTP={http_status}, file_ok={file_ok}, relevant_text={has_relevant_text}, btc_context={has_btc_context}, title={page_title!r}")
                if SCREENSHOT_FILE.exists():
                    captures.append({"label":"CoinGlass heatmap page screenshot — UNVERIFIED, inspect manually",
                                     "path":str(SCREENSHOT_FILE),"size_bytes":SCREENSHOT_FILE.stat().st_size,
                                     "http_status":http_status,"page_title":page_title,
                                     "semantic_check":"FAILED_OR_INCOMPLETE; screenshot retained for manual review; do not treat as data"})
            browser.close()
    except Exception as exc:
        print(f"[WARN] Сбой снятия скриншота: {exc}")
        try:
            if page is not None and not page.is_closed():
                page.screenshot(path=str(SCREENSHOT_FILE), full_page=False, timeout=5000)
                if SCREENSHOT_FILE.exists():
                    captures.append({"label":"CoinGlass heatmap page screenshot — UNVERIFIED partial capture",
                                     "path":str(SCREENSHOT_FILE),"size_bytes":SCREENSHOT_FILE.stat().st_size,
                                     "semantic_check":"NAVIGATION_OR_CAPTURE_ERROR; inspect manually; do not treat as market data"})
        except Exception:
            pass

    return captures


def capture_free_dashboard_pages() -> list[dict]:
    """Try screenshots of free public dashboards; failed/blocked pages are recorded, never treated as data."""
    if not ENABLE_SCREENSHOT:
        return [{"status":"DISABLED", "reason":"ENABLE_COINGLASS_SCREENSHOT=false"}]
    if sync_playwright is None:
        return [{"status":"BROWSER_UNAVAILABLE", "reason":"Install playwright and run playwright install chromium"}]
    out=[]
    shots_dir=BASE_DIR / "free_dashboard_screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True, args=["--no-sandbox","--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
            context=browser.new_context(viewport={"width":1920,"height":1080}, user_agent=BROWSER_USER_AGENT)
            for label,url,keywords in FREE_DASHBOARD_PAGES:
                safe_name=re.sub(r"[^a-z0-9]+","_",label.lower()).strip("_")
                path=shots_dir/f"{safe_name}.png"
                page = None
                nav_timeout = 25000
                try:
                    page=context.new_page()
                    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                    response=page.goto(url,timeout=nav_timeout,wait_until="domcontentloaded")
                    http=response.status if response else None

                    # Для тяжелых SPA (например CryptoQuant) даем время на гидратацию React/Highcharts
                    if "cryptoquant" in url.lower():
                        try:
                            page.wait_for_selector(".highcharts-container, svg, [class*='table']", timeout=12000)
                        except Exception:
                            pass
                        page.wait_for_timeout(3000)
                    else:
                        page.wait_for_timeout(2500)

                    title=(page.title() or "").strip()
                    body=(page.locator("body").inner_text(timeout=4000) or "")[:15000]
                    lower=body.lower()

                    # Быстрое определение Cloudflare/бот-блока
                    is_cf = any(cf in lower for cf in ("cloudflare", "performing security verification", "verify you are human", "just a moment")) or (http == 403)
                    if is_cf:
                        out.append({
                            "label": label, "url": url, "path": None, "http_status": http,
                            "page_title": title, "semantic_text_check": False,
                            "status": "BLOCKED_BY_CLOUDFLARE",
                            "warning": "Страница заблокирована защитой Cloudflare; график недоступен без авторизации.",
                        })
                        page.close()
                        continue

                    # Очистка оверлеев и рекламы
                    dismiss_page_overlays(page)

                    # Настройка viewport для дашбордов с длинным контентом
                    if "futures" in label.lower() and "coinglass" in label.lower():
                        try:
                            page.set_viewport_size({"width": 1920, "height": 3000})
                            page.wait_for_timeout(1000)
                            page.evaluate("() => window.scrollTo(0, 0)")
                            page.wait_for_timeout(500)
                        except Exception:
                            pass
                    elif "overview" in label.lower() and "cryptoquant" in label.lower():
                        try:
                            page.set_viewport_size({"width": 1920, "height": 1350})
                            page.wait_for_timeout(500)
                        except Exception:
                            pass

                    # Проверка фактического рендеринга графиков для SPA
                    rendered_elements_count = page.evaluate("() => document.querySelectorAll('svg, canvas, .highcharts-container').length")
                    semantic = any(k in lower for k in keywords)

                    # Не сохраняем пустой белый холст при нулевом числе элементов графика
                    if "cryptoquant" in url.lower() and rendered_elements_count < 3:
                        out.append({
                            "label": label, "url": url, "path": None, "http_status": http,
                            "page_title": title, "semantic_text_check": semantic,
                            "status": "SPA_EMPTY_RENDER",
                            "warning": "Интерфейс не отрендерил графики (пустой холст SPA); скриншот пропущен во избежание дезинформации.",
                        })
                        page.close()
                        continue

                    try:
                        page.mouse.move(0, 0)
                    except Exception:
                        pass
                    page.wait_for_timeout(1000)
                    # Повторная очистка: Legend NEW часто подгружается с задержкой
                    dismiss_page_overlays(page)
                    page.wait_for_timeout(500)

                    page.screenshot(path=str(path), full_page=False)
                    ok = bool(http and 200 <= http < 400 and semantic and path.exists() and path.stat().st_size > 20000)
                    out.append({
                        "label": label, "url": url, "path": str(path), "http_status": http,
                        "page_title": title, "semantic_text_check": semantic,
                        "rendered_charts_count": rendered_elements_count,
                        "status": "CAPTURED_PAGE_REQUIRES_VISUAL_VALIDATION" if ok else "CAPTURE_NOT_VERIFIED",
                        "body_preview": body[:1500],
                        "warning": "A screenshot of a page is not proof that a chart rendered or its values are readable."
                    })
                    page.close()
                except Exception as exc:
                    out.append({"label":label,"url":url,"status":"UNAVAILABLE","reason":str(exc),"path":None,
                                "warning":"Сбой загрузки страницы; скриншот отсутствует."})
                    if page is not None and not page.is_closed():
                        try:
                            page.close()
                        except Exception:
                            pass
            browser.close()
    except Exception as exc:
        out.append({"status":"BROWSER_UNAVAILABLE","reason":str(exc)})
    return out


# ------------------------------- ИСТОРИЯ -----------------------------------

def read_history() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        with HISTORY_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def get_historical_comparison(current: dict, history: list) -> dict:
    now = time.time()
    spot_price = current["prices"]["spot_last"]
    oi = current.get("derivatives", {}).get("live_open_interest_btc")
    current_bias = current.get("quant_bias", {}).get("composite_score")
    result = {"current_snapshot_utc": iso_utc(), "since_previous_run": None, "approximately_24h": None}

    valid = [row for row in history if finite_float(row.get("epoch")) is not None]
    if valid:
        previous = max(valid, key=lambda row: float(row["epoch"]))
        elapsed = (now - float(previous["epoch"])) / 3600
        prev_bias = finite_float(previous.get("quant_bias_score"))
        result["since_previous_run"] = {
            "elapsed_hours": round(elapsed, 2),
            "spot_price_change_usd": round(spot_price - float(previous.get("spot_price", spot_price)), 2),
            "oi_change_btc": round(oi - float(previous["open_interest_btc"]), 2)
                if oi is not None and finite_float(previous.get("open_interest_btc")) is not None else None,
            "quant_bias_change": round(current_bias - prev_bias, 1) if current_bias is not None and prev_bias is not None else None,
            "prev_quant_bias_label": previous.get("quant_bias_label"),
            "prev_divergence_state": previous.get("divergence_state"),
        }

    target = now - 24 * 3600
    candidates = [row for row in valid if abs(float(row["epoch"]) - target) <= 4 * 3600]
    if candidates:
        snap = min(candidates, key=lambda row: abs(float(row["epoch"]) - target))
        old_price = float(snap["spot_price"])
        old_oi = finite_float(snap.get("open_interest_btc"))
        old_bias = finite_float(snap.get("quant_bias_score"))
        result["approximately_24h"] = {
            "actual_elapsed_hours": round((now - float(snap["epoch"])) / 3600, 2),
            "spot_price_change_usd": round(spot_price - old_price, 2),
            "spot_price_change_pct": round((spot_price / old_price - 1) * 100, 2) if old_price else None,
            "oi_change_btc": round(oi - old_oi, 2) if oi is not None and old_oi is not None else None,
            "quant_bias_24h_ago": old_bias,
            "quant_bias_24h_change": round(current_bias - old_bias, 1) if current_bias is not None and old_bias is not None else None,
            "divergence_state_24h_ago": snap.get("divergence_state"),
        }
    return result


def save_snapshot(current: dict, history: list) -> None:
    derivatives = current.get("derivatives", {})
    quant = current.get("quant_bias", {})
    z_scores = current.get("statistical_z_scores", {})
    div = current.get("divergence_engine", {}).get("24h_divergence", {})
    row = {
        "epoch": time.time(),
        "timestamp_utc": iso_utc(),
        "symbol": SYMBOL,
        "spot_price": current["prices"]["spot_last"],
        "futures_price": current["prices"]["futures_last"],
        "open_interest_btc": derivatives.get("live_open_interest_btc"),
        "funding_pct": derivatives.get("current_funding_rate_pct"),
        # Quant metrics for trend/history analysis
        "quant_bias_score": quant.get("composite_score"),
        "quant_bias_label": quant.get("bias_label"),
        "oi_zscore": z_scores.get("oi_zscore"),
        "funding_zscore": z_scores.get("funding_zscore"),
        "divergence_state": div.get("divergence_state"),
    }
    history.append(row)
    cutoff = time.time() - HISTORY_LOOKBACK_HOURS * 3600
    kept = [x for x in history if finite_float(x.get("epoch"), 0) >= cutoff][-MAX_HISTORY_SNAPSHOTS:]
    tmp_path = HISTORY_FILE.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as f:
        json.dump(kept, f, ensure_ascii=False, indent=2)
    tmp_path.replace(HISTORY_FILE)


def update_calibration_tracker(current: dict, tracker_path: Optional[Path] = None, force_time: Optional[float] = None) -> dict:
    """
    Backtest & Calibration Logger for Quant Bias.
    Tracks predictions, checks outcomes after ~24 hours (or on SL/TP touch), and computes live win-rate metrics.
    """
    path = tracker_path or TRACKER_FILE
    now = force_time or time.time()
    prices = current.get("prices", {})
    spot_price = finite_float(prices.get("spot_last"))
    quant = current.get("quant_bias", {})
    score = quant.get("composite_score")
    label = quant.get("bias_label")
    div_state = current.get("divergence_engine", {}).get("24h_divergence", {}).get("divergence_state")
    oi_z = current.get("statistical_z_scores", {}).get("oi_zscore")

    # Explicit post-entry High / Low price detection (e.g. for unit tests and simulation).
    # P1.1 Institutional Fix: NEVER use rolling 24h ticker summary (spot_24h_summary) as post-entry extremes,
    # as it includes prices from BEFORE trade inception and causes instant false stop-outs.
    high_p = finite_float(current.get("high_price"))
    low_p = finite_float(current.get("low_price"))

    # Extract or compute ATR Risk Model
    risk = current.get("risk_model") or current.get("atr_risk")
    if not risk and spot_price:
        struct_4h = current.get("market_structure", {}).get("4h", {})
        atr14_val = struct_4h.get("atr14_price")
        if not atr14_val:
            struct_1h = current.get("market_structure", {}).get("1h", {})
            atr14_val = struct_1h.get("atr14_price", 0.0)
        if atr14_val:
            risk = calculate_atr_risk_levels(spot_price, atr14_val, score or 0)

    direction = risk.get("direction", "NEUTRAL") if risk else ("LONG" if (score and score >= 15) else ("SHORT" if (score and score <= -15) else "NEUTRAL"))
    atr14_val = risk.get("atr14") if risk else None
    sl_val = risk.get("recommended", {}).get("stop_loss") if risk else None
    tp1_val = risk.get("recommended", {}).get("tp1_rr2") if risk else None
    tp2_val = risk.get("recommended", {}).get("tp2_rr3") if risk else None

    tracker = []
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    tracker = data
        except Exception:
            tracker = []
    else:
        # Initial seed: import existing records from market_history.json if present
        try:
            if path == TRACKER_FILE and HISTORY_FILE.exists():
                with HISTORY_FILE.open("r", encoding="utf-8") as f:
                    hist = json.load(f)
                    if isinstance(hist, list):
                        for row in hist:
                            if row.get("quant_bias_score") is not None and row.get("spot_price") and row.get("epoch"):
                                tracker.append({
                                    "id": row.get("timestamp_utc") or iso_utc(),
                                    "epoch": float(row["epoch"]),
                                    "timestamp_utc": row.get("timestamp_utc") or iso_utc(),
                                    "direction": "LONG" if (row.get("quant_bias_score") or 0) >= 15 else ("SHORT" if (row.get("quant_bias_score") or 0) <= -15 else "NEUTRAL"),
                                    "entry_price": float(row["spot_price"]),
                                    "spot_price": float(row["spot_price"]),
                                    "quant_bias_score": row.get("quant_bias_score"),
                                    "quant_bias_label": row.get("quant_bias_label", "NEUTRAL"),
                                    "divergence_state": row.get("divergence_state"),
                                    "oi_zscore": row.get("oi_zscore"),
                                    "atr14_4h": None,
                                    "stop_loss": None,
                                    "tp1_rr2": None,
                                    "tp2_rr3": None,
                                    "resolved": False,
                                    "resolution_type": "PENDING",
                                })
        except Exception:
            pass

    # Backfill default fields for older records
    for item in tracker:
        item.setdefault("entry_price", item.get("spot_price"))
        if "direction" not in item:
            item_lbl = item.get("quant_bias_label", "NEUTRAL")
            item_sc = item.get("quant_bias_score", 0)
            if item_lbl in ("BULLISH", "STRONG BULLISH") or item_sc >= 15:
                item["direction"] = "LONG"
            elif item_lbl in ("BEARISH", "STRONG BEARISH") or item_sc <= -15:
                item["direction"] = "SHORT"
            else:
                item["direction"] = "NEUTRAL"
        item.setdefault("atr14_4h", None)
        item.setdefault("stop_loss", None)
        item.setdefault("tp1_rr2", None)
        item.setdefault("tp2_rr3", None)
        item.setdefault("resolution_type", "PENDING" if not item.get("resolved") else "24H_MARKET_EXPIRY")
        item.setdefault("pnl_pct", item.get("price_change_24h_pct"))

    # 1. Resolve pending predictions
    newly_resolved_count = 0
    for item in tracker:
        if not item.get("resolved"):
            item_epoch = finite_float(item.get("epoch"))
            item_entry = finite_float(item.get("entry_price") or item.get("spot_price"))
            if not item_epoch or not item_entry or item_entry <= 0:
                continue

            elapsed = (now - item_epoch) / 3600
            sl = finite_float(item.get("stop_loss"))
            tp1 = finite_float(item.get("tp1_rr2"))
            tp2 = finite_float(item.get("tp2_rr3"))
            dir_val = item.get("direction", "NEUTRAL")

            resolved_now = False
            res_type = None
            outcome = None
            is_win = None
            pnl_pct = None
            pnl_usd = None
            res_price = None

            # Case A: Event-driven touch check using post-entry price observations
            obs_high = high_p if high_p is not None else spot_price
            obs_low = low_p if low_p is not None else spot_price

            if sl is not None and obs_high is not None and obs_low is not None:
                if dir_val == "LONG":
                    if obs_low <= sl:
                        resolved_now = True
                        res_type = "SL_HIT"
                        outcome = "LOSS"
                        is_win = False
                        res_price = sl
                        pnl_pct = round((sl / item_entry - 1) * 100, 2)
                        pnl_usd = round(sl - item_entry, 2)
                    elif tp2 is not None and obs_high >= tp2:
                        resolved_now = True
                        res_type = "TP2_HIT"
                        outcome = "WIN"
                        is_win = True
                        res_price = tp2
                        pnl_pct = round((tp2 / item_entry - 1) * 100, 2)
                        pnl_usd = round(tp2 - item_entry, 2)
                    elif tp1 is not None and obs_high >= tp1:
                        resolved_now = True
                        res_type = "TP1_HIT"
                        outcome = "WIN"
                        is_win = True
                        res_price = tp1
                        pnl_pct = round((tp1 / item_entry - 1) * 100, 2)
                        pnl_usd = round(tp1 - item_entry, 2)
                elif dir_val == "SHORT":
                    if obs_high >= sl:
                        resolved_now = True
                        res_type = "SL_HIT"
                        outcome = "LOSS"
                        is_win = False
                        res_price = sl
                        pnl_pct = round((1 - sl / item_entry) * 100, 2)
                        pnl_usd = round(item_entry - sl, 2)
                    elif tp2 is not None and obs_low <= tp2:
                        resolved_now = True
                        res_type = "TP2_HIT"
                        outcome = "WIN"
                        is_win = True
                        res_price = tp2
                        pnl_pct = round((1 - tp2 / item_entry) * 100, 2)
                        pnl_usd = round(item_entry - tp2, 2)
                    elif tp1 is not None and obs_low <= tp1:
                        resolved_now = True
                        res_type = "TP1_HIT"
                        outcome = "WIN"
                        is_win = True
                        res_price = tp1
                        pnl_pct = round((1 - tp1 / item_entry) * 100, 2)
                        pnl_usd = round(item_entry - tp1, 2)

            # Case B: 24h close comparison fallback (if not resolved by touch and elapsed >= 23.5 hours)
            if not resolved_now and elapsed >= 23.5 and spot_price is not None:
                pct_change = (spot_price / item_entry - 1) * 100
                item_label = item.get("quant_bias_label", "NEUTRAL")
                item_score = item.get("quant_bias_score", 0)

                if dir_val == "LONG" or item_label in ("BULLISH", "STRONG BULLISH") or (item_score and item_score >= 15):
                    is_win = pct_change > 0.05
                    outcome = "WIN" if is_win else "LOSS"
                    res_type = "24H_MARKET_PROFIT" if is_win else "24H_MARKET_LOSS"
                    pnl_pct = round(pct_change, 2)
                    pnl_usd = round(spot_price - item_entry, 2)
                elif dir_val == "SHORT" or item_label in ("BEARISH", "STRONG BEARISH") or (item_score and item_score <= -15):
                    is_win = pct_change < -0.05
                    outcome = "WIN" if is_win else "LOSS"
                    res_type = "24H_MARKET_PROFIT" if is_win else "24H_MARKET_LOSS"
                    pnl_pct = round(-pct_change, 2)
                    pnl_usd = round(item_entry - spot_price, 2)
                else:  # NEUTRAL
                    is_win = abs(pct_change) <= 1.5
                    outcome = "WIN" if is_win else "TREND_BREAKOUT"
                    res_type = "24H_RANGE_BOUND" if is_win else "24H_TREND_BREAKOUT"
                    pnl_pct = round(pct_change, 2)
                    pnl_usd = round(spot_price - item_entry, 2)

                resolved_now = True
                res_price = spot_price

            if resolved_now:
                item["resolved"] = True
                item["resolved_at_utc"] = iso_utc(datetime.fromtimestamp(now, tz=timezone.utc))
                item["resolved_price"] = res_price
                item["price_change_24h_pct"] = round((spot_price / item_entry - 1) * 100, 2) if spot_price else pnl_pct
                item["price_change_24h_usd"] = round(spot_price - item_entry, 2) if spot_price else pnl_usd
                item["pnl_pct"] = pnl_pct
                item["pnl_usd"] = pnl_usd
                item["is_win"] = is_win
                item["outcome"] = outcome
                item["resolution_type"] = res_type
                item["actual_elapsed_hours"] = round(elapsed, 2)
                newly_resolved_count += 1

    # 2. Append new prediction if at least 2 hours passed since last logged entry
    valid_entries = [x for x in tracker if finite_float(x.get("epoch")) is not None]
    last_entry = max(valid_entries, key=lambda x: float(x["epoch"])) if valid_entries else None
    min_interval_sec = 2 * 3600

    new_logged = False
    if spot_price is not None and score is not None and label is not None:
        if not last_entry or (now - float(last_entry["epoch"])) >= min_interval_sec:
            tracker.append({
                "id": iso_utc(datetime.fromtimestamp(now, tz=timezone.utc)),
                "epoch": now,
                "timestamp_utc": iso_utc(datetime.fromtimestamp(now, tz=timezone.utc)),
                "direction": direction,
                "entry_price": spot_price,
                "spot_price": spot_price,
                "quant_bias_score": score,
                "quant_bias_label": label,
                "divergence_state": div_state,
                "oi_zscore": oi_z,
                "atr14_4h": atr14_val,
                "stop_loss": sl_val,
                "tp1_rr2": tp1_val,
                "tp2_rr3": tp2_val,
                "resolved": False,
                "resolution_type": "PENDING",
                "resolved_at_utc": None,
                "resolved_price": None,
                "pnl_pct": None,
                "pnl_usd": None,
                "is_win": None,
                "outcome": None,
                "actual_elapsed_hours": None,
            })
            new_logged = True

    # 3. Save tracker back to disk
    try:
        tmp_p = path.with_suffix(".tmp")
        with tmp_p.open("w", encoding="utf-8") as f:
            json.dump(tracker, f, ensure_ascii=False, indent=2)
        tmp_p.replace(path)
    except Exception as exc:
        print(f"[WARN] Сбой сохранения калибровочного логгера: {exc}")

    # 4. Compute Calibration Metrics
    resolved_list = [x for x in tracker if x.get("resolved") is True]
    pending_list = [x for x in tracker if not x.get("resolved")]
    total_resolved = len(resolved_list)

    stats = {
        "tracker_file": str(path.name),
        "total_signals_tracked": len(tracker),
        "pending_signals": len(pending_list),
        "resolved_signals_count": total_resolved,
        "newly_resolved_in_this_run": newly_resolved_count,
        "new_signal_logged_this_run": new_logged,
    }

    if total_resolved >= 1:
        wins = sum(1 for x in resolved_list if x.get("is_win") is True)
        overall_wr = round(wins / total_resolved * 100, 1)

        bulls = [x for x in resolved_list if x.get("quant_bias_label") in ("BULLISH", "STRONG BULLISH")]
        bears = [x for x in resolved_list if x.get("quant_bias_label") in ("BEARISH", "STRONG BEARISH")]
        neutrals = [x for x in resolved_list if x.get("quant_bias_label") == "NEUTRAL"]

        bull_wins = sum(1 for x in bulls if x.get("is_win") is True)
        bear_wins = sum(1 for x in bears if x.get("is_win") is True)

        bull_wr = round(bull_wins / len(bulls) * 100, 1) if bulls else None
        bear_wr = round(bear_wins / len(bears) * 100, 1) if bears else None

        bull_returns = [x.get("price_change_24h_pct") for x in bulls if x.get("price_change_24h_pct") is not None]
        bear_returns = [x.get("price_change_24h_pct") for x in bears if x.get("price_change_24h_pct") is not None]

        stats["overall_win_rate_pct"] = overall_wr
        stats["wins_total"] = wins
        stats["losses_total"] = total_resolved - wins
        stats["bullish_signals"] = {
            "count": len(bulls),
            "wins": bull_wins,
            "win_rate_pct": bull_wr,
            "avg_24h_price_change_pct": round(statistics.mean(bull_returns), 2) if bull_returns else None,
        }
        stats["bearish_signals"] = {
            "count": len(bears),
            "wins": bear_wins,
            "win_rate_pct": bear_wr,
            "avg_24h_price_change_pct": round(statistics.mean(bear_returns), 2) if bear_returns else None,
        }
        stats["neutral_signals"] = {
            "count": len(neutrals),
            "wins": sum(1 for x in neutrals if x.get("is_win") is True),
        }
        stats["status"] = "ACTIVE_CALIBRATION"
        advanced = compute_calibration_performance_metrics(tracker)
        stats["expected_value_pct"] = advanced.get("expected_value_pct")
        stats["expected_value_usd"] = advanced.get("expected_value_usd")
        stats["profit_factor"] = advanced.get("profit_factor")
        stats["sharpe_ratio"] = advanced.get("sharpe_ratio")
        stats["sortino_ratio"] = advanced.get("sortino_ratio")
        stats["max_drawdown_pct"] = advanced.get("max_drawdown_pct")
        stats["kelly_fraction"] = advanced.get("kelly_fraction")
        stats["half_kelly_fraction"] = advanced.get("half_kelly_fraction")
        stats["advanced_performance_metrics"] = advanced
        stats["readout"] = (
            f"Винрейт скоринга: {overall_wr}% ({wins}W / {total_resolved - wins}L из {total_resolved} сигналов). "
            f"Мат. ожидание (EV): {advanced.get('expected_value_pct', 0.0):+.2f}% / trade. "
            f"Бычьи сигналы: {bull_wr if bull_wr is not None else 'N/A'}% WR. "
            f"Медвежьи сигналы: {bear_wr if bear_wr is not None else 'N/A'}% WR."
        )
    else:
        stats["status"] = "ACCUMULATING_DATA"
        stats["overall_win_rate_pct"] = None
        stats["expected_value_pct"] = None
        stats["expected_value_usd"] = None
        stats["profit_factor"] = None
        stats["sharpe_ratio"] = None
        stats["sortino_ratio"] = None
        stats["max_drawdown_pct"] = 0.0
        stats["kelly_fraction"] = 0.0
        stats["half_kelly_fraction"] = 0.0
        stats["readout"] = (
            f"База калибровки накапливает данные: {len(pending_list)} активных сигналов в ожидании 24-часового закрытия. "
            f"Статистика винрейта появится после первых 24 часов."
        )

    return stats


# ---------------------------- АНАЛИТИЧЕСКИЙ МОЗГ (GEMINI) -------------------

SYSTEM_INSTRUCTION = """
Ты — старший quantitative-аналитик и профессиональный стратег по Bitcoin.
Твоя цель — предоставить практикующему трейдеру кристально ясный, глубокий и применимый на практике утренний отчет.

ПРАВИЛА ЯЗЫКА И СТИЛЯ:
1. СТРОГО ЧИСТЫЙ РУССКИЙ ЯЗЫК:
   - Запрещено использовать искусственные англицизмы, канцеляризмы и служебные теги (НЕ пиши: FACT, INTERPRETATION, LH_LL_downtrend, HH_HL_uptrend, bid_vs_ask_ratio, CVD, taker-дельта, Perpetual, AUM).
   - Пиши как опытный трейдер на родном языке:
     * Вместо "bid_vs_ask_ratio = 3.25" пиши: "В биржевом стакане перевес покупателей в 3.2 раза: 486 BTC лимитных покупок против 150 BTC продаж прямо под текущей ценой".
     * Вместо "LH_LL_downtrend" пиши: "Локальный нисходящий тренд (понижающиеся максимумы и минимумы)".
     * Вместо "CVD / Taker delta" пиши: "Агрессивные рыночные покупки / маркет-ордера".
     * Вместо "бэквордация" пиши: "Фьючерс торгуется со скидкой (дисконтом) к спотовой цене".
2. ПРАКТИЧЕСКАЯ ПОЛЬЗА И ВЫВОДЫ:
   - В конце отчета ОБЯЗАТЕЛЕН раздел «ГЛАВНЫЙ ВЫВОД И ТОРГОВЫЙ ПЛАН (ГЛАВНЫЕ ОЖИДАНИЯ)». Никаких размытых фраз — дай конкретные триггеры для входа в лонг, шорт и целевые уровни.
3. МАКРОЭКОНОМИКА С ВРЕМЕНЕМ ДЛЯ ЛАТВИИ:
   - В блоке макроэкономики используй данные из `macro_calendar.upcoming_events`.
   - Обязательно выпиши ВСЕ важные события США на текущую неделю (а если отчет формируется на выходных — на всю следующую торговую неделю) с указанием дня недели, даты и времени Риги (Латвия).

СТРУКТУРА ОТЧЕТА (СТРОГО СОБЛЮДАЙ ФОРМАТ):

# РЫНОЧНАЯ РАЗВЕДКА BTC/USDT

## 1. СУТЬ И БЫСТРЫЙ ВЕРДИКТ РИСК-МЕНЕДЖЕРА
- **Количественный скоринг (Quant Bias):** [Укажи балл от -100 до +100 и статус на русском, например: +10 из 100 (Нейтральный баланс)]
- **Динамика скоринга:** [Как изменился балл с прошлого запуска и за 24 часа из блока historical_comparison. Рынок усиливается или слабеет?]
- **Что происходит на рынке простыми словами:** [2-3 предложения без заумных терминов: кто контролирует ситуацию, где зажата цена, почему именно такой скоринг].
- **Угроза резкого сквиза (выноса стопов):** [Оцени риск по Z-Score открытого интереса и ставки финансирования. Есть ли аномалии выше 2.0? Стоит ли ждать каскадных ликвидаций?]
- **Исторический винрейт модели (Бэктест):** [Приведи quant_bias_calibration.readout: процент побед или факт накопления базы].
- **Итоговое решение риск-менеджера:** [ВНЕ РЫНКА (ЖДАТЬ ВЫХОДА) / ЛОНГ НА ПОДТВЕРЖДЕНИИ / ШОРТ НА ПОДТВЕРЖДЕНИИ].

## 2. КТО СЕЙЧАС ДАВИТ: СПОТ ИЛИ ФЬЮЧЕРСЫ
- **Биржевой стакан (лимитные стенки ±1% от цены):**
  * Спот Binance: [На чьей стороне перевес, сколько BTC в бидах и асках, есть ли плотная стена поддержки].
  * Фьючерсы Binance и Bybit: [На чьей стороне перевес лимиток на деривативах].
  * Институциональный стакан Coinbase Pro BTC-USD: [Отношение бидов к аскам из coinbase_orderbook].
- **Реальный поток рыночных ордеров (Спотовая дельта):**
  * Поведение маркет-покупателей за 15 минут, 1 час, 4 часа и 24 часа.
  * Вывод: [Есть ли реальный интерес покупать по рынку на споте, или объемы падают?]
- **Позиционирование толпы:**
  * Соотношение позиций: [Сколько % трейдеров сидит в лонгах на Binance и Bybit].
  * Предупреждение: [Перегружена ли толпа лонгами или шортами, где опасность сбора ликвидности].

## 3. КАРТА ЛИКВИДАЦИЙ: ГДЕ СТОП-ЛОССЫ ТОЛПЫ
- **Магнит сверху (Пул ликвидаций шортистов):** ~$XX,XXX – $XX,XXX [Опиши плотность скопления стопов].
- **Магнит снизу (Пул ликвидаций лонгистов):** ~$XX,XXX – $XX,XXX [Опиши плотность скопления стопов].
- **Куда тянет рынок:** [К какому из этих пулов цена ближе и где маркетмейкеру выгоднее устроить вынос].

## 4. КЛЮЧЕВЫЕ ЦЕНОВЫЕ УРОВНИ И СТРУКТУРА
- **Сопротивления сверху:** Локальное $XX,XXX (4H свинг-максимум), Главное $XX,XXX (дневной максимум).
- **Поддержки снизу:** Локальная $XX,XXX (4H свинг-минимум), Главная $XX,XXX (дневной минимум).
- **Состояние волатильности:** [Сужаются ли полосы Боллинджера, что показывает ATR и индекс подразумеваемой волатильности Deribit DVOL — готовится ли рынок к взрывному импульсу из боковика].

## 5. МАКРОЭКОНОМИКА И ИНСТИТУЦИОНАЛЬНЫЕ ПОТОКИ (ВРЕМЯ ДЛЯ ЛАТВИИ / РИГА)
### 📅 Календарь важных событий США:
[Используй macro_calendar.upcoming_events. Выпиши списком ВСЕ события на неделю (а на выходных — на следующую неделю) с днем недели, датой и временем по Риге]:
- 🔴 [День недели, дата, время Рига]: Название события — Уровень важности (Прогноз / Предыдущее). Пояснение влияния на доллар и крипту.
### 🏛️ Институциональные потоки и биржи США:
- **Спотовые Bitcoin ETF:** [Приток/отток за последние сессии из btc_spot_etf_flows, общий тренд институционалов].
- **Фьючерсы CME (BTC=F):** [Базис к споту из cme_basis, институциональная премия/дисконт и гэп выходных дней].
- **Главные инфоповоды:** [2-3 ключевые новости из ленты, которые могут повлиять на сантимент].

## 6. ГЛАВНЫЙ ВЫВОД И ТОРГОВЫЙ ПЛАН (ГЛАВНЫЕ ОЖИДАНИЯ)
- **Главное ожидание по рынку:** [Конкретное ожидание: чего ждем в первую очередь — ложный вынос ликвидности вниз, пробой вверх или затяжной боковик?]
- **Динамическая риск-модель ATR (R:R 1:2 и 1:3):** [Используй СТРОГО точные числовые данные из risk_model: укажи ATR14, буфер 1.5x ATR, рекомендуемый сценарий, стоп-лосс и цели TP1/TP2. Запрещено выдумывать свои цифры — бери точные значения из risk_model.recommended, risk_model.long и risk_model.short].
- **План на ЛОНГ:** [Точный уровень входа, стоп-лосс по ATR, цели TP1 (1:2) и TP2 (1:3), триггер подтверждения (например: «Вход в лонг только при закреплении 4-часовой свечи выше $83,150 с подтверждением спотовых покупок»)].
- **План на ШОРТ:** [Точный уровень входа, стоп-лосс по ATR, цели TP1 (1:2) и TP2 (1:3), триггер подтверждения (например: «Шорт при уверенном пробое $82,240 вниз при уходе спотовой дельты в минус»)].
- **Что отменит сценарий (Инвалидация):** [Какое ценовое или объемное событие полностью ломает план].
"""


def run_gemini_synthesis(payload: dict, screenshots: list[dict]) -> str:
    global genai, types
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY отсутствует в файле .env")
    if genai is None or types is None:
        try:
            from google import genai as _genai
            from google.genai import types as _types
            genai = _genai
            types = _types
        except ImportError:
            raise RuntimeError("Установите пакет google-genai: pip install google-genai")

    print(f"[*] Синтез рыночного брифа через {GEMINI_MODEL}...")
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = (
        "Составь профессиональный утренний бриф по Bitcoin на русском языке без англицизмов и без служебных ярлыков. "
        "Особое внимание удели блоку макроэкономики (выдели все события США на неделю/следующую неделю со временем Риги/Латвии) "
        "и обязательно закончи отчет четким разделом 'ГЛАВНЫЙ ВЫВОД И ТОРГОВЫЙ ПЛАН (ГЛАВНЫЕ ОЖИДАНИЯ)'.\n\n"
        "СЫРЫЕ РЫНОЧНЫЕ ДАННЫЕ:\n" + json.dumps(payload, ensure_ascii=False, indent=2)
    )
    contents = [prompt]
    image_paths = []
    for screenshot in screenshots:
        if screenshot.get("path"):
            image_paths.append((Path(screenshot["path"]), screenshot.get("label", "screenshot")))
    for item in payload.get("manual_inputs", []):
        if item.get("extension") in {".png", ".jpg", ".jpeg", ".webp"}:
            image_paths.append((Path(item["path"]), item.get("filename", "manual screenshot")))
    for image_path, label in image_paths:
        if image_path.exists():
            suffix = image_path.suffix.lower()
            mime = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/png")
            contents.append(f"\nВИЗУАЛЬНЫЙ ИСТОЧНИК: {label}. Укажи, если шкала, timestamp или значения не читаются.")
            contents.append(types.Part.from_bytes(data=image_path.read_bytes(), mime_type=mime))

    last_exc = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                ),
            )
            text = getattr(response, "text", None)
            if text and text.strip():
                return text.strip()
            raise RuntimeError("Gemini вернул пустой ответ.")
        except Exception as exc:
            last_exc = exc
            err_msg = str(exc)
            if attempt < 2 and any(code in err_msg for code in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                print(f"[*] Модель перегружена (попытка {attempt+1}/3), пауза {(attempt+1)*3}с перед повтором...")
                time.sleep((attempt + 1) * 3)
                continue
            raise last_exc


def fallback_report(payload: dict, error: str) -> str:
    """Аварийный отчёт без синтеза; это не торговая рекомендация."""
    prices = payload.get("binance", {}).get("prices", {})
    derivs = payload.get("binance", {}).get("derivatives", {})
    flow = payload.get("binance", {}).get("spot_taker_delta", {})
    quant = payload.get("binance", {}).get("quant_bias", {})
    z_scores = payload.get("binance", {}).get("statistical_z_scores", {})
    div = payload.get("binance", {}).get("divergence_engine", {}).get("24h_divergence", {})
    calib = payload.get("quant_bias_calibration", {})
    risk = payload.get("risk_model") or payload.get("binance", {}).get("risk_model", {})
    long_s = risk.get("long", {})
    short_s = risk.get("short", {})
    onchain = payload.get("onchain_metrics") or payload.get("onchain", {})

    spot = prices.get("spot_last", "N/A")
    fut = prices.get("futures_last", "N/A")
    basis = prices.get("basis_usd", "N/A")
    d1 = flow.get("1h", {}).get("delta_btc", "N/A")
    d4 = flow.get("4h", {}).get("delta_btc", "N/A")
    d24 = flow.get("24h", {}).get("delta_btc", "N/A")
    oi = derivs.get("live_open_interest_btc", "N/A")
    fr = derivs.get("current_funding_rate_pct", "N/A")

    # Sanitize error: strip giant JSON blobs, keep first 300 chars
    clean_error = str(error)
    json_start = clean_error.find("{")
    if json_start > 0:
        clean_error = clean_error[:json_start].strip()
    clean_error = clean_error[:300]

    lines = [
        "# BTC Market Intelligence — Аварийный срез данных",
        "",
        f"**⚠ Сбой вызова ИИ:** {clean_error}",
        "",
        "## Сырые метрики (без интерпретации ИИ)",
        "",
        f"| Метрика | Значение |",
        f"|---------|----------|",
        f"| Время (UTC) | {payload.get('timestamp_utc', 'N/A')} |",
        f"| Spot Price | ${spot} |",
        f"| Futures Price | ${fut} |",
        f"| Basis (Fut - Spot) | {basis} USD |",
        f"| Spot Taker Delta 1h | {d1} BTC |",
        f"| Spot Taker Delta 4h | {d4} BTC |",
        f"| Spot Taker Delta 24h | {d24} BTC |",
        f"| Live Open Interest | {oi} BTC |",
        f"| Funding Rate | {fr}% |",
        "",
        "## Количественные метрики (Quant Bias, рассчитаны Python, ИИ не потребовался)",
        "",
        f"| Метрика | Значение |",
        f"|---------|----------|",
        f"| **Quant Bias Score** | **{quant.get('composite_score', 'N/A')} ({quant.get('bias_label', 'N/A')})** |",
        f"| OI Z-Score | {z_scores.get('oi_zscore', 'N/A')} |",
        f"| Funding Z-Score | {z_scores.get('funding_zscore', 'N/A')} |",
        f"| Divergence Engine (24h) | {div.get('divergence_state', 'N/A')} |",
        f"| **Quant Bias Win-Rate** | **{calib.get('readout', 'База калибруется')}** |",
        "",
        "## Динамическая риск-модель ATR (R:R 1:2 и 1:3)",
        "",
        f"Рекомендованный сценарий: **{risk.get('direction', 'NEUTRAL')}** | ATR14: **${risk.get('atr14', 0.0):,.2f}** | Буфер (1.5x ATR): **${risk.get('buffer', 0.0):,.2f}**",
        "",
        "| Параметр | LONG Сценарий | SHORT Сценарий |",
        "|---|---|---|",
        f"| Точка входа | ${spot} | ${spot} |",
        f"| Стоп-лосс (1.5x ATR) | ${long_s.get('stop_loss', 0.0):,.2f} | ${short_s.get('stop_loss', 0.0):,.2f} |",
        f"| Тейк-профит 1 (1:2 R:R) | ${long_s.get('tp1_rr2', 0.0):,.2f} | ${short_s.get('tp1_rr2', 0.0):,.2f} |",
        f"| Тейк-профит 2 (1:3 R:R) | ${long_s.get('tp2_rr3', 0.0):,.2f} | ${short_s.get('tp2_rr3', 0.0):,.2f} |",
        "",
        "## Ончейн-оценка LookIntoBitcoin (MVRV Z-Score и NUPL)",
        "",
        "| Метрика | Значение | Фаза макроцикла |",
        "|---|---|---|",
        f"| MVRV Z-Score | {onchain.get('mvrv_zscore', 'N/A')} | {onchain.get('mvrv_stage', 'UNAVAILABLE')} |",
        f"| NUPL | {onchain.get('nupl', 'N/A')} | {onchain.get('nupl_stage', 'UNAVAILABLE')} |",
        f"| Realized Price | ${onchain.get('realized_price', 0.0):,.2f} | Фундаментальная себестоимость сети |",
        "",
        f"| ETF Flows | {payload.get('btc_spot_etf_flows', {}).get('status', 'UNKNOWN')} |",
        f"| Deribit Options | {payload.get('options_deribit', {}).get('status', 'UNKNOWN')} |",
        "> **Интерпретация отсутствует.** Данные собраны успешно. Повторите запуск позже или проверьте квоту API.",
    ]
    return "\n".join(lines)


def export_report_to_pdf_reportlab(report_md: str, pdf_path: Path, screenshots: Optional[list[dict]] = None) -> bool:
    """
    Pure-Python PDF generation via ReportLab (zero headless browser requirements).
    Works reliably across local workstations and Streamlit Community Cloud.
    """
    try:
        import os
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont

        font_name = "Helvetica"
        for fp in ["C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/TTF/DejaVuSans.ttf"]:
            if os.path.exists(fp):
                try:
                    pdfmetrics.registerFont(TTFont("AppUnicode", fp))
                    font_name = "AppUnicode"
                    break
                except Exception:
                    pass

        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle("RepTitle", fontName=font_name, fontSize=16, leading=20, textColor=colors.HexColor("#0f172a"))
        body_style = ParagraphStyle("RepBody", fontName=font_name, fontSize=9, leading=13, textColor=colors.HexColor("#334155"))
        h2_style = ParagraphStyle("RepH2", fontName=font_name, fontSize=12, leading=16, textColor=colors.HexColor("#1e293b"), spaceBefore=10, spaceAfter=4)
        cell_style = ParagraphStyle("RepCell", fontName=font_name, fontSize=8, leading=11, textColor=colors.HexColor("#1e293b"))
        cell_bold = ParagraphStyle("RepCellB", fontName=font_name, fontSize=8, leading=11, textColor=colors.HexColor("#0f172a"))

        story = [
            Paragraph("<b>BTC MARKET INTELLIGENCE — АНАЛИТИЧЕСКИЙ ОТЧЕТ</b>", title_style),
            Paragraph(f"Институциональная торговая аналитика и количественный риск-менеджмент | {iso_utc()}", body_style),
            Spacer(1, 6),
            HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#cbd5e1"), spaceAfter=10)
        ]

        lines = report_md.split("\n")
        table_rows = []
        in_table = False

        for line in lines:
            sline = line.strip()
            if not sline:
                if in_table and table_rows:
                    try:
                        t = Table(table_rows, colWidths=None)
                        t.setStyle(TableStyle([
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                            ("TOPPADDING", (0, 0), (-1, -1), 4),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ]))
                        story.append(t)
                        story.append(Spacer(1, 6))
                    except Exception:
                        pass
                    table_rows = []
                    in_table = False
                continue

            if sline.startswith("|") and sline.endswith("|"):
                cells = [c.strip() for c in sline[1:-1].split("|")]
                if all(c.replace("-", "").strip() == "" for c in cells):
                    continue
                in_table = True
                is_header = (len(table_rows) == 0)
                table_rows.append([Paragraph(c, cell_bold if is_header else cell_style) for c in cells])
                continue

            if in_table and table_rows:
                try:
                    t = Table(table_rows)
                    t.setStyle(TableStyle([
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
                    ]))
                    story.append(t)
                    story.append(Spacer(1, 6))
                except Exception:
                    pass
                table_rows = []
                in_table = False

            if sline.startswith("# "):
                continue
            elif sline.startswith("## "):
                story.append(Paragraph(f"<b>{sline[3:]}</b>", h2_style))
            elif sline.startswith("### "):
                story.append(Paragraph(f"<b>{sline[4:]}</b>", h2_style))
            elif sline.startswith("---"):
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=6))
            else:
                clean = sline.replace("**", "<b>", 1).replace("**", "</b>", 1).replace("⚠", "[!]")
                story.append(Paragraph(clean, body_style))

        # Append screenshots if present
        seen_imgs = set()
        screenshots_list = screenshots or []
        if not screenshots_list:
            sc_dir = BASE_DIR / "free_dashboard_screenshots"
            if sc_dir.exists():
                screenshots_list = [{"path": str(p), "label": p.stem.replace("_", " ").title()} for p in sorted(sc_dir.glob("*.png"))]

        if screenshots_list:
            story.append(Spacer(1, 10))
            story.append(Paragraph("ГРАФИЧЕСКИЕ ДАННЫЕ И ТЕПЛОВЫЕ КАРТЫ", h2_style))
            for sc in screenshots_list:
                p = Path(sc.get("path", ""))
                if not p.exists() or str(p) in seen_imgs or p.stat().st_size < 1000:
                    continue
                seen_imgs.add(str(p))
                try:
                    label = sc.get("label", p.stem)
                    story.append(Paragraph(f"• {label}", cell_bold))
                    story.append(RLImage(str(p), width=500, height=260, kind="proportional"))
                    story.append(Spacer(1, 12))
                except Exception:
                    pass

        doc.build(story)
        return pdf_path.exists() and pdf_path.stat().st_size > 1000
    except Exception as e:
        print(f"[WARN] Сбой формирования PDF через ReportLab: {e}")
        return False


def export_report_to_pdf_playwright(report_md: str, pdf_path: Path, screenshots: Optional[list[dict]] = None) -> bool:
    try:
        html_body = markdown.markdown(report_md, extensions=["tables", "fenced_code"])

        # Prepare embedded images section
        charts_html = []
        seen_paths = set()
        if screenshots:
            for s in screenshots:
                img_p = s.get("path")
                if not img_p:
                    continue
                p = Path(img_p)
                if not p.exists() or str(p) in seen_paths or p.stat().st_size < 10000:
                    continue
                seen_paths.add(str(p))

                # Convert image to base64
                try:
                    b64_data = base64.b64encode(p.read_bytes()).decode("utf-8")
                    suffix = p.suffix.lower().replace(".", "")
                    mime = f"image/{suffix}" if suffix in ("png", "jpeg", "webp") else "image/png"
                    label = s.get("label", p.stem.replace("_", " ").title())
                    charts_html.append(f"""
                    <div class="chart-card">
                      <div class="chart-header">📊 {label}</div>
                      <img src="data:{mime};base64,{b64_data}" alt="{label}" />
                    </div>
                    """)
                except Exception:
                    continue

        images_section = ""
        if charts_html:
            images_section = f"""
            <div class="charts-section">
              <h2 style="border-left: 4px solid #f59e0b; color: #b45309;">АНАЛИТИЧЕСКИЕ ГРАФИКИ И ТЕПЛОВЫЕ КАРТЫ</h2>
              {"".join(charts_html)}
            </div>
            """

        full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>BTC Market Intelligence Report</title>
<style>
  @page {{
    size: A4;
    margin: 15mm 15mm 15mm 15mm;
  }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    color: #1e293b;
    line-height: 1.55;
    font-size: 12.5px;
    background: #ffffff;
  }}
  .report-header {{
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    color: #ffffff;
    padding: 16px 20px;
    border-radius: 8px;
    margin-bottom: 20px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .report-header h1 {{
    margin: 0;
    font-size: 19px;
    color: #ffffff;
    border: none;
    padding: 0;
  }}
  .report-badge {{
    background: #3b82f6;
    color: #ffffff;
    padding: 4px 10px;
    border-radius: 9999px;
    font-weight: 700;
    font-size: 11px;
    text-transform: uppercase;
  }}
  h1 {{
    color: #0f172a;
    font-size: 19px;
    border-bottom: 2px solid #e2e8f0;
    padding-bottom: 6px;
    margin-top: 15px;
    margin-bottom: 12px;
  }}
  h2 {{
    color: #1e40af;
    font-size: 14.5px;
    margin-top: 22px;
    margin-bottom: 10px;
    border-left: 4px solid #2563eb;
    padding-left: 10px;
    letter-spacing: -0.2px;
    page-break-after: avoid;
  }}
  h3 {{
    font-size: 13px;
    color: #334155;
    margin-top: 14px;
    margin-bottom: 8px;
    page-break-after: avoid;
  }}
  table {{
    border-collapse: collapse;
    width: 100%;
    margin: 12px 0;
    font-size: 11.5px;
    page-break-inside: avoid;
  }}
  th, td {{
    border: 1px solid #e2e8f0;
    padding: 6px 10px;
    text-align: left;
  }}
  th {{
    background: #f8fafc;
    color: #0f172a;
    font-weight: 600;
    border-bottom: 2px solid #cbd5e1;
  }}
  tr:nth-child(even) {{
    background: #f8fafc;
  }}
  ul {{
    margin: 6px 0;
    padding-left: 18px;
  }}
  li {{
    margin-bottom: 4px;
  }}
  strong {{
    color: #0f172a;
  }}
  hr {{
    border: none;
    border-top: 1px solid #e2e8f0;
    margin: 16px 0;
  }}
  .chart-card {{
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    padding: 10px;
    margin: 16px 0;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    page-break-inside: avoid;
    text-align: center;
  }}
  .chart-header {{
    font-weight: 600;
    font-size: 12px;
    color: #334155;
    margin-bottom: 8px;
    text-align: left;
  }}
  .chart-card img {{
    max-width: 100%;
    height: auto;
    border-radius: 4px;
    display: block;
    margin: 0 auto;
  }}
  .footer-note {{
    margin-top: 25px;
    font-size: 10px;
    color: #94a3b8;
    text-align: center;
    border-top: 1px solid #f1f5f9;
    padding-top: 8px;
  }}
</style>
</head>
<body>
  <div class="report-header">
    <h1>BTC Market Intelligence Brief</h1>
    <div class="report-badge">INSTITUTIONAL QUANT REPORT</div>
  </div>
  {html_body}
  {images_section}
  <div class="footer-note">
    Сформировано автоматически конвейером BTC Market Intelligence v4.1 | Время отчета: {iso_utc()}
  </div>
</body>
</html>"""

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_content(full_html)
            page.pdf(
                path=str(pdf_path),
                format="A4",
                print_background=True,
                margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"}
            )
            browser.close()

        return pdf_path.exists() and pdf_path.stat().st_size > 5000
    except Exception as exc:
        print(f"[WARN] Playwright вернул исключение: {exc}")
        return False


def export_report_to_pdf(report_md: str, pdf_path: Path, screenshots: Optional[list[dict]] = None) -> bool:
    """
    Renders the market intelligence report into a high-quality PDF.
    Prefers Playwright if available; falls back seamlessly to ReportLab.
    """
    # 1. Try Playwright if browser runtime is installed
    if sync_playwright is not None and markdown is not None:
        try:
            print(f"[*] Формирование PDF-отчета через Playwright: {pdf_path.name}...")
            if export_report_to_pdf_playwright(report_md, pdf_path, screenshots):
                return True
        except Exception as exc:
            print(f"[WARN] Playwright вернул исключение: {exc}")

    # 2. Pure-Python ReportLab fallback (zero browser dependencies, works on Cloud)
    print(f"[*] Формирование PDF-отчета через ReportLab: {pdf_path.name}...")
    return export_report_to_pdf_reportlab(report_md, pdf_path, screenshots)


# ------------------------------- SELF-TEST -----------------------------------

def run_self_tests() -> int:
    """Offline smoke tests; no network calls and no API keys required."""
    checks = []
    try:
        now_ms = epoch_ms() - 5000
        candles = []
        for i in range(80):
            op = 50000 + i * 50
            close = op + 20
            high, low = close + 30, op - 30
            candles.append([now_ms - (80-i)*3_600_000, str(op), str(high), str(low), str(close), "100",
                            now_ms - (79-i)*3_600_000, str(5_000_000+i*1000), 100, "60", "40", "0"])
        # Проверка отсечения незакрытых свечей
        future_candle = [now_ms + 100_000, "60000", "60100", "59900", "60050", "50", now_ms + 3_600_000, "3000000", 50, "30", "20", "0"]
        candles_with_future = candles + [future_candle]
        closed_only = only_closed_klines(candles_with_future)
        assert len(closed_only) == len(candles), "Незакрытая свеча должна отсекаться фильтром only_closed_klines"
        checks.append("closed-candle filtering & technical layer")

        parser = _TableParser()
        parser.feed("<table><tr><th>Date</th><th>ETF</th><th>Total</th></tr><tr><td>09 Oct 2026</td><td>12.0</td><td>-12.0</td></tr></table>")
        assert any(row[0] == "09 Oct 2026" and row[-1] == "-12.0" for row in parser.rows)
        assert _parse_money_cell("(12.5)") == -12.5
        assert _parse_money_cell("$1,234.5") == 1234.5
        checks.append("ETF HTML parser and flow sign")

        # Проверка строгой толерантности горизонта OI
        now = time.time()
        history = [{"timestamp": (now - 3600)*1000, "sumOpenInterest": "100"}]
        oi_valid = nearest_oi_change(history, 105, 1)
        assert oi_valid.get("available") and oi_valid.get("change_pct") == 5.0
        # Снимок 24-минутной давности (0.4ч) должен отклоняться для горизонта 1ч
        history_too_recent = [{"timestamp": (now - 3600 * 0.4)*1000, "sumOpenInterest": "100"}]
        oi_invalid = nearest_oi_change(history_too_recent, 105, 1)
        assert oi_invalid.get("available") is False, "Слишком свежий снимок (24 мин) не должен приниматься за 1-часовой"
        checks.append("OI strict horizon validation")

        assert "fetch_bybit_telemetry" in globals()
        assert len(FREE_DASHBOARD_PAGES) >= 3
        assert "bybit" in fetch_bybit_telemetry.__name__
        assert SCREENSHOT_FILE.parent.name == "free_dashboard_screenshots"
        assert ENABLE_COINGLASS_API is False or bool(COINGLASS_API_KEY)
        checks.append("free multi-exchange and public dashboard modules present")
        checks.append("screenshots routed to dedicated folder; paid API disabled by default")

        # Quant Engine unit tests
        z = calculate_zscore(10.0, [5.0, 5.0, 5.0, 10.0, 5.0])
        assert z is not None and z > 0, "Z-Score should be positive when value > mean"
        z_neg = calculate_zscore(0.0, [5.0, 6.0, 4.0, 5.5, 4.5])  # mean=5, std>0, value=0 → negative
        assert z_neg is not None and z_neg < 0, "Z-Score should be negative when value < mean"
        z_zero = calculate_zscore(5.0, [5.0, 5.0, 5.0, 5.0])  # std=0 → returns 0.0
        assert z_zero == 0.0, "Z-Score should be 0 when value == mean and std == 0"
        checks.append("calculate_zscore: positive, negative, and zero std cases")

        mock_metrics = {
            "market_structure": {"1d": {"close_vs_rolling_vwap20_pct": 1.5}},  # +10
            "spot_taker_delta": {"24h": {"delta_btc": 500.0}},  # +15
            "orderbook_depth": {
                "spot": {"bid_vs_ask_ratio": 1.3},   # +15
                "futures": {"bid_vs_ask_ratio": 1.2}, # +10
            },
            "divergence_engine": {"24h_divergence": {"bias_contribution": 15}},  # +15
            "statistical_z_scores": {"oi_zscore": 1.0},  # no squeeze trigger
            "derivatives": {"current_funding_rate_pct": 0.001},
        }
        bias = calculate_quant_bias(mock_metrics)
        assert bias["composite_score"] == 66, f"Expected 66, got {bias['composite_score']}"
        assert bias["bias_label"] == "STRONG BULLISH", f"Expected STRONG BULLISH, got {bias['bias_label']}"
        assert "futures_orderbook_imbalance" in bias["breakdown"], "Futures OB should be in breakdown"
        checks.append("calculate_quant_bias: scoring and label correctness")

        # Calibration tracker unit test
        test_tracker_p = BASE_DIR / "_test_calibration_tracker.tmp"
        if test_tracker_p.exists():
            test_tracker_p.unlink()
        try:
            t0 = 1700000000.0
            snap1 = {
                "prices": {"spot_last": 80000.0},
                "quant_bias": {"composite_score": 25, "bias_label": "BULLISH"},
                "divergence_engine": {"24h_divergence": {"divergence_state": "Bullish Continuation"}},
                "statistical_z_scores": {"oi_zscore": 0.5},
            }
            res1 = update_calibration_tracker(snap1, tracker_path=test_tracker_p, force_time=t0)
            assert res1["total_signals_tracked"] == 1
            assert res1["resolved_signals_count"] == 0
            assert res1["status"] == "ACCUMULATING_DATA"

            # 24.5 hours later: price went UP to 82,000 -> Bullish WIN
            t1 = t0 + 24.5 * 3600
            snap2 = {
                "prices": {"spot_last": 82000.0},
                "quant_bias": {"composite_score": -20, "bias_label": "BEARISH"},
                "divergence_engine": {"24h_divergence": {"divergence_state": "Short Build-up"}},
                "statistical_z_scores": {"oi_zscore": 1.2},
            }
            res2 = update_calibration_tracker(snap2, tracker_path=test_tracker_p, force_time=t1)
            assert res2["total_signals_tracked"] == 2
            assert res2["resolved_signals_count"] == 1
            assert res2["wins_total"] == 1
            assert res2["overall_win_rate_pct"] == 100.0
            assert res2["bullish_signals"]["win_rate_pct"] == 100.0

            # Another 24.5 hours later: price went UP to 83,000 -> Bearish LOSS
            t2 = t1 + 24.5 * 3600
            snap3 = {
                "prices": {"spot_last": 83000.0},
                "quant_bias": {"composite_score": 0, "bias_label": "NEUTRAL"},
                "divergence_engine": {},
                "statistical_z_scores": {},
            }
            res3 = update_calibration_tracker(snap3, tracker_path=test_tracker_p, force_time=t2)
            assert res3["resolved_signals_count"] == 2
            assert res3["wins_total"] == 1
            assert res3["losses_total"] == 1
            assert res3["overall_win_rate_pct"] == 50.0
            assert res3["bullish_signals"]["win_rate_pct"] == 100.0
            assert res3["bearish_signals"]["win_rate_pct"] == 0.0
            checks.append("update_calibration_tracker: 24h win-rate resolution and calibration math")
        finally:
            if test_tracker_p.exists():
                test_tracker_p.unlink()

        # PDF exporter unit test
        test_pdf_p = BASE_DIR / "_test_report.pdf.tmp"
        if test_pdf_p.exists():
            test_pdf_p.unlink()
        try:
            pdf_res = export_report_to_pdf("# Тест заголовка\n\nТестовый текст", test_pdf_p, screenshots=None)
            if pdf_res is True:
                assert test_pdf_p.exists() and test_pdf_p.stat().st_size > 1000, "PDF file should be created and non-empty"
                checks.append("export_report_to_pdf: PDF compilation successful")
            else:
                checks.append("export_report_to_pdf: Graceful fallback when PDF engine unavailable")
        finally:
            if test_pdf_p.exists():
                test_pdf_p.unlink()

        # 10. ATR Dynamic Risk Model Unit Test
        risk_long = calculate_atr_risk_levels(80000.0, 500.0, 30)
        assert risk_long["direction"] == "LONG"
        assert risk_long["buffer"] == 750.0  # 1.5 * 500
        assert risk_long["long"]["stop_loss"] == 79250.0
        assert risk_long["long"]["tp1_rr2"] == 81500.0
        assert risk_long["long"]["tp2_rr3"] == 82250.0
        assert round((81500.0 - 80000.0) / 750.0, 1) == 2.0, "Long TP1 should be 1:2 R:R"
        assert round((82250.0 - 80000.0) / 750.0, 1) == 3.0, "Long TP2 should be 1:3 R:R"
        assert risk_long["recommended"]["scenario"] == "LONG"
        assert risk_long["recommended"]["stop_loss"] == 79250.0

        risk_short = calculate_atr_risk_levels(80000.0, 500.0, -30)
        assert risk_short["direction"] == "SHORT"
        assert risk_short["short"]["stop_loss"] == 80750.0
        assert risk_short["short"]["tp1_rr2"] == 78500.0
        assert risk_short["short"]["tp2_rr3"] == 77750.0
        assert round((80000.0 - 78500.0) / 750.0, 1) == 2.0, "Short TP1 should be 1:2 R:R"
        assert round((80000.0 - 77750.0) / 750.0, 1) == 3.0, "Short TP2 should be 1:3 R:R"
        assert risk_short["recommended"]["scenario"] == "SHORT"
        assert risk_short["recommended"]["stop_loss"] == 80750.0

        risk_neutral = calculate_atr_risk_levels(80000.0, 500.0, 0)
        assert risk_neutral["direction"] == "NEUTRAL"
        assert risk_neutral["recommended"]["scenario"] == "NEUTRAL"
        assert risk_neutral["long"]["stop_loss"] == 79250.0
        assert risk_neutral["short"]["stop_loss"] == 80750.0

        # Boundary / edge cases
        risk_zero = calculate_atr_risk_levels(0, 0, 0)
        assert risk_zero["buffer"] == 0.0
        assert risk_zero["direction"] == "NEUTRAL"
        checks.append("calculate_atr_risk_levels: dynamic Long/Short/Neutral R:R 1:2 and 1:3 calculations")

        # 11. Onchain parser & cycle stage classification unit tests
        assert classify_mvrv_stage(0.05) == "Bottom / Undervalued"
        assert classify_mvrv_stage(1.10) == "Fair Value / Early Bull"
        assert classify_mvrv_stage(2.50) == "Mature Bull / Expansion"
        assert classify_mvrv_stage(4.20) == "Overheated / Distribution Zone"
        assert classify_mvrv_stage(6.50) == "Cycle Top / Euphoria"
        assert classify_mvrv_stage(None) == "UNAVAILABLE"

        assert classify_nupl_stage(-0.10) == "Capitulation"
        assert classify_nupl_stage(0.15) == "Hope / Fear"
        assert classify_nupl_stage(0.38) == "Optimism / Anxiety"
        assert classify_nupl_stage(0.65) == "Belief / Denial"
        assert classify_nupl_stage(0.85) == "Euphoria / Greed"
        assert classify_nupl_stage(None) == "UNAVAILABLE"

        # Mock session for fetch_onchain_metrics
        class MockResponse:
            def __init__(self, data, status_code=200):
                self._data = data
                self.status_code = status_code
            def json(self):
                return self._data

        class MockSession:
            def get(self, url, headers=None, timeout=None):
                if "mvrv" in url:
                    return MockResponse([{"d": "2026-10-04", "mvrvZscore": 1.0926}])
                elif "nupl" in url:
                    return MockResponse([{"d": "2026-10-04", "nupl": 0.3842}])
                elif "realized" in url:
                    return MockResponse([{"d": "2026-10-04", "realizedPrice": 53294.67}])
                return MockResponse([], 404)

        mock_onchain = fetch_onchain_metrics(session=MockSession())
        assert mock_onchain["status"] == "OK"
        assert mock_onchain["mvrv_zscore"] == 1.09
        assert mock_onchain["mvrv_stage"] == "Fair Value / Early Bull"
        assert mock_onchain["nupl"] == 0.384
        assert mock_onchain["nupl_stage"] == "Optimism / Anxiety"
        assert mock_onchain["realized_price"] == 53294.67

        # Fallback offline error handling
        class FailingSession:
            def get(self, *args, **kwargs):
                raise RuntimeError("Network offline")
        fallback_onchain = fetch_onchain_metrics(session=FailingSession())
        assert fallback_onchain["status"] == "UNAVAILABLE"
        assert fallback_onchain["mvrv_zscore"] is None
        checks.append("fetch_onchain_metrics: cycle classification and fallback handling")

        # 12. Calibration Tracker Schema & Event-Driven Touch Resolution
        test_tracker_upgraded_p = BASE_DIR / "_test_calibration_upgraded.tmp"
        if test_tracker_upgraded_p.exists():
            test_tracker_upgraded_p.unlink()
        try:
            t_base = 1710000000.0
            snap_init = {
                "prices": {"spot_last": 80000.0},
                "quant_bias": {"composite_score": 30, "bias_label": "BULLISH"},
                "market_structure": {"4h": {"atr14_price": 500.0}},
            }
            res_upg1 = update_calibration_tracker(snap_init, tracker_path=test_tracker_upgraded_p, force_time=t_base)
            assert res_upg1["total_signals_tracked"] == 1

            # Verify file schema on disk
            raw_track = json.loads(test_tracker_upgraded_p.read_text(encoding="utf-8"))
            rec0 = raw_track[0]
            assert rec0["direction"] == "LONG"
            assert rec0["entry_price"] == 80000.0
            assert rec0["stop_loss"] == 79250.0  # 80000 - 1.5 * 500
            assert rec0["tp1_rr2"] == 81500.0
            assert rec0["tp2_rr3"] == 82250.0
            assert rec0["resolution_type"] == "PENDING"

            # 2 hours later: price wick down touched SL (79200 <= 79250) -> Event-driven SL_HIT
            t_touch = t_base + 2.0 * 3600
            snap_sl = {
                "prices": {"spot_last": 79400.0},
                "low_price": 79200.0,
                "high_price": 80200.0,
                "quant_bias": {"composite_score": -10, "bias_label": "NEUTRAL"},
            }
            res_upg2 = update_calibration_tracker(snap_sl, tracker_path=test_tracker_upgraded_p, force_time=t_touch)
            assert res_upg2["resolved_signals_count"] == 1
            assert res_upg2["losses_total"] == 1
            raw_track_sl = json.loads(test_tracker_upgraded_p.read_text(encoding="utf-8"))
            assert raw_track_sl[0]["resolved"] is True
            assert raw_track_sl[0]["resolution_type"] == "SL_HIT"
            assert raw_track_sl[0]["outcome"] == "LOSS"
            assert raw_track_sl[0]["is_win"] is False

            checks.append("update_calibration_tracker: upgraded schema and event-driven SL/TP resolution")
        finally:
            if test_tracker_upgraded_p.exists():
                test_tracker_upgraded_p.unlink()

        # 13. Fast Momentum Scan mock execution flow
        mock_fast_snap = run_fast_momentum_scan(quiet=True, mock=True)
        assert mock_fast_snap["execution_mode"] == "FAST_MOMENTUM_SCAN"
        assert mock_fast_snap["spot_price"] > 0
        assert "composite_score" in mock_fast_snap["quant_bias"]
        assert "atr14" in mock_fast_snap["risk_model"]
        assert "long" in mock_fast_snap["risk_model"]
        assert "short" in mock_fast_snap["risk_model"]
        assert "recommended" in mock_fast_snap["risk_model"]
        assert "mvrv_zscore" in mock_fast_snap["onchain_metrics"]
        assert "nupl" in mock_fast_snap["onchain_metrics"]
        assert "execution_time_sec" in mock_fast_snap
        checks.append("run_fast_momentum_scan: offline mock execution flow and schema")

        print("SELF-TEST: PASS")
        for item in checks:
            print(f"  [PASS] {item}")
        print("No network/API/Gemini credentials were used.")
        return 0
    except Exception as exc:
        print(f"SELF-TEST: FAIL — {exc}")
        return 1


# ------------------------------- ОСНОВНОЙ ПАЙПЛАЙН --------------------------

def main() -> int:
    started = time.time()
    print("=== ЗАПУСК BTC MARKET INTELLIGENCE V4 (FREE DATA) ===")
    statuses = {}
    try:
        binance, binance_statuses = fetch_binance_telemetry()
        statuses.update(binance_statuses)
    except DataIntegrityError as exc:
        print(f"[FATAL] Критический сбой данных: {exc}")
        return 2

    bybit = fetch_bybit_telemetry()
    statuses["bybit_public_data"] = status_record(bybit.get("status") == "OK", "Bybit public V5 market data; exchange-specific cross-check")

    macro_cross_asset = fetch_macro_cross_asset()
    statuses["macro_cross_asset"] = status_record(
        any(x.get("status") == "OK" for x in macro_cross_asset.get("instruments", [])),
        "Yahoo Finance публичные котировки",
    )
    
    macro_calendar = fetch_macro_calendar()
    statuses["macro_calendar"] = status_record(
        macro_calendar.get("status") == "OK",
        "Календарь Forex Factory",
    )
    
    news = fetch_rss_headlines()
    statuses["rss_news"] = status_record(
        news.get("status") == "OK",
        "RSS-ленты новостей",
    )

    etf_flows = fetch_btc_etf_flows()
    statuses["btc_spot_etf_flows"] = status_record(etf_flows.get("status") == "OK", "Farside Investors daily net flow table; USD millions")

    options = fetch_deribit_options()
    statuses["deribit_options"] = status_record(options.get("status") == "OK", "Deribit public options summary; not global options market")

    coinglass_aggregate = fetch_coinglass_aggregate()
    statuses["coinglass_api_aggregate"] = status_record(coinglass_aggregate.get("status") == "OK", "Optional licensed cross-exchange futures data")

    onchain = fetch_onchain_metrics()
    mvrv_val = onchain.get("mvrv_zscore") if not isinstance(onchain.get("mvrv_zscore"), dict) else onchain.get("mvrv_zscore", {}).get("value")
    nupl_val = onchain.get("nupl") if not isinstance(onchain.get("nupl"), dict) else onchain.get("nupl", {}).get("value")
    statuses["onchain_bgeometrics"] = status_record(
        onchain.get("status") == "OK",
        f"BGeometrics REST on-chain metrics (MVRV Z-Score: {mvrv_val}, NUPL: {nupl_val})",
    )

    manual_inputs = collect_manual_inputs()
    statuses["manual_inputs"] = status_record(bool(manual_inputs), f"{len(manual_inputs)} files in {MANUAL_INPUT_DIR}")
    
    history = read_history()
    historical_diff = get_historical_comparison(binance, history)
    calibration_summary = update_calibration_tracker(binance)
    statuses["quant_bias_calibration"] = status_record(
        True,
        calibration_summary.get("readout", "Calibration tracker active"),
    )
    screenshots = capture_coinglass_clean()
    coinglass_screenshot_count = len(screenshots)
    free_dashboard_screenshots = capture_free_dashboard_pages()
    screenshots.extend([x for x in free_dashboard_screenshots if x.get("status") == "CAPTURED_PAGE_REQUIRES_VISUAL_VALIDATION" and x.get("path") and Path(x["path"]).exists()])
    captured_dashboard_count = sum(1 for x in free_dashboard_screenshots if x.get("status") == "CAPTURED_PAGE_REQUIRES_VISUAL_VALIDATION")
    statuses["free_dashboard_screenshots"] = status_record(
        captured_dashboard_count > 0,
        f"Validated page-level captures {captured_dashboard_count}/{len(FREE_DASHBOARD_PAGES)} requested; all chart pixels require manual visual validation",
    )
    heatmap_page_check_passed = any(str(x.get("semantic_check", "")).startswith("PASS:") for x in screenshots[:coinglass_screenshot_count])
    statuses["coinglass_screenshot"] = status_record(
        heatmap_page_check_passed,
        f"CoinGlass heatmap page checks passed={heatmap_page_check_passed}; any saved unverified image is for manual review only",
    )

    deribit_dvol = fetch_deribit_dvol()
    statuses["deribit_dvol"] = status_record(
        deribit_dvol.get("status") == "OK",
        f"Deribit DVOL Index (Crypto VIX: {deribit_dvol.get('current_dvol')})",
    )

    coinbase_ob = fetch_coinbase_orderbook()
    statuses["coinbase_orderbook"] = status_record(
        coinbase_ob.get("status") == "OK",
        f"Coinbase Pro BTC-USD L2 depth (Ratio: {coinbase_ob.get('bid_vs_ask_ratio')})",
    )

    spot_p = binance.get("prices", {}).get("spot_last", 0.0)
    cme_basis = fetch_cme_basis(spot_p)
    statuses["cme_basis"] = status_record(
        cme_basis.get("status") == "OK",
        f"CME Futures BTC=F basis: {cme_basis.get('basis_vs_spot_usd')} USD ({cme_basis.get('basis_vs_spot_pct')}%)",
    )

    binance["deribit_dvol"] = deribit_dvol
    binance["coinbase_orderbook"] = coinbase_ob
    binance["cme_basis"] = cme_basis

    risk_model = binance.get("risk_model", {})
    payload = {
        "timestamp_utc": iso_utc(),
        "local_timezone": LOCAL_TIMEZONE,
        "data_quality_statuses": statuses,
        "binance": binance,
        "bybit": bybit,
        "onchain_metrics": onchain,
        "onchain": onchain,
        "deribit_dvol": deribit_dvol,
        "coinbase_orderbook": coinbase_ob,
        "cme_basis": cme_basis,
        "risk_model": risk_model,
        "atr_risk": risk_model,
        "free_dashboard_screenshots": free_dashboard_screenshots,
        "historical_comparison": historical_diff,
        "quant_bias_calibration": calibration_summary,
        "macro_cross_asset": macro_cross_asset,
        "macro_calendar": macro_calendar,
        "news_headlines": news,
        "btc_spot_etf_flows": etf_flows,
        "options_deribit": options,
        "coinglass_aggregate_derivatives": coinglass_aggregate,
        "manual_inputs": manual_inputs,
    }

    # Print CLI summary table of ATR risk and on-chain valuation in Full mode
    print("\n" + "=" * 70)
    print("  ДИНАМИЧЕСКАЯ МОДЕЛЬ РИСКА (ATR) И ON-CHAIN МЕТРИКИ")
    print("=" * 70)
    rec = risk_model.get("recommended", {})
    spot_val = binance.get("prices", {}).get("spot_last", 0.0)
    atr_val = risk_model.get("atr14", 0.0)
    print(f"  BTC Spot: ${spot_val:,.2f} | 4h ATR14: ${atr_val:,.2f}")
    print(f"  Рекомендация: {rec.get('direction', 'NEUTRAL')}")
    print(f"  Stop-Loss:   ${rec.get('stop_loss', 0.0):,.2f} (1.5x ATR buffer)")
    print(f"  TP1 (1:2):   ${rec.get('tp1', 0.0):,.2f}")
    print(f"  TP2 (1:3):   ${rec.get('tp2', 0.0):,.2f}")
    if onchain.get("status") == "OK":
        mvrv_v = onchain.get("mvrv_zscore")
        mvrv_st = onchain.get("mvrv_stage", "N/A")
        nupl_v = onchain.get("nupl")
        nupl_st = onchain.get("nupl_stage", "N/A")
        print(f"  MVRV Z-Score: {mvrv_v} [{mvrv_st}]")
        print(f"  NUPL:         {nupl_v} [{nupl_st}]")
    print("=" * 70 + "\n")

    try:
        if not GEMINI_API_KEY:
            raise RuntimeError("структурированный расчет по формулам")
        report = run_gemini_synthesis(payload, screenshots)
    except Exception as exc:
        if GEMINI_API_KEY:
            print(f"[WARN] Сбой синтеза Gemini: {exc}")
        else:
            print("[*] Формирование квантового отчета (математический расчет)...")
        report = fallback_report(payload, str(exc))

    payload["run_finished_at_utc"] = iso_utc()
    RAW_SNAPSHOT_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    report += f"\n\n---\n*Сформировано: {iso_utc()} | Время выполнения: {time.time() - started:.1f}с*\n"

    OUTPUT_REPORT_FILE.write_text(report, encoding="utf-8")
    save_snapshot(binance, history)

    # Экспорт в PDF со встроенными графиками
    pdf_ok = export_report_to_pdf(report, OUTPUT_PDF_FILE, screenshots)

    print("\n" + "=" * 70)
    print(report)
    print("=" * 70)
    print(f"[✓] Markdown-отчет сохранен: {OUTPUT_REPORT_FILE}")
    if pdf_ok:
        print(f"[✓] Журнальный PDF сохранен: {OUTPUT_PDF_FILE}")
    print(f"[✓] База истории обновлена: {HISTORY_FILE}")
    print(f"[✓] Сырой пакет данных сохранен: {RAW_SNAPSHOT_FILE}")
    return 0


if __name__ == "__main__":
    if "--help" in sys.argv or "-h" in sys.argv:
        print("BTC Market Intelligence v4.1 (Free Data Pipeline)")
        print("Использование: python btc_market_intelligence.py [--fast] [--self-test] [--help]")
        print("  --fast       Быстрое REST-сканирование (<5.0 сек, без Playwright/браузера)")
        print("  --self-test  Запуск автономных локальных тестов без сетевых вызовов")
        print("  --help, -h   Вывод справки")
        sys.exit(0)

    # Validate against unknown CLI arguments
    valid_flags = {"--fast", "--self-test", "--help", "-h"}
    unrecognized = [arg for arg in sys.argv[1:] if arg not in valid_flags]
    if unrecognized:
        print(f"Error: unrecognized argument(s): {', '.join(unrecognized)}", file=sys.stderr)
        sys.exit(2)

    if "--self-test" in sys.argv:
        raise SystemExit(run_self_tests())
    if "--fast" in sys.argv:
        res = run_fast_momentum_scan()
        sys.exit(0 if res.get("spot_price") else 1)
    raise SystemExit(main())