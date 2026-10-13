"""
BTC Market Intelligence — Telegram Alert & Signal Dispatcher (v5.0)
Sends real-time institutional market alerts, volatility spikes, and PDF reports.
"""

import json
import os
import sys
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def is_telegram_configured() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def send_telegram_message(text: str, parse_mode: str = "HTML") -> bool:
    """Отправка текстового сообщения в Telegram."""
    if not is_telegram_configured():
        print("[WARN] TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID не заданы; уведомление пропущено.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            return True
        print(f"[!] Сбой отправки Telegram: HTTP {resp.status_code} — {resp.text}")
    except Exception as exc:
        print(f"[!] Исключение при отправке в Telegram: {exc}")
    return False


def send_telegram_document(document_path: Path, caption: str = "") -> bool:
    """Отправка файла (например, PDF-отчета) в Telegram."""
    if not is_telegram_configured():
        return False
    if not document_path.exists():
        print(f"[!] Файл для отправки не найден: {document_path}")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendDocument"
    try:
        with open(document_path, "rb") as f:
            files = {"document": f}
            data = {"chat_id": TELEGRAM_CHAT_ID, "caption": caption, "parse_mode": "HTML"}
            resp = requests.post(url, data=data, files=files, timeout=30)
            return resp.status_code == 200
    except Exception as exc:
        print(f"[!] Сбой отправки документа в Telegram: {exc}")
        return False


def format_signal_alert(snapshot: dict) -> str:
    """Форматирует институциональное оповещение по снимку рынка."""
    spot = snapshot.get("spot_price") or snapshot.get("prices", {}).get("spot_last", 0.0)
    quant = snapshot.get("quant_bias", {})
    score = quant.get("composite_score", 0)
    label = quant.get("bias_label", "NEUTRAL")
    
    risk = snapshot.get("risk_model") or snapshot.get("atr_risk", {})
    rec = risk.get("recommended", {})
    direction = rec.get("direction", "NEUTRAL")
    sl = rec.get("stop_loss", 0.0)
    tp1 = rec.get("tp1_rr2") or rec.get("tp1", 0.0)
    tp2 = rec.get("tp2_rr3") or rec.get("tp2", 0.0)

    divergence = snapshot.get("binance", {}).get("divergence_engine", {}).get("24h_divergence", {}).get("divergence_state", "N/A")
    dvol = snapshot.get("deribit_dvol", {}).get("current_dvol", "N/A")
    cb = snapshot.get("coinbase_orderbook", {})
    cb_ratio = cb.get("bid_vs_ask_ratio", "N/A")

    emoji_signal = "🟢 <b>BULLISH SIGNAL</b>" if "BULL" in label else ("🔴 <b>BEARISH SIGNAL</b>" if "BEAR" in label else "⚪ <b>NEUTRAL MARKET PULSE</b>")

    lines = [
        f"⚡ <b>BTC MARKET INTELLIGENCE TERMINAL</b> ⚡",
        f"{emoji_signal}",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"💰 <b>Цена BTC Spot:</b> ${spot:,.2f}",
        f"📊 <b>Композитный скор:</b> <code>{score:+d}</code> ({label})",
        f"📈 <b>Дивергенция 24h:</b> {divergence}",
        f"🌊 <b>Coinbase L2 Bid/Ask:</b> {cb_ratio}x",
        f"🌪 <b>Deribit DVOL:</b> {dvol} pts",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>РИСК-МОДЕЛЬ ATR (R:R 1:2 / 1:3):</b>",
        f"• Направление: <b>{direction}</b>",
        f"• Stop-Loss (1.5x ATR): ${sl:,.2f}",
        f"• Take-Profit 1 (1:2):  ${tp1:,.2f}",
        f"• Take-Profit 2 (1:3):  ${tp2:,.2f}",
        f"━━━━━━━━━━━━━━━━━━━━━",
        f"🕒 <i>Время: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}</i>",
    ]
    return "\n".join(lines)


def check_and_dispatch_alerts(snapshot: dict, tracker_file: Optional[Path] = None) -> bool:
    """
    Проверяет снимок на критические события и отправляет алерт при их обнаружении.
    """
    if not is_telegram_configured():
        return False

    quant = snapshot.get("quant_bias", {})
    score = abs(quant.get("composite_score", 0))

    # Отправляем алерт при сильном направленном сигнале (|score| >= 25)
    if score >= 25:
        msg = format_signal_alert(snapshot)
        return send_telegram_message(msg)
    return False


if __name__ == "__main__":
    if "--test" in sys.argv:
        print("[*] Тестовый запуск модуля Telegram...")
        if is_telegram_configured():
            mock_snap = {
                "spot_price": 83450.0,
                "quant_bias": {"composite_score": 35, "bias_label": "BULLISH"},
                "risk_model": {
                    "recommended": {
                        "direction": "LONG",
                        "stop_loss": 82600.0,
                        "tp1_rr2": 85150.0,
                        "tp2_rr3": 86000.0,
                    }
                },
                "binance": {
                    "divergence_engine": {
                        "24h_divergence": {"divergence_state": "Bullish Continuation"}
                    }
                },
                "deribit_dvol": {"current_dvol": 52.4},
                "coinbase_orderbook": {"bid_vs_ask_ratio": 1.35},
            }
            alert_text = format_signal_alert(mock_snap)
            print("Сформированное сообщение:")
            print(alert_text)
            ok = send_telegram_message(alert_text)
            print(f"Статус отправки: {'УСПЕХ' if ok else 'ОШИБКА'}")
        else:
            print("[INFO] Telegram не сконфигурирован. Задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID для активации.")
