"""
BTC Market Intelligence — Background Autonomous Daemon Engine (v5.0)
Continuously aggregates real-time market data without UI blocking or manual intervention.
Provides atomic disk snapshots, health heartbeats, and graceful process management.
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from btc_market_intelligence import run_fast_momentum_scan, RAW_SNAPSHOT_FILE, iso_utc
except ImportError:
    print("[ERROR] Не удалось импортировать btc_market_intelligence.")
    sys.exit(1)

DAEMON_STATUS_FILE = BASE_DIR / "daemon_status.json"
PID_FILE = BASE_DIR / "daemon.pid"

RUNNING = True


def handle_shutdown(signum, frame):
    global RUNNING
    print(f"\n[*] Получен сигнал завершения ({signum}). Корректная остановка демона...")
    RUNNING = False


signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)


def atomic_write_json(filepath: Path, data: dict) -> None:
    """Атомарная запись через временный файл для защиты от одновременного чтения."""
    tmp_path = filepath.with_suffix(filepath.suffix + ".tmp")
    try:
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(filepath)
    except Exception as exc:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass
        raise exc


def update_daemon_status(
    status: str,
    started_at: float,
    cycles_completed: int,
    last_cycle_sec: float,
    interval_sec: int,
    latest_snapshot: Optional[dict] = None,
    last_error: Optional[str] = None,
) -> None:
    now = time.time()
    uptime = round(now - started_at, 1)

    feeds = {}
    spot_price = 0.0
    if latest_snapshot:
        spot_price = latest_snapshot.get("spot_price") or latest_snapshot.get("prices", {}).get("spot_last", 0.0)
        binance_data = latest_snapshot.get("binance", {})
        bybit_data = latest_snapshot.get("bybit", {})
        cb_data = latest_snapshot.get("coinbase_orderbook", {})
        onchain_data = latest_snapshot.get("onchain", {})

        feeds["binance"] = "OK" if binance_data.get("prices", {}).get("spot_last") else "ERROR"
        feeds["bybit"] = bybit_data.get("status", "UNAVAILABLE")
        feeds["coinbase"] = cb_data.get("status", "UNAVAILABLE")
        feeds["onchain"] = onchain_data.get("status", "UNAVAILABLE")

    status_payload = {
        "status": status,
        "pid": os.getpid(),
        "uptime_seconds": uptime,
        "cycles_completed": cycles_completed,
        "interval_seconds": interval_sec,
        "last_cycle_duration_sec": round(last_cycle_sec, 2),
        "last_heartbeat_utc": iso_utc(),
        "spot_price": spot_price,
        "feeds": feeds,
        "last_error": last_error,
    }
    atomic_write_json(DAEMON_STATUS_FILE, status_payload)


def get_running_status() -> dict:
    if not DAEMON_STATUS_FILE.exists():
        return {"status": "STOPPED", "reason": "daemon_status.json отсутствует"}
    try:
        data = json.loads(DAEMON_STATUS_FILE.read_text(encoding="utf-8"))
        # Проверяем живость процесса по PID и времени последнего сердцебиения
        pid = data.get("pid")
        last_hb = data.get("last_heartbeat_utc")
        if last_hb:
            dt = datetime.fromisoformat(last_hb.replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - dt).total_seconds()
            data["heartbeat_age_seconds"] = round(age, 1)
            interval = data.get("interval_seconds", 20)
            if age > interval * 3:
                data["status"] = "STALE_OR_DEAD"
        return data
    except Exception as exc:
        return {"status": "ERROR", "reason": str(exc)}


def stop_daemon() -> None:
    st = get_running_status()
    pid = st.get("pid")
    if not pid:
        print("[!] Активный процесс демона не найден.")
        return
    try:
        os.kill(pid, signal.SIGTERM)
        print(f"[✓] Сигнал остановки отправлен процессу PID {pid}.")
    except Exception as exc:
        print(f"[!] Не удалось завершить процесс PID {pid}: {exc}")


def run_daemon_loop(interval_sec: int = 20, max_cycles: Optional[int] = None) -> None:
    global RUNNING
    started_at = time.time()
    cycles_completed = 0
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")

    print("=" * 65)
    print("  BTC MARKET INTELLIGENCE — АВТОНОМНЫЙ ФОНОВЫЙ ДЕМОН (v5.0)")
    print(f"  Интервал опроса: {interval_sec} сек | PID: {os.getpid()}")
    print("  Нажмите Ctrl+C для безопасного завершения")
    print("=" * 65 + "\n")

    update_daemon_status("STARTING", started_at, 0, 0.0, interval_sec)

    last_snapshot = None
    try:
        while RUNNING:
            cycle_start = time.time()
            snapshot = None
            err_msg = None

            print(f"[{iso_utc()}] Цикл #{cycles_completed + 1}: сбор телеметрии...")
            try:
                snapshot = run_fast_momentum_scan(quiet=True, mock=False)
                last_snapshot = snapshot
                cycle_duration = time.time() - cycle_start
                spot = snapshot.get("spot_price", 0.0)
                score = snapshot.get("quant_bias", {}).get("composite_score", 0)
                label = snapshot.get("quant_bias", {}).get("bias_label", "NEUTRAL")
                print(f"  [✓] Успешно за {cycle_duration:.2f}с | BTC: ${spot:,.2f} | Скор: {score} ({label})")
                cycles_completed += 1
            except Exception as exc:
                cycle_duration = time.time() - cycle_start
                err_msg = str(exc)
                print(f"  [!] Ошибка цикла #{cycles_completed + 1} ({cycle_duration:.2f}с): {exc}")

            update_daemon_status(
                status="RUNNING" if RUNNING else "STOPPED",
                started_at=started_at,
                cycles_completed=cycles_completed,
                last_cycle_sec=cycle_duration,
                interval_sec=interval_sec,
                latest_snapshot=snapshot,
                last_error=err_msg,
            )

            if max_cycles and cycles_completed >= max_cycles:
                print(f"[*] Достигнут лимит циклов ({max_cycles}). Остановка.")
                break

            # Ожидание следующего цикла с проверкой флага RUNNING каждые 0.5с
            sleep_time = max(1.0, interval_sec - cycle_duration)
            sleep_end = time.time() + sleep_time
            while RUNNING and time.time() < sleep_end:
                time.sleep(0.5)

    finally:
        update_daemon_status(
            status="STOPPED",
            started_at=started_at,
            cycles_completed=cycles_completed,
            last_cycle_sec=0.0,
            interval_sec=interval_sec,
            latest_snapshot=last_snapshot,
        )
        if PID_FILE.exists():
            try:
                PID_FILE.unlink()
            except Exception:
                pass
        print(f"\n[✓] Демон корректно остановлен. Выполнено циклов: {cycles_completed}.")


def main():
    parser = argparse.ArgumentParser(description="BTC Market Intelligence Background Daemon")
    parser.add_argument("--interval", type=int, default=20, help="Интервал обновления в секундах (по умолчанию 20)")
    parser.add_argument("--once", action="store_true", help="Выполнить один цикл и выйти")
    parser.add_argument("--status", action="store_true", help="Проверить статус работающего демона")
    parser.add_argument("--stop", action="store_true", help="Остановить работающий демон")
    parser.add_argument("--max-cycles", type=int, default=None, help="Ограничить количество циклов (для тестов)")

    args = parser.parse_args()

    if args.status:
        st = get_running_status()
        print(json.dumps(st, ensure_ascii=False, indent=2))
        sys.exit(0)

    if args.stop:
        stop_daemon()
        sys.exit(0)

    if args.once:
        run_daemon_loop(interval_sec=1, max_cycles=1)
        sys.exit(0)

    run_daemon_loop(interval_sec=args.interval, max_cycles=args.max_cycles)


if __name__ == "__main__":
    main()
