#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC Market Intelligence v4.2 — расширенный бесплатный multi-exchange конвейер с контролем качества данных.

Собирает открытую телеметрию Binance (спот/фьючерсы с облачным фолбэком на Bybit V5 и Coinbase L2),
макро-активы (Yahoo Finance), календарь событий (Forex Factory), новостной фон (RSS),
скриншот карты ликвидаций (CoinGlass) и историю предыдущих запусков.
Передает срез в Gemini (по умолчанию gemini-3.8-flash с переключением на gemini-3.7-flash).
"""

from __future__ import annotations

import base64
import concurrent.futures
import html
import json
import math
import os
import re
import statistics
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

# Принудительная настройка UTF-8 вывода для надежной работы на Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from quant_enhancements import (
    REGIME_BALANCED_NORMAL,
    REGIME_HIGH_VOL_SQUEEZE,
    REGIME_LOW_VOL_CONSOLIDATION,
    REGIME_TRENDING_BEAR,
    REGIME_TRENDING_BULL,
    REGIME_WEIGHTS,
    calculate_liquidity_aware_stops,
    calculate_regime_adaptive_bias,
    compute_calibration_performance_metrics,
    detect_market_regime,
)

genai = None
types = None

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

SUPPORTED_GEMINI_MODELS = ("gemini-3.8-flash", "gemini-3.7-flash")
DEFAULT_GEMINI_MODEL = "gemini-3.8-flash"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL).strip() or DEFAULT_GEMINI_MODEL
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
UI_SETTINGS_FILE = CACHE_DIR / "ui_settings.json"

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


def atomic_write_text(filepath: Path, content: str) -> None:
    """Атомарная запись текстового или JSON-файла через временный файл."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(filepath)
    except Exception:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        filepath.write_text(content, encoding="utf-8")


def atomic_write_json(filepath: Path, data: Any) -> None:
    """Атомарная сериализация структуры данных в JSON на диск."""
    atomic_write_text(filepath, json.dumps(data, ensure_ascii=False, indent=2))


def get_configured_gemini_model() -> str:
    """Возвращает выбранную пользователем модель Gemini (по умолчанию gemini-3.8-flash)."""
    try:
        if UI_SETTINGS_FILE.exists():
            cfg = json.loads(UI_SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(cfg, dict):
                m = str(cfg.get("gemini_model", "")).strip()
                if m in SUPPORTED_GEMINI_MODELS:
                    return m
    except Exception:
        pass
    env_m = os.getenv("GEMINI_MODEL", GEMINI_MODEL).strip()
    return env_m if env_m else DEFAULT_GEMINI_MODEL


def set_configured_gemini_model(model_name: str) -> str:
    """Сохраняет выбранную модель Gemini для синхронизации между UI и CLI."""
    global GEMINI_MODEL
    clean_model = model_name.strip() if model_name else DEFAULT_GEMINI_MODEL
    if clean_model not in SUPPORTED_GEMINI_MODELS:
        clean_model = DEFAULT_GEMINI_MODEL
    os.environ["GEMINI_MODEL"] = clean_model
    GEMINI_MODEL = clean_model
    try:
        cfg = {}
        if UI_SETTINGS_FILE.exists():
            cfg = json.loads(UI_SETTINGS_FILE.read_text(encoding="utf-8"))
            if not isinstance(cfg, dict):
                cfg = {}
        cfg["gemini_model"] = clean_model
        cfg["updated_at_utc"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        atomic_write_json(UI_SETTINGS_FILE, cfg)
    except Exception:
        pass
    return clean_model


def get_ai_telemetry(last_status: Optional[str] = None, used_model: Optional[str] = None) -> dict:
    """Формирует телеметрию состояния ИИ-модуля для боковой панели терминала."""
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip()
    configured_model = get_configured_gemini_model()
    has_key = bool(api_key)
    status = last_status or ("ONLINE" if has_key else "STANDBY_NO_KEY")
    return {
        "status": status,
        "api_key_configured": has_key,
        "configured_model": configured_model,
        "active_model": used_model or configured_model,
        "supported_models": list(SUPPORTED_GEMINI_MODELS),
        "Updated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


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
        atomic_write_json(cache_file, data)
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
        response = SESSION.get(url, params=params, timeout=(0.8, min(TIMEOUT_SEC, 1.8)))
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        is_451 = hasattr(exc, "response") and exc.response is not None and getattr(exc.response, "status_code", None) == 451
        if is_451 and "api.binance.com" in url:
            alt_url = url.replace("https://api.binance.com", "https://data-api.binance.vision")
            try:
                alt_resp = SESSION.get(alt_url, params=params, timeout=(0.8, min(TIMEOUT_SEC, 1.8)))
                alt_resp.raise_for_status()
                return alt_resp.json()
            except Exception:
                pass
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
            label = "Положительная taker-дельта на споте (1h и 4h); прокси агрессивных рыночных покупок"
        elif d1 < 0 and d4 < 0:
            label = "Отрицательная taker-дельта на споте (1h и 4h); прокси агрессивных рыночных продаж"
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
        if highs[i] > max(highs[i - 2 : i] + highs[i + 1 : i + 3]):
            swing_highs.append({"price": highs[i], "index": i})
        if lows[i] < min(lows[i - 2 : i] + lows[i + 1 : i + 3]):
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

    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [max(x, 0) for x in deltas]
    losses = [max(-x, 0) for x in deltas]
    avg_gain = statistics.mean(gains[-14:]) if len(gains) >= 14 else None
    avg_loss = statistics.mean(losses[-14:]) if len(losses) >= 14 else None
    rsi = (
        (100 - 100 / (1 + avg_gain / avg_loss))
        if avg_gain is not None and avg_loss not in (None, 0)
        else (100.0 if avg_gain and avg_loss == 0 else None)
    )

    true_ranges = []
    for i in range(1, len(closed)):
        true_ranges.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
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
    lookback = min(20, len(closes) - 1)
    return_pct = (last_close / closes[-1 - lookback] - 1) * 100 if closes[-1 - lookback] else None
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

    vwap20 = None
    if len(closed) >= 20 and sum(volumes[-20:]) > 0:
        vwap20 = sum(
            ((highs[i] + lows[i] + closes[i]) / 3) * volumes[i] for i in range(len(closed) - 20, len(closed))
        ) / sum(volumes[-20:])
    ema12, ema26 = ema(closes, 12), ema(closes, 26)
    macd_line = (ema12 - ema26) if ema12 is not None and ema26 is not None else None
    macd_hist = None
    if len(closes) >= 34:
        macd_series = []
        for j in range(26, len(closes) + 1):
            e12j, e26j = ema(closes[:j], 12), ema(closes[:j], 26)
            if e12j is not None and e26j is not None:
                macd_series.append(e12j - e26j)
        if len(macd_series) >= 9:
            macd_hist = macd_series[-1] - ema(macd_series, 9)
    bb_mid = sma(closes, 20)
    bb_std = statistics.pstdev(closes[-20:]) if len(closes) >= 20 else None
    bb_upper = bb_mid + 2 * bb_std if bb_mid is not None and bb_std is not None else None
    bb_lower = bb_mid - 2 * bb_std if bb_mid is not None and bb_std is not None else None
    bb_percent_b = (
        (last_close - bb_lower) / (bb_upper - bb_lower)
        if bb_upper is not None and bb_lower is not None and bb_upper != bb_lower
        else None
    )

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
        "return_last_1_candle_pct": round((closes[-1] / closes[-2] - 1) * 100, 3) if closes[-2] else None,
        "return_last_4_candles_pct": round((closes[-1] / closes[-5] - 1) * 100, 3) if len(closes) >= 5 and closes[-5] else None,
        "return_last_24_candles_pct": round((closes[-1] / closes[-25] - 1) * 100, 3) if len(closes) >= 25 and closes[-25] else None,
        "ema20": round(_ema20, 2) if (_ema20 := ema(closes, 20)) is not None else None,
        "ema50": round(_ema50, 2) if (_ema50 := ema(closes, 50)) is not None else None,
        "rolling_vwap20_proxy": round(vwap20, 2) if vwap20 is not None else None,
        "close_vs_rolling_vwap20_pct": round((last_close / vwap20 - 1) * 100, 3) if vwap20 else None,
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
        "indicator_limits": "EMA/RSI/ATR/MACD/Bollinger/VWAP/volume are descriptive.",
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
    if hours <= 1:
        tolerance = 0.25
    elif hours <= 4:
        tolerance = 0.75
    else:
        tolerance = 1.5
    if abs(actual_hours - hours) > tolerance:
        return {
            "available": False,
            "reason": f"Ближайший снимок {actual_hours:.2f}ч назад; отклонение от горизонта {hours}ч больше {tolerance:.2f}ч",
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


def _compute_depth_from_lists(raw_bids: list, raw_asks: list, threshold_pct: float = 1.0) -> Optional[dict]:
    """Вспомогательный расчет глубины стакана в коридоре ±threshold_pct% от mid-price."""
    try:
        bids_parsed = [(float(p), float(q)) for p, q in raw_bids]
        asks_parsed = [(float(p), float(q)) for p, q in raw_asks]
        if not bids_parsed or not asks_parsed:
            return None
        best_bid = bids_parsed[0][0]
        best_ask = asks_parsed[0][0]
        mid = (best_bid + best_ask) / 2.0
        if mid <= 0:
            return None
        lower_bound = mid * (1.0 - threshold_pct / 100.0)
        upper_bound = mid * (1.0 + threshold_pct / 100.0)

        bids = [x for x in bids_parsed if x[0] >= lower_bound]
        asks = [x for x in asks_parsed if x[0] <= upper_bound]

        bid_qty = sum(q for _, q in bids)
        ask_qty = sum(q for _, q in asks)

        return {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_bps": round((best_ask - best_bid) / mid * 10000, 3),
            "threshold_pct": threshold_pct,
            "bid_depth_base_qty": round(bid_qty, 3),
            "ask_depth_base_qty": round(ask_qty, 3),
            "bid_vs_ask_ratio": round(bid_qty / ask_qty, 3) if ask_qty else None,
            "interpretation_limit": f"Snapshot strictly measuring bids/asks within ±{threshold_pct}% of mid price.",
        }
    except Exception:
        return None


def fetch_orderbook_snapshot(base_url: str, path: str, symbol: str, limit: int = 1000, threshold_pct: float = 1.0) -> Optional[dict]:
    data = safe_get_json(f"{base_url}{path}", {"symbol": symbol, "limit": limit})
    if not isinstance(data, dict) or not data.get("bids") or not data.get("asks"):
        return None
    return _compute_depth_from_lists(data["bids"], data["asks"], threshold_pct=threshold_pct)


def calculate_zscore(current_val: float, history_vals: list[float], eps: float = 1e-6) -> Optional[float]:
    if len(history_vals) < 2:
        return None
    try:
        mean = statistics.mean(history_vals)
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
        "bias_contribution": score,
    }


def calculate_quant_bias(metrics: dict, regime_adaptive: bool = False) -> dict:
    if regime_adaptive:
        return calculate_regime_adaptive_bias(metrics)
    score = 0.0
    breakdown = {}

    # 1. Daily VWAP trend (±15 pts)
    struct = metrics.get("market_structure", {}).get("1d", {})
    if struct.get("close_vs_rolling_vwap20_pct") is not None:
        val = struct["close_vs_rolling_vwap20_pct"]
        pts = round(15.0 * math.tanh(val / 0.75), 1)
        score += pts
        breakdown["1d_vwap_trend"] = int(round(pts))

    # 2. 24h Spot CVD (±20 pts)
    spot = metrics.get("spot_taker_delta", {})
    if spot.get("24h", {}).get("delta_btc") is not None:
        delta_btc = spot["24h"]["delta_btc"]
        pts = round(20.0 * math.tanh(delta_btc / 400.0), 1)
        score += pts
        breakdown["24h_spot_cvd"] = int(round(pts))

    # 3. Spot Orderbook Imbalance ±1% (±20 pts)
    ob_spot = metrics.get("orderbook_depth", {}).get("spot", {})
    if ob_spot and ob_spot.get("bid_vs_ask_ratio") is not None:
        ratio = ob_spot["bid_vs_ask_ratio"]
        if ratio > 0:
            log_r = math.log(ratio)
            pts = round(20.0 * math.tanh(log_r / 0.35), 1)
            score += pts
            breakdown["spot_orderbook_imbalance"] = int(round(pts))

    # 4. Futures Orderbook Imbalance ±1% (±15 pts)
    ob_fut = metrics.get("orderbook_depth", {}).get("futures", {})
    if ob_fut and ob_fut.get("bid_vs_ask_ratio") is not None:
        ratio = ob_fut["bid_vs_ask_ratio"]
        if ratio > 0:
            log_r = math.log(ratio)
            pts = round(15.0 * math.tanh(log_r / 0.35), 1)
            score += pts
            breakdown["futures_orderbook_imbalance"] = int(round(pts))

    # 5. Divergence Engine (±15 pts)
    div = metrics.get("divergence_engine", {}).get("24h_divergence", {})
    if div:
        pts = div.get("bias_contribution", 0)
        score += pts
        breakdown["24h_divergence_engine"] = int(pts)

    # 6. OI Squeeze Risk (±15 pts)
    oi_z = metrics.get("statistical_z_scores", {}).get("oi_zscore")
    if oi_z is not None and abs(oi_z) > 1.8:
        fund = metrics.get("derivatives", {}).get("current_funding_rate_pct", 0)
        if fund is not None:
            fund_dev = round(fund - 0.010, 6)
            if oi_z > 1.8 and fund_dev >= 0.005:
                pts = -15
            elif oi_z > 1.8 and fund_dev <= -0.005:
                pts = 15
            elif oi_z < -1.8:
                pts = 10 if fund_dev < 0 else -10
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

    regime_details = detect_market_regime(metrics) if metrics else {"regime": "BALANCED_NORMAL"}
    return {
        "composite_score": final_score,
        "bias_label": label,
        "breakdown": breakdown,
        "market_regime": regime_details.get("regime", "BALANCED_NORMAL"),
        "regime_info": regime_details,
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
    и целевые уровни тейк-профита 1:2 и 1:3 Risk:Reward.
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
    Получает актуальные ончейн-метрики (MVRV Z-Score, NUPL, Realized Price) через REST API.
    Использует локальный дисковый кэш (TTL 12ч).
    """
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
    """Выводит консольный дашборд для режима быстрого сканирования (--fast)."""
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

    calib = snapshot.get("quant_bias_calibration", {})
    wr = calib.get("overall_win_rate_pct")
    wr_str = f"{wr}%" if wr is not None else "Накапливает данные"

    print("\n" + "=" * 70)
    print("BTC MARKET INTELLIGENCE — FAST MOMENTUM SCANNER (REST-ONLY)")
    print("=" * 70)
    print(f"Время (UTC): {now_str} | Время выполнения: {exec_sec:.2f}с")
    print("\n[КОЛИЧЕСТВЕННЫЙ СКОРИНГ (QUANT BIAS)]")
    print("-" * 70)
    sign = "+" if score > 0 else ""
    print(f"  Скоринг:      {sign}{score} / 100  [{label}]")
    if bd:
        for k, v in bd.items():
            k_disp = k.replace("_", " ").title()
            v_sign = "+" if v > 0 else ""
            print(f"    • {k_disp:32s}: {v_sign}{v} pts")
    print("\n[ЦЕНА И ДЕРИВАТИВЫ]")
    print("-" * 70)
    print(f"  Spot Price:   ${spot_p:,.2f}  |  Futures Price: ${fut_p:,.2f}  |  Basis: ${basis_usd:+.2f} ({basis_pct:+.2f}%)")
    oi_z_str = f"{oi_z:+.2f}" if oi_z is not None else "N/A"
    fund_z_str = f"{fund_z:+.2f}" if fund_z is not None else "N/A"
    live_oi_val = live_oi if live_oi is not None else 0.0
    fund_pct_val = fund_pct if fund_pct is not None else 0.0
    print(f"  Live OI:      {live_oi_val:,.1f} BTC  |  OI Z-Score:   {oi_z_str}")
    print(f"  Funding Rate: {fund_pct_val:+.4f}%    |  Fund Z-Score: {fund_z_str}")
    print("\n[РИСК-МОДЕЛЬ ATR (R:R 1:2 И 1:3)]")
    print("-" * 70)
    print(f"  ATR14: ${atr14:,.2f} | Буфер (1.5x ATR): ${buffer:,.2f} | Рекомендация: {direction}")
    print(f"  LONG  -> SL: ${long_setup.get('stop_loss', 0.0):,.2f} | TP1: ${long_setup.get('tp1_rr2', 0.0):,.2f} | TP2: ${long_setup.get('tp2_rr3', 0.0):,.2f}")
    print(f"  SHORT -> SL: ${short_setup.get('stop_loss', 0.0):,.2f} | TP1: ${short_setup.get('tp1_rr2', 0.0):,.2f} | TP2: ${short_setup.get('tp2_rr3', 0.0):,.2f}")
    print("\n[ОНЧЕЙН И КАЛИБРОВКА]")
    print("-" * 70)
    mvrv_str = f"{mvrv_z:.2f}" if mvrv_z is not None else "N/A"
    nupl_str = f"{nupl_v:.3f}" if nupl_v is not None else "N/A"
    rp_str = f"${rp_v:,.2f}" if rp_v is not None else "N/A"
    print(f"  MVRV Z-Score: {mvrv_str} [{mvrv_stage}] | NUPL: {nupl_str} [{nupl_stage}] | Realized: {rp_str}")
    print(f"  Винрейт:      {wr_str}")
    print("=" * 70 + "\n")


def run_fast_momentum_scan(quiet: bool = False, mock: bool = False) -> dict:
    """
    Режим мгновенного импульса (--fast):
    Параллельный опрос REST API Binance, Bybit, Deribit, Coinbase, CME и BGeometrics.
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
            },
            "market_regime": "BALANCED_NORMAL",
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
        ob_spot_mock = {
            "best_bid": 83048.0,
            "best_ask": 83052.0,
            "bid_depth_base_qty": 320.4,
            "ask_depth_base_qty": 215.0,
            "bid_vs_ask_ratio": 1.49,
            "threshold_pct": 1.0,
        }
        binance = {
            "prices": {"spot_last": spot_price, "futures_last": 83020.0, "basis_usd": -30.0, "basis_pct": -0.036},
            "spot_24h_summary": {"change_pct": 1.25, "high": 83500.0, "low": 81500.0},
            "derivatives": {"live_open_interest_btc": 92500, "current_funding_rate_pct": 0.0012},
            "statistical_z_scores": {"oi_zscore": -0.85, "funding_zscore": -1.20},
            "divergence_engine": {"24h_divergence": {"divergence_state": "Bullish Continuation (Long Build-up)"}},
            "orderbook_depth": {"spot": ob_spot_mock, "futures": ob_spot_mock},
            "orderbook_depth_summary": {"bids_btc": 320.4, "asks_btc": 215.0, "bid_ask_ratio": 1.49},
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
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=6)
        try:
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
        finally:
            pool.shutdown(wait=False)

        spot_price = binance.get("prices", {}).get("spot_last", 0.0)
        if spot_price > 0 and cme_basis.get("status") == "OK" and cme_basis.get("cme_last_price"):
            cme_last = cme_basis["cme_last_price"]
            cme_basis["basis_vs_spot_usd"] = round(cme_last - spot_price, 2)
            cme_basis["basis_vs_spot_pct"] = round((cme_last / spot_price - 1) * 100, 3)
            cme_basis["weekend_gap_usd"] = round(spot_price - cme_last, 2)

        # Если спотовый стакан Binance был недоступен, используем данные Coinbase Pro L2
        ob_depth = binance.get("orderbook_depth", {})
        if (not ob_depth.get("spot") or not ob_depth["spot"].get("bid_vs_ask_ratio")) and coinbase_ob.get("status") == "OK":
            cb_mapped = {
                "best_bid": coinbase_ob.get("best_bid"),
                "best_ask": coinbase_ob.get("best_ask"),
                "bid_depth_base_qty": coinbase_ob.get("bid_depth_btc", 0.0),
                "ask_depth_base_qty": coinbase_ob.get("ask_depth_btc", 0.0),
                "bid_vs_ask_ratio": coinbase_ob.get("bid_vs_ask_ratio", 1.0),
                "threshold_pct": 1.0,
            }
            binance.setdefault("orderbook_depth", {})["spot"] = cb_mapped
            binance["orderbook_depth_summary"] = {
                "bids_btc": cb_mapped["bid_depth_base_qty"],
                "asks_btc": cb_mapped["ask_depth_base_qty"],
                "bid_ask_ratio": cb_mapped["bid_vs_ask_ratio"],
            }
            binance["quant_bias"] = calculate_quant_bias(binance)

        quant_bias = binance.get("quant_bias", {})
        score = quant_bias.get("composite_score", 0)

        struct_4h = binance.get("market_structure", {}).get("4h", {})
        atr14_val = struct_4h.get("atr14_price")
        if not atr14_val:
            struct_1h = binance.get("market_structure", {}).get("1h", {})
            atr14_val = struct_1h.get("atr14_price", 0.0)

        atr_risk = calculate_atr_risk_levels(
            spot_price=spot_price,
            atr14=atr14_val,
            quant_bias_score=score,
            orderbook_depth=binance.get("orderbook_depth"),
        )
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
        "ai_telemetry": get_ai_telemetry(),
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
            atomic_write_json(RAW_SNAPSHOT_FILE, snapshot)
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
        pool = concurrent.futures.ThreadPoolExecutor(max_workers=16)
        try:
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
            f_ob_spot = pool.submit(fetch_orderbook_snapshot, BINANCE_SPOT, "/api/v3/depth", SYMBOL, 100, 1.0)
            f_ob_fut = pool.submit(fetch_orderbook_snapshot, BINANCE_FUTURES, "/fapi/v1/depth", SYMBOL, 100, 1.0)

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
        finally:
            pool.shutdown(wait=False)
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

    # 1. Спотовый фолбэк (data-api.binance.vision / Coinbase)
    if not isinstance(spot_ticker, dict) or not spot_ticker.get("price"):
        alt_spot = safe_get_json("https://data-api.binance.vision/api/v3/ticker/price", {"symbol": SYMBOL})
        if isinstance(alt_spot, dict) and alt_spot.get("price"):
            spot_ticker = alt_spot
        else:
            cb_data = safe_get_json("https://api.exchange.coinbase.com/products/BTC-USD/ticker")
            if isinstance(cb_data, dict) and cb_data.get("price"):
                spot_ticker = {"symbol": SYMBOL, "price": str(cb_data["price"])}

    # 2. Полный фьючерсный фолбэк (Bybit V5) при блокировке fapi.binance.com (HTTP 451 в США / Streamlit Cloud)
    if not isinstance(fut_ticker, dict) or not fut_ticker.get("price"):
        bybit_data = safe_get_json("https://api.bybit.com/v5/market/tickers", {"category": "linear", "symbol": "BTCUSDT"})
        if isinstance(bybit_data, dict) and bybit_data.get("result", {}).get("list"):
            bybit_item = bybit_data["result"]["list"][0]
            fut_ticker = {"symbol": SYMBOL, "price": str(bybit_item.get("lastPrice", "0"))}
            if not isinstance(premium, dict) or not premium.get("markPrice"):
                premium = {
                    "markPrice": str(bybit_item.get("markPrice", fut_ticker["price"])),
                    "indexPrice": str(
                        bybit_item.get(
                            "indexPrice",
                            spot_ticker.get("price", fut_ticker["price"]) if isinstance(spot_ticker, dict) else fut_ticker["price"],
                        )
                    ),
                    "lastFundingRate": str(bybit_item.get("fundingRate", "0.0001")),
                }
            if not isinstance(live_oi_data, dict) or not live_oi_data.get("openInterest"):
                live_oi_data = {
                    "openInterest": str(bybit_item.get("openInterest", "0")),
                    "time": int(time.time() * 1000),
                }

            # Фолбэк истории OI (для сохранения OI Z-Score и Divergence Engine в облаке)
            if not isinstance(oi_history, list) or not oi_history:
                bb_oi_res = safe_get_json(
                    "https://api.bybit.com/v5/market/open-interest",
                    {"category": "linear", "symbol": "BTCUSDT", "intervalTime": "1h", "limit": 50},
                )
                if isinstance(bb_oi_res, dict) and bb_oi_res.get("result", {}).get("list"):
                    bb_oi_list = bb_oi_res["result"]["list"]
                    oi_history = [
                        {"timestamp": int(r.get("timestamp", 0)), "sumOpenInterest": str(r.get("openInterest", "0"))}
                        for r in reversed(bb_oi_list)
                        if r.get("timestamp") and r.get("openInterest")
                    ]

            # Фолбэк истории фандинга (для сохранения Funding Z-Score в облаке)
            if not isinstance(last_funding, list) or not last_funding:
                bb_fund_res = safe_get_json(
                    "https://api.bybit.com/v5/market/funding/history",
                    {"category": "linear", "symbol": "BTCUSDT", "limit": 50},
                )
                if isinstance(bb_fund_res, dict) and bb_fund_res.get("result", {}).get("list"):
                    bb_fund_list = bb_fund_res["result"]["list"]
                    last_funding = [
                        {"fundingRate": str(r.get("fundingRate", "0.0001")), "fundingTime": int(r.get("fundingRateTimestamp", 0))}
                        for r in reversed(bb_fund_list)
                        if r.get("fundingRate") is not None
                    ]

            # Фолбэк фьючерсного стакана (для сохранения Futures Book Imbalance в облаке)
            if not ob_fut or not ob_fut.get("best_bid"):
                bb_book_res = safe_get_json(
                    "https://api.bybit.com/v5/market/orderbook",
                    {"category": "linear", "symbol": "BTCUSDT", "limit": 200},
                )
                if isinstance(bb_book_res, dict) and bb_book_res.get("result"):
                    bb_book = bb_book_res["result"]
                    if bb_book.get("b") and bb_book.get("a"):
                        ob_fut = _compute_depth_from_lists(bb_book["b"], bb_book["a"], threshold_pct=1.0)

    # 3. Фолбэк фьючерсных свечей через Bybit Linear V5
    bybit_map = {"1w": "W", "1d": "D", "4h": "240", "1h": "60", "15m": "15", "5m": "5", "12h": "720", "3d": "D"}
    interval_ms_map = {
        "1w": 604800000,
        "1d": 86400000,
        "4h": 14400000,
        "1h": 3600000,
        "15m": 900000,
        "5m": 300000,
        "12h": 43200000,
        "3d": 259200000,
    }
    for inter, lim in intervals_fut:
        if not raw_fut.get(inter) or len(raw_fut[inter]) < 5:
            bb_code = bybit_map.get(inter, "60")
            dur_ms = interval_ms_map.get(inter, 3600000)
            bb_res = safe_get_json(
                "https://api.bybit.com/v5/market/kline",
                {"category": "linear", "symbol": "BTCUSDT", "interval": bb_code, "limit": lim},
            )
            if isinstance(bb_res, dict) and bb_res.get("result", {}).get("list"):
                bb_klines = bb_res["result"]["list"]
                converted = []
                for k in reversed(bb_klines):
                    converted.append([
                        int(k[0]), k[1], k[2], k[3], k[4], k[5],
                        int(k[0]) + dur_ms - 1, k[6], 100,
                        float(k[5]) * 0.5, float(k[6]) * 0.5, "0"
                    ])
                raw_fut[inter] = converted

    # 4. Фолбэк спотовых свечей и стакана через data-api.binance.vision
    for inter, lim in intervals_spot:
        if not raw_spot.get(inter) or len(raw_spot[inter]) < 5:
            alt_res = safe_get_json("https://data-api.binance.vision/api/v3/klines", {"symbol": SYMBOL, "interval": inter, "limit": lim})
            if isinstance(alt_res, list) and len(alt_res) > 0:
                raw_spot[inter] = alt_res

    if not k1m or len(k1m) < 5:
        alt_k1m = safe_get_json("https://data-api.binance.vision/api/v3/klines", {"symbol": SYMBOL, "interval": "1m", "limit": 15})
        if isinstance(alt_k1m, list) and len(alt_k1m) > 0:
            k1m = alt_k1m
            spot_flow = fetch_spot_flow(SYMBOL, {**raw_spot, "1m": k1m})

    if not isinstance(ticker24, dict) or not ticker24.get("lastPrice"):
        alt_t24 = safe_get_json("https://data-api.binance.vision/api/v3/ticker/24hr", {"symbol": SYMBOL})
        if isinstance(alt_t24, dict):
            ticker24 = alt_t24

    if not ob_spot or not ob_spot.get("best_bid"):
        ob_spot = fetch_orderbook_snapshot("https://data-api.binance.vision", "/api/v3/depth", SYMBOL, 100, 1.0)

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

    # Расчет Z-Scores с защитой от нулевой дисперсии на плоском фандинге
    oi_zscore = None
    if isinstance(oi_history, list) and live_oi is not None:
        oi_vals = [finite_float(x.get("sumOpenInterest")) for x in oi_history]
        oi_vals = [x for x in oi_vals if x is not None]
        oi_zscore = calculate_zscore(live_oi, oi_vals)

    funding_zscore = None
    if isinstance(last_funding, list) and funding_rate is not None:
        fund_vals = [finite_float(x.get("fundingRate")) for x in last_funding]
        fund_vals = [x for x in fund_vals if x is not None]
        funding_zscore = calculate_zscore(funding_rate, fund_vals, eps=1e-9)
        if funding_zscore is None and len(fund_vals) >= 2:
            mean_f = statistics.mean(fund_vals)
            funding_zscore = round(max(-5.0, min(5.0, (funding_rate - mean_f) / 0.00005)), 3)

    # Закрытые часовые свечи для точной пост-входовой проверки SL/TP в калибраторе
    closed_1h_klines = []
    for c in only_closed_klines(raw_spot.get("1h") or raw_fut.get("1h") or [])[-30:]:
        try:
            closed_1h_klines.append({
                "open_time_ms": int(c[0]),
                "close_time_ms": int(c[6]),
                "high": float(c[2]),
                "low": float(c[3]),
                "close": float(c[4]),
            })
        except Exception:
            continue

    ob_spot_dict = ob_spot if isinstance(ob_spot, dict) else {}
    ob_summary = {
        "bids_btc": ob_spot_dict.get("bid_depth_base_qty", 0.0),
        "asks_btc": ob_spot_dict.get("ask_depth_base_qty", 0.0),
        "bid_ask_ratio": ob_spot_dict.get("bid_vs_ask_ratio", 1.0),
    }

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
        "orderbook_depth_summary": ob_summary,
        "market_structure": structures,
        "spot_market_structure": spot_structures,
        "recent_closed_klines_1h": closed_1h_klines,
        "structure_source": "Separate closed-candle structure for Binance spot and USD-M futures.",
    }

    price_chg_24 = result["spot_24h_summary"]["change_pct"]
    oi_chg_24 = oi_metrics.get("24h", {}).get("change_pct")
    if price_chg_24 is not None and oi_chg_24 is not None:
        result["divergence_engine"] = {
            "24h_divergence": detect_divergence_engine(price_chg_24, oi_chg_24)
        }

    result["statistical_z_scores"] = {
        "oi_zscore": oi_zscore,
        "funding_zscore": funding_zscore,
        "note": "Z-Scores using historical observations to identify statistical anomalies (> 2.0 or < -2.0).",
    }

    result["quant_bias"] = calculate_quant_bias(result)

    atr14_val = structures.get("4h", {}).get("atr14_price") or structures.get("1h", {}).get("atr14_price", 0.0)
    score_val = result["quant_bias"].get("composite_score", 0)
    result["risk_model"] = calculate_atr_risk_levels(
        spot_price=spot_price,
        atr14=atr14_val,
        quant_bias_score=score_val,
        orderbook_depth=result["orderbook_depth"],
    )
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
    """Free cross-check: Bybit linear BTCUSDT price, OI, funding, account ratio and orderbook."""
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
        out["ticker"] = {
            k: finite_float(t.get(k))
            for k in ("lastPrice", "markPrice", "indexPrice", "fundingRate", "openInterest", "turnover24h", "volume24h", "price24hPcnt")
        }
        out["ticker"]["price24hPcnt_pct"] = round((out["ticker"].get("price24hPcnt") or 0) * 100, 4)
    else:
        out["ticker"] = {"status": "UNAVAILABLE", "reason": ticker.get("_error", "No ticker data") if isinstance(ticker, dict) else "No data"}
    oi_rows = oi.get("list", []) if isinstance(oi, dict) else []
    oi_rows = sorted(oi_rows, key=lambda r: int(r.get("timestamp", 0))) if oi_rows else []
    oi_series = []
    for row in oi_rows:
        ts = finite_float(row.get("timestamp"))
        val = finite_float(row.get("openInterest"))
        if ts is not None and val is not None:
            oi_series.append({"timestamp_utc": iso_utc(datetime.fromtimestamp(ts / 1000, tz=timezone.utc)), "open_interest": val})
    oi_changes = {}
    if len(oi_series) >= 2:
        latest = oi_series[-1]
        for hours in (1, 4, 24):
            target = datetime.fromisoformat(latest["timestamp_utc"].replace("Z", "+00:00")) - timedelta(hours=hours)
            candidates = [
                r
                for r in oi_series
                if abs((datetime.fromisoformat(r["timestamp_utc"].replace("Z", "+00:00")) - target).total_seconds())
                <= hours * 3600 * 0.25 + 1800
            ]
            if candidates:
                prev = min(
                    candidates,
                    key=lambda r: abs((datetime.fromisoformat(r["timestamp_utc"].replace("Z", "+00:00")) - target).total_seconds()),
                )
                oi_changes[f"{hours}h"] = {
                    "available": True,
                    "from": prev,
                    "to": latest,
                    "change_pct": round((latest["open_interest"] / prev["open_interest"] - 1) * 100, 3) if prev["open_interest"] else None,
                }
            else:
                oi_changes[f"{hours}h"] = {"available": False, "reason": "No sufficiently close historical OI observation"}
    out["open_interest_history"] = {
        "status": "OK" if oi_series else "UNAVAILABLE",
        "unit": "Bybit-reported contract units; do not add to USD OI without conversion",
        "series": oi_series,
        "changes": oi_changes,
    }
    fund_rows = funding.get("list", []) if isinstance(funding, dict) else []
    out["funding_history"] = [
        {
            "funding_rate_pct": round(finite_float(r.get("fundingRate"), 0) * 100, 5),
            "funding_time_utc": iso_utc(datetime.fromtimestamp(int(r.get("fundingRateTimestamp", 0)) / 1000, tz=timezone.utc))
            if r.get("fundingRateTimestamp")
            else None,
        }
        for r in fund_rows
    ]
    ratio_rows = ratio.get("list", []) if isinstance(ratio, dict) else []
    out["account_long_short_ratio"] = [
        {"timestamp": r.get("timestamp"), "buy_ratio": finite_float(r.get("buyRatio")), "sell_ratio": finite_float(r.get("sellRatio"))}
        for r in ratio_rows[:24]
    ]
    if isinstance(book, dict) and book.get("b") and book.get("a"):
        bids = [(finite_float(x[0], 0), finite_float(x[1], 0)) for x in book["b"]]
        asks = [(finite_float(x[0], 0), finite_float(x[1], 0)) for x in book["a"]]
        bid_usd = sum(p * q for p, q in bids)
        ask_usd = sum(p * q for p, q in asks)
        out["orderbook_snapshot"] = {
            "status": "OK",
            "timestamp_ms": book.get("ts"),
            "bid_notional_usd_top50": round(bid_usd, 2),
            "ask_notional_usd_top50": round(ask_usd, 2),
            "bid_ask_notional_ratio": round(bid_usd / ask_usd, 4) if ask_usd else None,
            "warning": "Single snapshot; not a predictive signal and can be spoofed/cancelled.",
        }
    else:
        out["orderbook_snapshot"] = {"status": "UNAVAILABLE", "reason": book.get("_error") if isinstance(book, dict) else "No data"}
    out["status"] = "OK" if out.get("ticker", {}).get("lastPrice") else "PARTIAL_OR_UNAVAILABLE"
    out["interpretation_limit"] = "Bybit is a separate exchange cross-check, not global market aggregation."
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
    cached = load_disk_cache("macro_calendar_cache.json", ttl_seconds=2 * 3600)
    if cached and cached.get("status") == "OK" and cached.get("upcoming_events") is not None:
        cached["cache_status"] = "CACHE_HIT"
        return cached

    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    events = safe_get_json(url)
    if not isinstance(events, list):
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
        7: "июл", 8: "авг", 9: "сен", 10: "окт", 11: "ноя", 12: "дек",
    }

    upcoming = []
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
    dedup = []
    seen = set()
    for item in items:
        key = re.sub(r"\W+", " ", item.get("title", "").lower()).strip()
        if key and key not in seen:
            seen.add(key)
            dedup.append(item)
    return {"status": "OK" if dedup else "UNAVAILABLE", "window_hours": 36, "sources_attempted": len(feeds), "items": dedup[:12]}


# -------------------------- ETF / OPTIONS / AGGREGATE DERIVATIVES -------------

class _TableParser(HTMLParser):
    """Small dependency-free HTML table reader for Farside's published table."""
    def __init__(self):
        super().__init__()
        self.rows = []
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.rows.append(self.row)
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
            try:
                dt = datetime.strptime(date_cell, "%d %b %Y").replace(tzinfo=timezone.utc)
            except ValueError:
                continue
            vals = [_parse_money_cell(x) for x in row[1:]]
            total = vals[-1] if vals else None
            if total is None:
                continue
            fund_cells = vals[:-1] if len(vals) > 1 else []
            if fund_cells and all(v is None for v in fund_cells) and total == 0.0:
                continue
            candidates.append({"date": dt.date().isoformat(), "date_utc": iso_utc(dt), "total_net_flow_usd_millions": total})
        if not candidates:
            return {"status": "UNAVAILABLE", "source": FARSIDE_BTC_ETF_URL, "reason": "No parseable daily rows found"}
        candidates.sort(key=lambda x: x["date"])
        recent = candidates[-30:]
        flows = [x["total_net_flow_usd_millions"] for x in recent]
        n_sessions = len(flows)
        return {
            "status": "OK",
            "source": FARSIDE_BTC_ETF_URL,
            "source_note": "Farside Investors table; values in USD millions.",
            "latest": recent[-1],
            "trading_sessions_available": n_sessions,
            "latest_3_sessions_sum_usd_millions": round(sum(flows[-3:]), 2) if n_sessions >= 3 else None,
            "latest_7_sessions_sum_usd_millions": round(sum(flows[-7:]), 2) if n_sessions >= 7 else None,
            "latest_30d_sum_usd_millions": round(sum(flows[-30:]), 2) if n_sessions >= 30 else None,
            "available_history_sum_usd_millions": round(sum(flows), 2),
            "daily_history_available": recent,
            "btc_equivalent": "Not calculated here because flow date and current BTC price are not the same timestamp.",
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
        bucket = expiries.setdefault(
            key,
            {
                "expiry_utc": key,
                "call_open_interest_contracts": 0.0,
                "put_open_interest_contracts": 0.0,
                "iv_observations": [],
                "days_to_expiry": max(0, (expiry.date() - now.date()).days),
            },
        )
        if side == "C":
            bucket["call_open_interest_contracts"] += oi
            total_call_oi += oi
        else:
            bucket["put_open_interest_contracts"] += oi
            total_put_oi += oi
        total_oi += oi
        if iv is not None:
            ivs.append(iv)
            if underlying and abs(strike / underlying - 1) <= 0.03:
                bucket["iv_observations"].append(iv)
    expiry_rows = []
    for key, bucket in sorted(expiries.items()):
        obs = bucket.pop("iv_observations")
        bucket["near_atm_iv_mean_pct"] = round(statistics.mean(obs), 2) if obs else None
        bucket["put_call_oi_ratio"] = (
            round(bucket["put_open_interest_contracts"] / bucket["call_open_interest_contracts"], 3)
            if bucket["call_open_interest_contracts"]
            else None
        )
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
        "limitations": "Deribit-only, not global options market.",
    }


def fetch_deribit_dvol() -> dict:
    """Бесплатный публичный индекс подразумеваемой волатильности Bitcoin (Crypto VIX / DVOL)."""
    cached = load_disk_cache("deribit_dvol_cache.json", ttl_seconds=15 * 60)
    if cached and cached.get("current_dvol") is not None:
        cached["cache_status"] = "CACHE_HIT"
        return cached
    if cached and cached.get("status") == "UNAVAILABLE":
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
                dvol_val = float(latest[4])
                regime = (
                    "Высокая (High Volatility)"
                    if dvol_val >= 55.0
                    else ("Умеренная (Normal)" if dvol_val >= 40.0 else "Низкая (Compressed Vol)")
                )
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
                        save_disk_cache(
                            "cme_basis_cache.json",
                            {
                                "cme_last_price": cme_last,
                                "cme_prev_close": cme_prev,
                                "regular_market_time_utc": reg_time,
                            },
                        )
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
            f"{COINGLASS_API_BASE}{path}",
            params=params,
            timeout=(3, TIMEOUT_SEC),
            headers={"CG-API-KEY": COINGLASS_API_KEY, "accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or str(payload.get("code", "0")) not in ("0", "200", "None"):
            return {"status": "API_ERROR", "http_status": response.status_code, "response": payload}
        return {
            "status": "OK",
            "http_status": response.status_code,
            "data": payload.get("data"),
            "source": "CoinGlass API",
            "collected_at_utc": iso_utc(),
        }
    except Exception as exc:
        return {"status": "UNAVAILABLE", "reason": str(exc), "source": "CoinGlass API"}


def fetch_coinglass_aggregate() -> dict:
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
    return {
        "status": "OK" if ok else "PARTIAL_OR_UNAVAILABLE",
        "available_endpoint_count": ok,
        "requested_endpoint_count": len(calls),
        "metrics": calls,
        "interpretation_limit": "CoinGlass aggregates exchange data.",
    }


def collect_manual_inputs() -> list[dict]:
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
    """Очистка всплывающих окон, согласий на cookie и рекламных баннеров."""
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

    try:
        page.evaluate("""() => {
            const closeBtn = document.querySelector('button[aria-label="Close heatmap settings"]');
            if (closeBtn) {
                closeBtn.click();
            } else {
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

    try:
        page.evaluate("""() => {
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
        }""")
    except Exception:
        pass


def capture_coinglass_clean() -> list[dict]:
    if not ENABLE_SCREENSHOT or sync_playwright is None:
        return []

    captures = []
    page = None
    SCREENSHOT_FILE.parent.mkdir(parents=True, exist_ok=True)
    print("[*] Получение скриншота карты ликвидаций CoinGlass...")
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

            try:
                page.wait_for_selector("canvas", timeout=12000)
            except Exception:
                pass
            page.wait_for_timeout(2000)

            dismiss_page_overlays(page)
            try:
                page.mouse.move(0, 0)
            except Exception:
                pass
            page.wait_for_timeout(1500)
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
                    "label": "CoinGlass Liquidation Heatmap Model 3",
                    "path": str(SCREENSHOT_FILE),
                    "size_bytes": SCREENSHOT_FILE.stat().st_size,
                    "http_status": http_status,
                    "page_title": page_title,
                    "semantic_check": "PASS: HTTP + relevant page text + BTC context",
                })
            else:
                if SCREENSHOT_FILE.exists():
                    captures.append({
                        "label": "CoinGlass heatmap page screenshot — UNVERIFIED",
                        "path": str(SCREENSHOT_FILE),
                        "size_bytes": SCREENSHOT_FILE.stat().st_size,
                        "http_status": http_status,
                        "page_title": page_title,
                        "semantic_check": "FAILED_OR_INCOMPLETE",
                    })
            browser.close()
    except Exception as exc:
        print(f"[WARN] Сбой снятия скриншота: {exc}")
        try:
            if page is not None and not page.is_closed():
                page.screenshot(path=str(SCREENSHOT_FILE), full_page=False, timeout=5000)
                if SCREENSHOT_FILE.exists():
                    captures.append({
                        "label": "CoinGlass heatmap page screenshot — UNVERIFIED partial capture",
                        "path": str(SCREENSHOT_FILE),
                        "size_bytes": SCREENSHOT_FILE.stat().st_size,
                        "semantic_check": "NAVIGATION_OR_CAPTURE_ERROR",
                    })
        except Exception:
            pass

    return captures


def capture_free_dashboard_pages() -> list[dict]:
    if not ENABLE_SCREENSHOT:
        return [{"status": "DISABLED", "reason": "ENABLE_COINGLASS_SCREENSHOT=false"}]
    if sync_playwright is None:
        return [{"status": "BROWSER_UNAVAILABLE", "reason": "Install playwright and run playwright install chromium"}]
    out = []
    shots_dir = BASE_DIR / "free_dashboard_screenshots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"])
            context = browser.new_context(viewport={"width": 1920, "height": 1080}, user_agent=BROWSER_USER_AGENT)
            for label, url, keywords in FREE_DASHBOARD_PAGES:
                safe_name = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
                path = shots_dir / f"{safe_name}.png"
                page = None
                try:
                    page = context.new_page()
                    page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
                    response = page.goto(url, timeout=25000, wait_until="domcontentloaded")
                    http = response.status if response else None

                    if "cryptoquant" in url.lower():
                        try:
                            page.wait_for_selector(".highcharts-container, svg, [class*='table']", timeout=12000)
                        except Exception:
                            pass
                        page.wait_for_timeout(3000)
                    else:
                        page.wait_for_timeout(2500)

                    title = (page.title() or "").strip()
                    body = (page.locator("body").inner_text(timeout=4000) or "")[:15000]
                    lower = body.lower()

                    is_cf = any(cf in lower for cf in ("cloudflare", "performing security verification", "verify you are human", "just a moment")) or (http == 403)
                    if is_cf:
                        out.append({
                            "label": label, "url": url, "path": None, "http_status": http,
                            "page_title": title, "semantic_text_check": False,
                            "status": "BLOCKED_BY_CLOUDFLARE",
                        })
                        page.close()
                        continue

                    dismiss_page_overlays(page)
                    rendered_elements_count = page.evaluate("() => document.querySelectorAll('svg, canvas, .highcharts-container').length")
                    semantic = any(k in lower for k in keywords)

                    if "cryptoquant" in url.lower() and rendered_elements_count < 3:
                        out.append({
                            "label": label, "url": url, "path": None, "http_status": http,
                            "page_title": title, "semantic_text_check": semantic,
                            "status": "SPA_EMPTY_RENDER",
                        })
                        page.close()
                        continue

                    page.screenshot(path=str(path), full_page=False)
                    ok = bool(http and 200 <= http < 400 and semantic and path.exists() and path.stat().st_size > 20000)
                    out.append({
                        "label": label, "url": url, "path": str(path), "http_status": http,
                        "page_title": title, "semantic_text_check": semantic,
                        "rendered_charts_count": rendered_elements_count,
                        "status": "CAPTURED_PAGE_REQUIRES_VISUAL_VALIDATION" if ok else "CAPTURE_NOT_VERIFIED",
                    })
                    page.close()
                except Exception as exc:
                    out.append({"label": label, "url": url, "status": "UNAVAILABLE", "reason": str(exc), "path": None})
                    if page is not None and not page.is_closed():
                        try:
                            page.close()
                        except Exception:
                            pass
            browser.close()
    except Exception as exc:
        out.append({"status": "BROWSER_UNAVAILABLE", "reason": str(exc)})
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
            if oi is not None and finite_float(previous.get("open_interest_btc")) is not None
            else None,
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
        "quant_bias_score": quant.get("composite_score"),
        "quant_bias_label": quant.get("bias_label"),
        "oi_zscore": z_scores.get("oi_zscore"),
        "funding_zscore": z_scores.get("funding_zscore"),
        "divergence_state": div.get("divergence_state"),
    }
    history.append(row)
    cutoff = time.time() - HISTORY_LOOKBACK_HOURS * 3600
    kept = [x for x in history if finite_float(x.get("epoch"), 0) >= cutoff][-MAX_HISTORY_SNAPSHOTS:]
    atomic_write_json(HISTORY_FILE, kept)


def update_calibration_tracker(current: dict, tracker_path: Optional[Path] = None, force_time: Optional[float] = None) -> dict:
    """
    Backtest & Calibration Logger for Quant Bias.
    Отслеживает сигналы строго по историческим свечам ПОСЛЕ точки входа (Zero Lookbehind/Lookahead Bias).
    При одновременном касании SL и TP внутри одной свечи фиксирует SL_HIT (Worst-Case Execution).
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

    explicit_high_p = finite_float(current.get("high_price"))
    explicit_low_p = finite_float(current.get("low_price"))
    recent_klines_1h = current.get("recent_closed_klines_1h")
    if not isinstance(recent_klines_1h, list):
        recent_klines_1h = []

    risk = current.get("risk_model") or current.get("atr_risk")
    if not risk and spot_price:
        struct_4h = current.get("market_structure", {}).get("4h", {})
        atr14_val = struct_4h.get("atr14_price")
        if not atr14_val:
            struct_1h = current.get("market_structure", {}).get("1h", {})
            atr14_val = struct_1h.get("atr14_price", 0.0)
        if atr14_val:
            risk = calculate_atr_risk_levels(spot_price, atr14_val, score or 0)

    direction = (
        risk.get("direction", "NEUTRAL")
        if risk
        else ("LONG" if (score and score >= 15) else ("SHORT" if (score and score <= -15) else "NEUTRAL"))
    )
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

    # 1. Разрешение активных прогнозов строго по пост-входовым наблюдениям
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

            # Собираем последовательность ценовых окон строго ПОСЛЕ входа (open_time_ms > item_epoch * 1000)
            observation_windows: list[tuple[float, float]] = []
            if explicit_high_p is not None or explicit_low_p is not None:
                oh = explicit_high_p if explicit_high_p is not None else spot_price
                ol = explicit_low_p if explicit_low_p is not None else spot_price
                if oh is not None and ol is not None:
                    observation_windows.append((oh, ol))
            else:
                for kline in recent_klines_1h:
                    k_open_ms = finite_float(kline.get("open_time_ms"))
                    k_high = finite_float(kline.get("high"))
                    k_low = finite_float(kline.get("low"))
                    if k_open_ms is not None and k_open_ms > (item_epoch * 1000.0) and k_high is not None and k_low is not None:
                        observation_windows.append((k_high, k_low))
                if spot_price is not None and elapsed > 0:
                    observation_windows.append((spot_price, spot_price))

            if sl is not None and observation_windows:
                for obs_high, obs_low in observation_windows:
                    if dir_val == "LONG":
                        # Worst-case execution: SL проверяется первым
                        if obs_low <= sl:
                            resolved_now = True
                            res_type = "SL_HIT"
                            outcome = "LOSS"
                            is_win = False
                            res_price = sl
                            pnl_pct = round((sl / item_entry - 1) * 100, 2)
                            pnl_usd = round(sl - item_entry, 2)
                            break
                        elif tp2 is not None and obs_high >= tp2:
                            resolved_now = True
                            res_type = "TP2_HIT"
                            outcome = "WIN"
                            is_win = True
                            res_price = tp2
                            pnl_pct = round((tp2 / item_entry - 1) * 100, 2)
                            pnl_usd = round(tp2 - item_entry, 2)
                            break
                        elif tp1 is not None and obs_high >= tp1:
                            resolved_now = True
                            res_type = "TP1_HIT"
                            outcome = "WIN"
                            is_win = True
                            res_price = tp1
                            pnl_pct = round((tp1 / item_entry - 1) * 100, 2)
                            pnl_usd = round(tp1 - item_entry, 2)
                            break
                    elif dir_val == "SHORT":
                        if obs_high >= sl:
                            resolved_now = True
                            res_type = "SL_HIT"
                            outcome = "LOSS"
                            is_win = False
                            res_price = sl
                            pnl_pct = round((1 - sl / item_entry) * 100, 2)
                            pnl_usd = round(item_entry - sl, 2)
                            break
                        elif tp2 is not None and obs_low <= tp2:
                            resolved_now = True
                            res_type = "TP2_HIT"
                            outcome = "WIN"
                            is_win = True
                            res_price = tp2
                            pnl_pct = round((1 - tp2 / item_entry) * 100, 2)
                            pnl_usd = round(item_entry - tp2, 2)
                            break
                        elif tp1 is not None and obs_low <= tp1:
                            resolved_now = True
                            res_type = "TP1_HIT"
                            outcome = "WIN"
                            is_win = True
                            res_price = tp1
                            pnl_pct = round((1 - tp1 / item_entry) * 100, 2)
                            pnl_usd = round(item_entry - tp1, 2)
                            break

            # Case B: Закрытие по истечении 24 часов
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
                else:
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

    # 2. Добавление нового прогноза (не чаще раза в 2 часа)
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

    # 3. Атомарное сохранение базы калибровки
    try:
        atomic_write_json(path, tracker)
    except Exception as exc:
        print(f"[WARN] Сбой сохранения калибровочного логгера: {exc}")

    # 4. Вычисление метрик калибровки
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
2. ПРАКТИЧЕСКАЯ ПОЛЬЗА И ВЫВОДЫ:
   - В конце отчета ОБЯЗАТЕЛЕН раздел «ГЛАВНЫЙ ВЫВОД И ТОРГОВЫЙ ПЛАН (ГЛАВНЫЕ ОЖИДАНИЯ)». Никаких размытых фраз — дай конкретные триггеры для входа в лонг, шорт и целевые уровни.
3. МАКРОЭКОНОМИКА С ВРЕМЕНЕМ ДЛЯ ЛАТВИИ:
   - В блоке макроэкономики используй данные из `macro_calendar.upcoming_events`.
   - Обязательно выпиши ВСЕ важные события США на текущую неделю (а на выходных — на следующую торговую неделю) с указанием дня недели, даты и времени Риги (Латвия).

СТРУКТУРА ОТЧЕТА (СТРОГО СОБЛЮДАЙ ФОРМАТ):

# РЫНОЧНАЯ РАЗВЕДКА BTC/USDT

## 1. СУТЬ И БЫСТРЫЙ ВЕРДИКТ РИСК-МЕНЕДЖЕРА
- **Количественный скоринг (Quant Bias):** [Укажи балл от -100 до +100 и статус на русском]
- **Динамика скоринга:** [Как изменился балл с прошлого запуска и за 24 часа из блока historical_comparison]
- **Что происходит на рынке простыми словами:** [2-3 предложения: кто контролирует ситуацию, где зажата цена, почему именно такой скоринг].
- **Угроза резкого сквиза (выноса стопов):** [Оцени риск по Z-Score открытого интереса и ставки финансирования].
- **Исторический винрейт модели (Бэктест):** [Приведи quant_bias_calibration.readout].
- **Итоговое решение риск-менеджера:** [ВНЕ РЫНКА (ЖДАТЬ ВЫХОДА) / ЛОНГ НА ПОДТВЕРЖДЕНИИ / ШОРТ НА ПОДТВЕРЖДЕНИИ].

## 2. КТО СЕЙЧАС ДАВИТ: СПОТ ИЛИ ФЬЮЧЕРСЫ
- **Биржевой стакан (лимитные стенки ±1% от цены):**
  * Спот Binance, Фьючерсы Binance/Bybit, Институциональный стакан Coinbase Pro BTC-USD.
- **Реальный поток рыночных ордеров (Спотовая дельта):**
  * Поведение маркет-покупателей за 15 минут, 1 час, 4 часа и 24 часа.
- **Позиционирование толпы:**
  * Соотношение позиций и риск сбора ликвидности.

## 3. КАРТА ЛИКВИДАЦИЙ: ГДЕ СТОП-ЛОССЫ ТОЛПЫ
- **Магнит сверху (Пул ликвидаций шортистов):** ~$XX,XXX – $XX,XXX.
- **Магнит снизу (Пул ликвидаций лонгистов):** ~$XX,XXX – $XX,XXX.
- **Куда тянет рынок:** [Где маркетмейкеру выгоднее устроить вынос].

## 4. КЛЮЧЕВЫЕ ЦЕНОВЫЕ УРОВНИ И СТРУКТУРА
- **Сопротивления сверху и Поддержки снизу (4H и 1D).**
- **Состояние волатильности (ATR и индекс Deribit DVOL).**

## 5. МАКРОЭКОНОМИКА И ИНСТИТУЦИОНАЛЬНЫЕ ПОТОКИ (ВРЕМЯ ДЛЯ ЛАТВИИ / РИГА)
- **Календарь важных событий США (время Риги).**
- **Спотовые Bitcoin ETF, Фьючерсы CME (BTC=F) и Главные инфоповоды.**

## 6. ГЛАВНЫЙ ВЫВОД И ТОРГОВЫЙ ПЛАН (ГЛАВНЫЕ ОЖИДАНИЯ)
- **Главное ожидание по рынку.**
- **Динамическая риск-модель ATR (R:R 1:2 и 1:3):** [Используй СТРОГО точные числовые данные из risk_model].
- **План на ЛОНГ:** [Точный уровень входа, стоп-лосс по ATR, цели TP1 (1:2) и TP2 (1:3), триггер подтверждения].
- **План на ШОРТ:** [Точный уровень входа, стоп-лосс по ATR, цели TP1 (1:2) и TP2 (1:3), триггер подтверждения].
- **Что отменит сценарий (Инвалидация).**
"""


def log_gemini_usage_to_lifeos_db(
    model_name: str,
    prompt_tokens: int,
    candidates_tokens: int,
    total_tokens: int,
    summary: str = "BTC Market Intelligence — Синтез рыночного брифа",
) -> None:
    """Фиксирует расход токенов Gemini в единой базе Second Brain (LifeOS DB) для сквозного учета квот."""
    db_path = os.getenv("LIFEOS_DB_PATH", r"C:\LifeOS\lifeos.db").strip()
    if not db_path or not os.path.exists(db_path):
        return
    try:
        import sqlite3
        import uuid

        op_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(db_path, timeout=5.0) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute(
                """
                INSERT INTO operations (
                    id, created_at, telegram_message_id, summary,
                    drive_file_id, calendar_event_id, sheet_rows_json,
                    status, prompt_tokens, candidates_tokens, total_tokens, model_used
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    op_id,
                    created_at,
                    None,
                    summary,
                    None,
                    None,
                    "[]",
                    "active",
                    prompt_tokens,
                    candidates_tokens,
                    total_tokens,
                    model_name,
                ),
            )
            conn.commit()
    except Exception as exc:
        print(f"[!] Предупреждение: не удалось зафиксировать токены в LifeOS DB: {exc}")


def run_gemini_synthesis(payload: dict, screenshots: list[dict], model_override: Optional[str] = None) -> str:
    global genai, types
    api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY отсутствует в файле .env")
    if genai is None or types is None:
        try:
            from google import genai as _genai
            from google.genai import types as _types
            genai = _genai
            types = _types
        except ImportError:
            raise RuntimeError("Установите пакет google-genai: pip install google-genai")

    primary_model = model_override or get_configured_gemini_model()
    fallback_model = "gemini-3.7-flash" if primary_model == "gemini-3.8-flash" else "gemini-3.8-flash"
    candidate_models = [primary_model]
    if fallback_model not in candidate_models:
        candidate_models.append(fallback_model)

    client = genai.Client(api_key=api_key)
    prompt = (
        "Составь профессиональный утренний бриф по Bitcoin на русском языке без англицизмов и без служебных ярлыков. "
        "Особое внимание удели блоку макроэкономики (выдели все события США на неделю со временем Риги/Латвии) "
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
    for model_name in candidate_models:
        print(f"[*] Синтез рыночного брифа через {model_name}...")
        for attempt in range(2):
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_INSTRUCTION,
                    ),
                )
                text = getattr(response, "text", None)
                if text and text.strip():
                    usage = getattr(response, "usage_metadata", None)
                    prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
                    candidates_tokens = getattr(usage, "candidates_token_count", 0) or 0
                    total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + candidates_tokens)

                    log_gemini_usage_to_lifeos_db(
                        model_name=model_name,
                        prompt_tokens=prompt_tokens,
                        candidates_tokens=candidates_tokens,
                        total_tokens=total_tokens,
                        summary="BTC Market Intelligence — Синтез рыночного брифа",
                    )

                    payload["ai_telemetry"] = get_ai_telemetry(last_status="ONLINE", used_model=model_name)
                    payload["ai_telemetry"]["prompt_tokens"] = prompt_tokens
                    payload["ai_telemetry"]["candidates_tokens"] = candidates_tokens
                    payload["ai_telemetry"]["total_tokens"] = total_tokens
                    return text.strip()
                raise RuntimeError(f"Модель {model_name} вернула пустой ответ.")
            except Exception as exc:
                last_exc = exc
                err_msg = str(exc)
                if attempt < 1 and any(code in err_msg for code in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED")):
                    time.sleep(2)
                    continue
                break
    payload["ai_telemetry"] = get_ai_telemetry(last_status="DEGRADED_FALLBACK", used_model=primary_model)
    raise last_exc


def fallback_report(payload: dict, error: str) -> str:
    """Аварийный отчёт без ИИ-синтеза (математический расчет на чистом Python)."""
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

    clean_error = str(error)
    json_start = clean_error.find("{")
    if json_start > 0:
        clean_error = clean_error[:json_start].strip()
    clean_error = clean_error[:300]

    lines = [
        "# BTC Market Intelligence — Количественный срез данных",
        "",
        f"**Статус генератора ИИ:** {clean_error}",
        "",
        "## Сырые рыночные метрики",
        "",
        "| Метрика | Значение |",
        "|---------|----------|",
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
        "## Количественные метрики (Quant Bias)",
        "",
        "| Метрика | Значение |",
        "|---------|----------|",
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
        "## Ончейн-оценка (MVRV Z-Score и NUPL)",
        "",
        "| Метрика | Значение | Фаза макроцикла |",
        "|---|---|---|",
        f"| MVRV Z-Score | {onchain.get('mvrv_zscore', 'N/A')} | {onchain.get('mvrv_stage', 'UNAVAILABLE')} |",
        f"| NUPL | {onchain.get('nupl', 'N/A')} | {onchain.get('nupl_stage', 'UNAVAILABLE')} |",
        f"| Realized Price | ${onchain.get('realized_price') or 0.0:,.2f} | Фундаментальная себестоимость сети |",
    ]
    return "\n".join(lines)


def export_report_to_pdf_reportlab(report_md: str, pdf_path: Path, screenshots: Optional[list[dict]] = None) -> bool:
    """Pure-Python PDF generation via ReportLab."""
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

        font_name = "Helvetica"
        for fp in [
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans.ttf",
        ]:
            if os.path.exists(fp):
                try:
                    pdfmetrics.registerFont(TTFont("AppUnicode", fp))
                    font_name = "AppUnicode"
                    break
                except Exception:
                    pass

        doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
        title_style = ParagraphStyle("RepTitle", fontName=font_name, fontSize=16, leading=20, textColor=colors.HexColor("#0f172a"))
        body_style = ParagraphStyle("RepBody", fontName=font_name, fontSize=9, leading=13, textColor=colors.HexColor("#334155"))
        h2_style = ParagraphStyle("RepH2", fontName=font_name, fontSize=12, leading=16, textColor=colors.HexColor("#1e293b"), spaceBefore=10, spaceAfter=4)
        cell_style = ParagraphStyle("RepCell", fontName=font_name, fontSize=8, leading=11, textColor=colors.HexColor("#1e293b"))
        cell_bold = ParagraphStyle("RepCellB", fontName=font_name, fontSize=8, leading=11, textColor=colors.HexColor("#0f172a"))

        story = [
            Paragraph("<b>BTC MARKET INTELLIGENCE — АНАЛИТИЧЕСКИЙ ОТЧЕТ</b>", title_style),
            Paragraph(f"Институциональная торговая аналитика и количественный риск-менеджмент | {iso_utc()}", body_style),
            Spacer(1, 6),
            HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#cbd5e1"), spaceAfter=10),
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
                is_header = len(table_rows) == 0
                table_rows.append([Paragraph(html.escape(c), cell_bold if is_header else cell_style) for c in cells])
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
                story.append(Paragraph(f"<b>{html.escape(sline[3:])}</b>", h2_style))
            elif sline.startswith("### "):
                story.append(Paragraph(f"<b>{html.escape(sline[4:])}</b>", h2_style))
            elif sline.startswith("---"):
                story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#e2e8f0"), spaceAfter=6))
            else:
                escaped = html.escape(sline)
                clean = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped).replace("⚠", "[!]")
                story.append(Paragraph(clean, body_style))

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
                    story.append(Paragraph(f"• {html.escape(label)}", cell_bold))
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

                try:
                    b64_data = base64.b64encode(p.read_bytes()).decode("utf-8")
                    suffix = p.suffix.lower().replace(".", "")
                    mime = f"image/{suffix}" if suffix in ("png", "jpeg", "webp") else "image/png"
                    label = s.get("label", p.stem.replace("_", " ").title())
                    charts_html.append(f"""
                    <div class="chart-card">
                      <div class="chart-header">{label}</div>
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
  @page {{ size: A4; margin: 15mm; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; color: #1e293b; line-height: 1.55; font-size: 12.5px; background: #ffffff; }}
  .report-header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); color: #ffffff; padding: 16px 20px; border-radius: 8px; margin-bottom: 20px; display: flex; justify-content: space-between; align-items: center; }}
  .report-header h1 {{ margin: 0; font-size: 19px; color: #ffffff; border: none; padding: 0; }}
  .report-badge {{ background: #3b82f6; color: #ffffff; padding: 4px 10px; border-radius: 9999px; font-weight: 700; font-size: 11px; text-transform: uppercase; }}
  h1 {{ color: #0f172a; font-size: 19px; border-bottom: 2px solid #e2e8f0; padding-bottom: 6px; margin-top: 15px; margin-bottom: 12px; }}
  h2 {{ color: #1e40af; font-size: 14.5px; margin-top: 22px; margin-bottom: 10px; border-left: 4px solid #2563eb; padding-left: 10px; page-break-after: avoid; }}
  h3 {{ font-size: 13px; color: #334155; margin-top: 14px; margin-bottom: 8px; page-break-after: avoid; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12px 0; font-size: 11.5px; page-break-inside: avoid; }}
  th, td {{ border: 1px solid #e2e8f0; padding: 6px 10px; text-align: left; }}
  th {{ background: #f8fafc; color: #0f172a; font-weight: 600; border-bottom: 2px solid #cbd5e1; }}
  tr:nth-child(even) {{ background: #f8fafc; }}
  .chart-card {{ background: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 10px; margin: 16px 0; page-break-inside: avoid; text-align: center; }}
  .chart-header {{ font-weight: 600; font-size: 12px; color: #334155; margin-bottom: 8px; text-align: left; }}
  .chart-card img {{ max-width: 100%; height: auto; border-radius: 4px; display: block; margin: 0 auto; }}
  .footer-note {{ margin-top: 25px; font-size: 10px; color: #94a3b8; text-align: center; border-top: 1px solid #f1f5f9; padding-top: 8px; }}
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
    Сформировано автоматически конвейером BTC Market Intelligence | Время отчета: {iso_utc()}
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
                margin={"top": "15mm", "bottom": "15mm", "left": "15mm", "right": "15mm"},
            )
            browser.close()

        return pdf_path.exists() and pdf_path.stat().st_size > 5000
    except Exception as exc:
        print(f"[WARN] Playwright вернул исключение: {exc}")
        return False


def export_report_to_pdf(report_md: str, pdf_path: Path, screenshots: Optional[list[dict]] = None) -> bool:
    if sync_playwright is not None and markdown is not None:
        try:
            if export_report_to_pdf_playwright(report_md, pdf_path, screenshots):
                return True
        except Exception:
            pass
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
            candles.append([
                now_ms - (80 - i) * 3_600_000, str(op), str(high), str(low), str(close), "100",
                now_ms - (79 - i) * 3_600_000, str(5_000_000 + i * 1000), 100, "60", "40", "0",
            ])
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

        now = time.time()
        history = [{"timestamp": (now - 3600) * 1000, "sumOpenInterest": "100"}]
        oi_valid = nearest_oi_change(history, 105, 1)
        assert oi_valid.get("available") and oi_valid.get("change_pct") == 5.0
        history_too_recent = [{"timestamp": (now - 3600 * 0.4) * 1000, "sumOpenInterest": "100"}]
        oi_invalid = nearest_oi_change(history_too_recent, 105, 1)
        assert oi_invalid.get("available") is False
        checks.append("OI strict horizon validation")

        z = calculate_zscore(10.0, [5.0, 5.0, 5.0, 10.0, 5.0])
        assert z is not None and z > 0
        z_neg = calculate_zscore(0.0, [5.0, 6.0, 4.0, 5.5, 4.5])
        assert z_neg is not None and z_neg < 0
        z_zero = calculate_zscore(5.0, [5.0, 5.0, 5.0, 5.0])
        assert z_zero == 0.0
        checks.append("calculate_zscore: positive, negative, and zero std cases")

        mock_metrics = {
            "market_structure": {"1d": {"close_vs_rolling_vwap20_pct": 1.5}},
            "spot_taker_delta": {"24h": {"delta_btc": 500.0}},
            "orderbook_depth": {
                "spot": {"bid_vs_ask_ratio": 1.3},
                "futures": {"bid_vs_ask_ratio": 1.2},
            },
            "divergence_engine": {"24h_divergence": {"bias_contribution": 15}},
            "statistical_z_scores": {"oi_zscore": 1.0},
            "derivatives": {"current_funding_rate_pct": 0.001},
        }
        bias = calculate_quant_bias(mock_metrics)
        assert bias["composite_score"] == 66, f"Expected 66, got {bias['composite_score']}"
        assert bias["bias_label"] == "STRONG BULLISH"
        checks.append("calculate_quant_bias: scoring and label correctness")

        risk_long = calculate_atr_risk_levels(80000.0, 500.0, 30)
        assert risk_long["direction"] == "LONG"
        assert risk_long["buffer"] == 750.0
        assert risk_long["long"]["stop_loss"] == 79250.0
        assert risk_long["long"]["tp1_rr2"] == 81500.0
        assert risk_long["long"]["tp2_rr3"] == 82250.0
        assert risk_long["recommended"]["scenario"] == "LONG"
        assert risk_long["recommended"]["direction"] == "LONG"
        assert risk_long["recommended"]["tp1"] == 81500.0
        assert risk_long["recommended"]["tp2"] == 82250.0
        checks.append("calculate_atr_risk_levels: unified schema & dynamic R:R 1:2 and 1:3")

        mock_fast_snap = run_fast_momentum_scan(quiet=True, mock=True)
        assert mock_fast_snap["execution_mode"] == "FAST_MOMENTUM_SCAN"
        assert mock_fast_snap["spot_price"] > 0
        assert "ai_telemetry" in mock_fast_snap
        checks.append("run_fast_momentum_scan: offline mock execution flow and schema")

        print("SELF-TEST: PASS")
        for item in checks:
            print(f"  [PASS] {item}")
        return 0
    except Exception as exc:
        print(f"SELF-TEST: FAIL — {exc}")
        return 1


# ------------------------------- ОСНОВНОЙ ПАЙПЛАЙН --------------------------

def main() -> int:
    started = time.time()
    print("=== ЗАПУСК BTC MARKET INTELLIGENCE V4.2 (FREE DATA) ===")
    statuses = {}
    try:
        binance, binance_statuses = fetch_binance_telemetry()
        statuses.update(binance_statuses)
    except DataIntegrityError as exc:
        print(f"[FATAL] Критический сбой данных: {exc}")
        return 2

    bybit = fetch_bybit_telemetry()
    statuses["bybit_public_data"] = status_record(bybit.get("status") == "OK", "Bybit public V5 market data")

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
    statuses["btc_spot_etf_flows"] = status_record(etf_flows.get("status") == "OK", "Farside Investors daily net flow table")

    options = fetch_deribit_options()
    statuses["deribit_options"] = status_record(options.get("status") == "OK", "Deribit public options summary")

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
    screenshots.extend([
        x for x in free_dashboard_screenshots
        if x.get("status") == "CAPTURED_PAGE_REQUIRES_VISUAL_VALIDATION" and x.get("path") and Path(x["path"]).exists()
    ])
    captured_dashboard_count = sum(1 for x in free_dashboard_screenshots if x.get("status") == "CAPTURED_PAGE_REQUIRES_VISUAL_VALIDATION")
    statuses["free_dashboard_screenshots"] = status_record(
        captured_dashboard_count > 0,
        f"Captured {captured_dashboard_count}/{len(FREE_DASHBOARD_PAGES)} dashboards",
    )
    heatmap_page_check_passed = any(str(x.get("semantic_check", "")).startswith("PASS:") for x in screenshots[:coinglass_screenshot_count])
    statuses["coinglass_screenshot"] = status_record(
        heatmap_page_check_passed,
        f"CoinGlass heatmap page checks passed={heatmap_page_check_passed}",
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
        "ai_telemetry": get_ai_telemetry(),
        "spot_price": spot_p,
        "prices": binance.get("prices", {}),
        "statistical_z_scores": binance.get("statistical_z_scores", {}),
        "spot_taker_delta": binance.get("spot_taker_delta", {}),
        "quant_bias": binance.get("quant_bias", {}),
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

    print("\n" + "=" * 70)
    print("  ДИНАМИЧЕСКАЯ МОДЕЛЬ РИСКА (ATR) И ON-CHAIN МЕТРИКИ")
    print("=" * 70)
    rec = risk_model.get("recommended", {})
    spot_val = binance.get("prices", {}).get("spot_last", 0.0)
    atr_val = risk_model.get("atr14", 0.0)
    rec_dir = rec.get("direction") or rec.get("scenario", "NEUTRAL")
    rec_tp1 = rec.get("tp1_rr2") or rec.get("tp1", 0.0)
    rec_tp2 = rec.get("tp2_rr3") or rec.get("tp2", 0.0)
    print(f"  BTC Spot: ${spot_val:,.2f} | 4h ATR14: ${atr_val:,.2f}")
    print(f"  Рекомендация: {rec_dir}")
    print(f"  Stop-Loss:   ${rec.get('stop_loss', 0.0):,.2f} (1.5x ATR buffer)")
    print(f"  TP1 (1:2):   ${rec_tp1:,.2f}")
    print(f"  TP2 (1:3):   ${rec_tp2:,.2f}")
    if onchain.get("status") == "OK":
        print(f"  MVRV Z-Score: {onchain.get('mvrv_zscore')} [{onchain.get('mvrv_stage', 'N/A')}]")
        print(f"  NUPL:         {onchain.get('nupl')} [{onchain.get('nupl_stage', 'N/A')}]")
    print("=" * 70 + "\n")

    try:
        api_key = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip()
        if not api_key:
            payload["ai_telemetry"] = get_ai_telemetry(last_status="STANDBY_NO_KEY")
            raise RuntimeError("структурированный расчет по формулам (ключ GEMINI_API_KEY не задан)")
        report = run_gemini_synthesis(payload, screenshots)
    except Exception as exc:
        if os.getenv("GEMINI_API_KEY", GEMINI_API_KEY).strip():
            print(f"[WARN] Сбой синтеза Gemini: {exc}")
        else:
            print("[*] Формирование квантового отчета (математический расчет)...")
        report = fallback_report(payload, str(exc))

    payload["run_finished_at_utc"] = iso_utc()
    atomic_write_json(RAW_SNAPSHOT_FILE, payload)
    report += f"\n\n---\n*Сформировано: {iso_utc()} | Модель: {payload.get('ai_telemetry', {}).get('active_model', DEFAULT_GEMINI_MODEL)} | Время выполнения: {time.time() - started:.1f}с*\n"

    atomic_write_text(OUTPUT_REPORT_FILE, report)
    save_snapshot(binance, history)

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
        print("BTC Market Intelligence v4.2 (Free Data Pipeline)")
        print("Использование: python btc_market_intelligence.py [--fast] [--self-test] [--model <name>] [--help]")
        print("  --fast                Быстрое REST-сканирование (<5.0 сек, без Playwright/браузера)")
        print("  --self-test           Запуск автономных локальных тестов без сетевых вызовов")
        print("  --model <model_name>  Выбор модели ИИ (gemini-3.8-flash или gemini-3.7-flash)")
        print("  --help, -h            Вывод справки")
        sys.exit(0)

    args = sys.argv[1:]
    filtered_args = []
    idx = 0
    while idx < len(args):
        if args[idx] == "--model" and idx + 1 < len(args):
            set_configured_gemini_model(args[idx + 1])
            idx += 2
        elif args[idx].startswith("--model="):
            set_configured_gemini_model(args[idx].split("=", 1)[1])
            idx += 1
        else:
            filtered_args.append(args[idx])
            idx += 1

    valid_flags = {"--fast", "--self-test", "--help", "-h"}
    unrecognized = [arg for arg in filtered_args if arg not in valid_flags]
    if unrecognized:
        print(f"Error: unrecognized argument(s): {', '.join(unrecognized)}", file=sys.stderr)
        sys.exit(2)

    if "--self-test" in filtered_args:
        raise SystemExit(run_self_tests())
    if "--fast" in filtered_args:
        res = run_fast_momentum_scan()
        sys.exit(0 if res.get("spot_price") else 1)
    raise SystemExit(main())