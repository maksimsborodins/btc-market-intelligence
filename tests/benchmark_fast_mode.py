"""
Empirical Benchmark Harness for Fast Mode Latency & Stability Stress Test
btc_market_intelligence project - Challenger 1 Track

Executes repeated CLI fast momentum scans, collects latency distributions,
validates output snapshot and tracker integrity after every run, and
outputs a detailed performance report.
"""

import sys
import time
import json
import statistics
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PYTHON_EXE = sys.executable
CLI_SCRIPT = PROJECT_ROOT / "btc_market_intelligence.py"
SNAPSHOT_FILE = PROJECT_ROOT / "market_snapshot.json"
TRACKER_FILE = PROJECT_ROOT / "quant_calibration_tracker.json"


def run_benchmark(num_runs: int = 10) -> dict:
    print(f"================================================================")
    print(f"Starting Fast Mode Stress Benchmark: {num_runs} consecutive runs")
    print(f"Hard Requirement: Latency < 5.0 seconds per run")
    print(f"================================================================")

    latencies = []
    internal_times = []
    exit_codes = []
    snapshot_checks = []
    tracker_checks = []

    for i in range(1, num_runs + 1):
        print(f"\n--- Run {i}/{num_runs} ---")
        t0 = time.time()
        
        proc = subprocess.run(
            [PYTHON_EXE, str(CLI_SCRIPT), "--fast"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15.0,
        )
        wall_time = time.time() - t0
        latencies.append(wall_time)
        exit_codes.append(proc.returncode)

        print(f"Exit code: {proc.returncode} | Wall-clock: {wall_time:.3f}s")
        if wall_time >= 5.0:
            print(f"[VIOLATION] Run {i} exceeded 5.0s limit! ({wall_time:.3f}s)")
        else:
            print(f"[PASS] Run {i} completed within budget (< 5.0s)")

        # Verify Snapshot integrity
        snap_ok = False
        internal_time = None
        if SNAPSHOT_FILE.exists():
            try:
                snap_data = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
                internal_time = snap_data.get("execution_time_sec")
                if internal_time is not None:
                    internal_times.append(internal_time)
                # Check critical keys
                if "execution_mode" in snap_data and "spot_price" in snap_data and "risk_model" in snap_data:
                    snap_ok = True
            except Exception as e:
                print(f"[FAIL] Snapshot JSON read error: {e}")
        snapshot_checks.append(snap_ok)

        # Verify Tracker integrity
        track_ok = False
        if TRACKER_FILE.exists():
            try:
                track_data = json.loads(TRACKER_FILE.read_text(encoding="utf-8"))
                if isinstance(track_data, list):
                    track_ok = True
            except Exception as e:
                print(f"[FAIL] Tracker JSON read error: {e}")
        tracker_checks.append(track_ok)

        time.sleep(0.5)  # brief pause between runs

    # Statistical computation
    min_lat = min(latencies)
    max_lat = max(latencies)
    mean_lat = statistics.mean(latencies)
    median_lat = statistics.median(latencies)
    stdev_lat = statistics.stdev(latencies) if len(latencies) > 1 else 0.0
    sorted_lat = sorted(latencies)
    p95_idx = int(0.95 * len(sorted_lat)) - 1
    p95_lat = sorted_lat[max(0, p95_idx)]

    violations = [t for t in latencies if t >= 5.0]

    report = {
        "num_runs": num_runs,
        "exit_codes": exit_codes,
        "all_zero_exit": all(c == 0 for c in exit_codes),
        "wall_latencies": [round(t, 3) for t in latencies],
        "min_latency_sec": round(min_lat, 3),
        "max_latency_sec": round(max_lat, 3),
        "mean_latency_sec": round(mean_lat, 3),
        "median_latency_sec": round(median_lat, 3),
        "stdev_latency_sec": round(stdev_lat, 3),
        "p95_latency_sec": round(p95_lat, 3),
        "internal_reported_mean_sec": round(statistics.mean(internal_times), 3) if internal_times else None,
        "violations_count": len(violations),
        "violation_details": violations,
        "snapshot_validity_all_pass": all(snapshot_checks),
        "tracker_validity_all_pass": all(tracker_checks),
    }

    print("\n================================================================")
    print("BENCHMARK SUMMARY RESULTS:")
    print(f"Total runs: {num_runs}")
    print(f"All runs exited 0: {report['all_zero_exit']}")
    print(f"Min latency: {min_lat:.3f}s")
    print(f"Mean latency: {mean_lat:.3f}s")
    print(f"Median latency: {median_lat:.3f}s")
    print(f"P95 latency: {p95_lat:.3f}s")
    print(f"Max latency: {max_lat:.3f}s")
    print(f"Standard deviation: {stdev_lat:.3f}s")
    print(f"Violations (>= 5.0s): {len(violations)} / {num_runs}")
    print(f"Snapshot integrity: {'100% PASS' if report['snapshot_validity_all_pass'] else 'FAIL'}")
    print(f"Tracker integrity: {'100% PASS' if report['tracker_validity_all_pass'] else 'FAIL'}")
    print("================================================================")

    return report


if __name__ == "__main__":
    runs = 10
    if len(sys.argv) > 1:
        try:
            runs = int(sys.argv[1])
        except ValueError:
            pass
    res = run_benchmark(runs)
    with open(PROJECT_ROOT / "benchmark_results.json", "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)
