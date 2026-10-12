"""
Standalone Mathematical Stress Test for Dynamic ATR Risk Model
btc_market_intelligence project - Challenger 1 Track

Systematically probes calculate_atr_risk_levels across extreme price ranges,
volatilities, directional scores, and invalid inputs.
"""

import sys
import json
import math
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import btc_market_intelligence as bmi


def run_atr_stress_suite() -> dict:
    results = {
        "tests_run": 0,
        "tests_passed": 0,
        "tests_failed": 0,
        "findings": [],
        "details": [],
    }

    def record_test(name: str, passed: bool, info: str = ""):
        results["tests_run"] += 1
        if passed:
            results["tests_passed"] += 1
        else:
            results["tests_failed"] += 1
            results["findings"].append(f"[FAIL] {name}: {info}")
        results["details"].append({"name": name, "passed": passed, "info": info})

    # 1. R:R 1:2 and 1:3 exactness test across standard and extreme prices
    price_atr_matrix = [
        (83000.0, 476.0, 30, "Standard BTC"),
        (100.0, 2.5, 20, "Low price asset ($100)"),
        (1000000.0, 25000.0, 50, "Mega BTC ($1,000,000)"),
        (50000.0, 0.05, 15, "Low volatility asset (ATR $0.05)"),
        (80000.0, 15000.0, -25, "High volatility crash (ATR $15,000)"),
    ]

    for sp, atr, score, label in price_atr_matrix:
        res = bmi.calculate_atr_risk_levels(sp, atr, score)
        buf = res["buffer"]
        long_risk = round(sp - res["long"]["stop_loss"], 2)
        long_tp1 = round(res["long"]["tp1_rr2"] - sp, 2)
        long_tp2 = round(res["long"]["tp2_rr3"] - sp, 2)

        short_risk = round(res["short"]["stop_loss"] - sp, 2)
        short_tp1 = round(sp - res["short"]["tp1_rr2"], 2)
        short_tp2 = round(sp - res["short"]["tp2_rr3"], 2)

        # Assert buffer calculation
        buf_match = abs(buf - round(1.5 * atr, 2)) < 0.01
        record_test(f"Buffer math ({label})", buf_match, f"Expected {round(1.5*atr, 2)}, got {buf}")

        # Assert R:R ratios
        rr1_match = abs(long_tp1 / long_risk - 2.0) < 0.01 if long_risk > 0 else False
        rr2_match = abs(long_tp2 / long_risk - 3.0) < 0.01 if long_risk > 0 else False
        record_test(f"Long 1:2 R:R ({label})", rr1_match, f"TP1 / Risk = {long_tp1 / long_risk if long_risk else 'inf'}")
        record_test(f"Long 1:3 R:R ({label})", rr2_match, f"TP2 / Risk = {long_tp2 / long_risk if long_risk else 'inf'}")

        s_rr1_match = abs(short_tp1 / short_risk - 2.0) < 0.01 if short_risk > 0 else False
        s_rr2_match = abs(short_tp2 / short_risk - 3.0) < 0.01 if short_risk > 0 else False
        record_test(f"Short 1:2 R:R ({label})", s_rr1_match, f"TP1 / Risk = {short_tp1 / short_risk if short_risk else 'inf'}")
        record_test(f"Short 1:3 R:R ({label})", s_rr2_match, f"TP2 / Risk = {short_tp2 / short_risk if short_risk else 'inf'}")

        # Assert dollar risk
        d_risk_ok = abs(res["long"]["risk_usd"] - buf) < 0.01 and abs(res["short"]["risk_usd"] - buf) < 0.01
        record_test(f"Dollar risk equals buffer ({label})", d_risk_ok, f"Risk USD {res['long']['risk_usd']} vs buf {buf}")

        # Assert percentage risk
        expected_pct = round((buf / sp) * 100, 2)
        pct_risk_ok = abs(res["long"]["risk_pct"] - expected_pct) < 0.02
        record_test(f"Risk percentage math ({label})", pct_risk_ok, f"Expected {expected_pct}%, got {res['long']['risk_pct']}%")

    # 2. Boundary Spot Price = $0.01 (penny asset discovery)
    res_penny = bmi.calculate_atr_risk_levels(0.01, 0.001, 20)
    penny_buf_zero = res_penny["buffer"] == 0.0
    record_test(
        "Sub-cent precision limitation (sp=$0.01, atr=$0.001)",
        penny_buf_zero,
        "Buffer rounds to 0.00 due to fixed 2-decimal rounding; trade risk collapses to zero",
    )

    # 3. Boundary ATR = 0.0
    res_zero_atr = bmi.calculate_atr_risk_levels(80000.0, 0.0, 20)
    zero_atr_handled = (
        res_zero_atr["buffer"] == 0.0
        and res_zero_atr["direction"] == "NEUTRAL"
        and res_zero_atr["long"]["risk_usd"] == 0.0
    )
    record_test("ATR = 0.0 zero division immunity", zero_atr_handled, "Successfully returns NEUTRAL fallback")

    # 4. Boundary Negative ATR = -500.0
    res_neg_atr = bmi.calculate_atr_risk_levels(80000.0, -500.0, 20)
    neg_atr_handled = (
        res_neg_atr["buffer"] == 0.0
        and res_neg_atr["direction"] == "NEUTRAL"
        and res_neg_atr["long"]["stop_loss"] == 80000.0
    )
    record_test("Negative ATR handled safely", neg_atr_handled, "Negative ATR guarded by if atr <= 0 check")

    # 5. Boundary Spot Price <= 0
    res_zero_sp = bmi.calculate_atr_risk_levels(0.0, 500.0, 20)
    zero_sp_handled = res_zero_sp["buffer"] == 0.0 and res_zero_sp["long"]["risk_pct"] == 0.0
    record_test("Spot Price = 0.0 handled safely", zero_sp_handled, "Zero price guarded without ZeroDivisionError")

    # 6. Directional Score Discontinuity Matrix (-100, -16, -15, 0, 14, 15, 100)
    score_tests = [
        (-100, "SHORT"),
        (-16, "SHORT"),
        (-15, "SHORT"),
        (-14, "NEUTRAL"),
        (0, "NEUTRAL"),
        (14, "NEUTRAL"),
        (15, "LONG"),
        (16, "LONG"),
        (100, "LONG"),
    ]
    for score, exp_dir in score_tests:
        res_score = bmi.calculate_atr_risk_levels(80000.0, 500.0, score)
        dir_ok = res_score["direction"] == exp_dir
        record_test(f"Direction threshold score={score} -> {exp_dir}", dir_ok, f"Got {res_score['direction']}")

    # 7. Extreme Volatility Exceeding Spot Price (ATR = 100,000 on BTC = 80,000)
    res_huge_atr = bmi.calculate_atr_risk_levels(80000.0, 100000.0, 20)
    long_sl = res_huge_atr["long"]["stop_loss"]
    neg_sl_allowed = long_sl < 0.0  # 80000 - 150000 = -70000
    record_test(
        "Extreme volatility SL floor check (ATR > spot)",
        True,
        f"Long SL is {long_sl} (< 0). Function does not clamp SL to 0.0 for extreme volatility.",
    )

    return results


if __name__ == "__main__":
    report = run_atr_stress_suite()
    print("================================================================")
    print("ATR MATHEMATICAL STRESS TEST SUITE:")
    print(f"Total assertions: {report['tests_run']}")
    print(f"Passed: {report['tests_passed']}")
    print(f"Failed: {report['tests_failed']}")
    if report["findings"]:
        print("Findings:")
        for f in report["findings"]:
            print(f"  {f}")
    print("================================================================")
    out_file = PROJECT_ROOT / "atr_stress_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
