# E2E Test Infra: BTC Market Intelligence Terminal

## Test Philosophy
- Opaque-box, requirement-driven, derived strictly from `ORIGINAL_REQUEST.md`.
- No dependence on internal implementation details.
- Progressive testability: verification operates via CLI invocation, exit codes, file existence, and output schema assertions.
- Methodology: 4-Tier Test Architecture (Category-Partition + BVA + Pairwise + Real-World Workload).

## Feature Inventory Mapping
| # | Feature | Source (Requirement) | Tier 1 | Tier 2 | Tier 3 | Tier 4 |
|---|---------|---------------------|:------:|:------:|:------:|:------:|
| 1 | Fast Mode CLI (`--fast`) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 2 | Parallel REST Ingestion & Latency (<5s) | ORIGINAL_REQUEST §R2 | 5 | 5 | ✓ | ✓ |
| 3 | On-chain Metrics (MVRV & NUPL) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 4 | Dynamic ATR Risk Model (SL & 1:2 / 1:3 TP) | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 5 | Winrate Calibration Tracker | ORIGINAL_REQUEST §R3 | 5 | 5 | ✓ | ✓ |
| 6 | Streamlit Dashboard File & Syntax (`dashboard.py`) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 7 | Dashboard Visuals (Gauge, Charts, PDF/MD) | ORIGINAL_REQUEST §R1 | 5 | 5 | ✓ | ✓ |
| 8 | 1-Click Execution & Launcher (`run_dashboard.bat`) | ORIGINAL_REQUEST §R1, §R4 | 5 | 5 | ✓ | ✓ |
| 9 | Backward Compatibility & Self-Tests (`--self-test`) | ORIGINAL_REQUEST §R4 | 5 | 5 | ✓ | ✓ |

## Test Architecture
- Test runner: Python `unittest` / `pytest` runner invoked via `python -m unittest discover -s tests -p "test_*.py"`.
- Test case format: Standard Python test classes inheriting `unittest.TestCase`.
- Directory layout:
  * `tests/`
    - `__init__.py`
    - `test_tier1_features.py`: Independent happy-path validation for all features.
    - `test_tier2_boundaries.py`: Boundary and corner cases (empty files, corrupted data, extreme ATR, timeout resilience, rate limits).
    - `test_tier3_combinations.py`: Cross-feature combinations (Fast mode + ATR risk output + tracker update; Dashboard data hydration with missing files; CLI flag combinations).
    - `test_tier4_workloads.py`: End-to-end realistic user scenarios (cold start, repeated 1-click executions, calibration cycle over time, report generation).

## Coverage Thresholds
- Identified Features: N = 9 distinct feature domains.
- Tier 1: ≥5 test cases per feature (≥45 tests).
- Tier 2: ≥5 test cases per feature (≥45 tests).
- Tier 3: ≥9 test cases covering major feature interactions.
- Tier 4: ≥5 realistic application scenarios.
- **Total Minimum Target: ~104+ test cases**.
