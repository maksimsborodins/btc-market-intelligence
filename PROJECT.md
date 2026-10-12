# Project: BTC Market Intelligence Terminal

## Architecture
The system consists of three primary architectural layers:
1. **Core Analytical Engine (`btc_market_intelligence.py`)**:
   - Data Ingestion Layer: Binance Spot & Futures REST API, Bybit REST API, Macro, On-chain (BGeometrics REST for MVRV Z-Score & NUPL, LookIntoBitcoin visual scrapers).
   - Quantitative & Risk Layer: Quant Bias composite scoring (-100 to +100), statistical Z-scores (OI, Funding), Orderbook imbalance, CVD taker delta, dynamic ATR risk model (SL, 1:2 TP1, 1:3 TP2 for Long/Short).
   - Execution Pipelines:
     * Full Mode (`python btc_market_intelligence.py`): Ingestion -> Scrapers (Playwright) -> Analysis -> AI Synthesis (Gemini) -> Markdown report -> PDF generation (`daily_report.pdf`) -> Tracker update.
     * Fast Mode (`python btc_market_intelligence.py --fast`): Parallel REST-only ingestion (<3s) -> Quant Bias & ATR Risk -> Console display & JSON snapshot update -> Tracker update (<5s total, no Playwright). Verified execution time: 2.87s.
     * Verification Mode (`python btc_market_intelligence.py --self-test`): Offline unit tests validating math, parsing, risk models, tracker logic, mock fast mode. 13/13 suites passing offline with exit code 0.
2. **Interactive Web Dashboard (`dashboard.py`)**:
   - Built on Streamlit and Plotly.
   - Interactive components:
     * Quant Bias Speedometer gauge (-100 to +100) and horizontal factor breakdown.
     * Interactive charts: Price with ATR levels, multi-timeframe CVD delta, OI & Funding Z-score history.
     * 1-Click execution panel: Subprocess runner triggering Full Analysis or Fast Momentum Scan with real-time log streaming.
     * Document & Media viewer: Base64 embedded PDF viewer (`daily_report.pdf`), styled Markdown viewer, screenshot gallery.
     * Winrate Calibration table: KPI summary cards, historical signals, WIN/LOSS outcomes.
3. **Runners & Launcher Scripts**:
   - `run_dashboard.bat`: Windows 1-click batch launcher verifying Python environment, dependencies, and launching Streamlit.
   - `requirements.txt`: Project dependencies specification.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Fast Mode CLI (`--fast`) | CLI argument and execution flow bypassing Playwright and slow scrapers | M1 | ORIGINAL_REQUEST §R2 |
| 2 | Parallel REST Ingestion | Parallelized multi-threaded fetching of Binance & Bybit endpoints under 3s | M1 | ORIGINAL_REQUEST §R2 |
| 3 | On-chain REST Metrics | MVRV Z-Score & NUPL data fetching via fast REST API (~300ms) with cycle stage categorization | M1 | ORIGINAL_REQUEST §R3 |
| 4 | Dynamic ATR Risk Model | ATR14 computation, dynamic Stop-Loss (1.5x ATR buffer), and 1:2 / 1:3 R:R targets for Long and Short | M1 | ORIGINAL_REQUEST §R3 |
| 5 | Risk Model Report Integration | Presentation of ATR risk levels in CLI output, Markdown report, and JSON data structures | M1 | ORIGINAL_REQUEST §R3 |
| 6 | Winrate Calibration Tracker Maintenance | Upgraded schema in `quant_calibration_tracker.json` with direction, SL, TP levels, PnL %, and win/loss evaluation | M1 | ORIGINAL_REQUEST §R3 |
| 7 | Self-Test Suite Expansion | Expanding `python btc_market_intelligence.py --self-test` to test ATR risk math, fast scan mock, tracker upgrades, and onchain | M1 | ORIGINAL_REQUEST §R4 |
| 8 | Backward Compatibility | Ensuring default `python btc_market_intelligence.py` continues working without regressions | M1 | ORIGINAL_REQUEST §R4 |
| 9 | Streamlit Dashboard Layout (`dashboard.py`) | Multi-tab local web UI structure with KPI ribbon, sidebar, and status indicators | M2 | ORIGINAL_REQUEST §R1 |
| 10 | Quant Bias Speedometer & Factor Breakdown | Plotly gauge chart (-100 to +100) with 5 semantic zones and horizontal factor contribution chart | M2 | ORIGINAL_REQUEST §R1 |
| 11 | Interactive Charts | Plotly charts for Price with ATR bands, CVD taker delta across intervals, and OI/Funding Z-Score history | M2 | ORIGINAL_REQUEST §R1 |
| 12 | 1-Click Analysis Runner | Subprocess execution engine for Full and Fast runs with live log streaming and auto-refresh | M2 | ORIGINAL_REQUEST §R1 |
| 13 | In-app Report & PDF Viewer | Embedded Base64 iframe for `daily_report.pdf` and styled viewer for `daily_report.md` | M2 | ORIGINAL_REQUEST §R1 |
| 14 | Calibration Table UI | Display calibration tracker data with winrate metrics, status badges, and trade history | M2 | ORIGINAL_REQUEST §R1 |
| 15 | Windows 1-Click Launcher (`run_dashboard.bat`) | Resilient batch script detecting Python, checking dependencies, and launching dashboard | M2 | ORIGINAL_REQUEST §R4 |
| 16 | Dependency Management | Updating `requirements.txt` with Streamlit, Plotly, Pandas without breaking existing libraries | M2 | ORIGINAL_REQUEST §R4 |
| 17 | E2E Test Suite Validation | 100% pass of Tiers 1-4 tests covering CLI, Fast mode, Risk math, UI files, self-tests | M3 | ORIGINAL_REQUEST §Acceptance Criteria |
| 18 | Adversarial Coverage Hardening | White-box stress testing and edge-case validation (Tier 5) | M3 | Project Pattern Phase 2 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Core Analytical Engine (`btc_market_intelligence.py`) | Implement `--fast` CLI flag, parallel REST ingestion (<3s), on-chain REST metrics, ATR dynamic risk model (SL, TP1, TP2), tracker upgrade, and `--self-test` assertions | none | DONE |
| M2 | Streamlit Web Dashboard & Launcher (`dashboard.py`, `run_dashboard.bat`) | Implement `dashboard.py` (gauge, breakdown, charts, 1-click subprocess runner, PDF/MD viewer, tracker table), `run_dashboard.bat`, and `requirements.txt` | M1 | IN_PROGRESS |
| M3 | Final Milestone: 100% E2E Test Pass & Adversarial Hardening | Pass 100% of E2E tests (Tiers 1-4), adversarial stress-testing (Tier 5), forensic audit check | M2, TEST_READY | PLANNED |

## Interface Contracts

### `btc_market_intelligence.py` ↔ Consumers (CLI / Dashboard / Tests)
- `calculate_atr_risk_levels(spot_price: float, atr14: float, quant_bias_score: int) -> dict`:
  Returns:
  ```python
  {
      "atr14": float,
      "buffer": float,  # 1.5 * atr14
      "direction": "LONG" | "SHORT" | "NEUTRAL",
      "entry_price": float,
      "long": {
          "stop_loss": float,
          "tp1_rr2": float,
          "tp2_rr3": float,
          "risk_usd": float,
          "risk_pct": float
      },
      "short": {
          "stop_loss": float,
          "tp1_rr2": float,
          "tp2_rr3": float,
          "risk_usd": float,
          "risk_pct": float
      },
      "recommended": {
          "scenario": "LONG" | "SHORT" | "NEUTRAL",
          "stop_loss": float,
          "tp1_rr2": float,
          "tp2_rr3": float
      }
  }
  ```
- `fetch_onchain_metrics(session: requests.Session = None) -> dict`:
  Returns:
  ```python
  {
      "mvrv_zscore": float | None,
      "mvrv_stage": str,  # e.g., "Fair Value / Mid Cycle"
      "nupl": float | None,
      "nupl_stage": str,  # e.g., "Optimism / Anxiety"
      "realized_price": float | None,
      "status": "OK" | "UNAVAILABLE"
  }
  ```
- `run_fast_momentum_scan(quiet: bool = False) -> dict`:
  Returns snapshot dict containing `spot_price`, `quant_bias`, `atr_risk`, `onchain`, `execution_time_sec` (<5.0s).
- CLI Invocation:
  * `python btc_market_intelligence.py --fast`: Prints instant terminal overview and updates `market_snapshot.json` and tracker in <5s.
  * `python btc_market_intelligence.py --self-test`: Executes offline test suite, exiting 0 on PASS.
  * `python btc_market_intelligence.py`: Executes standard full run with Playwright screenshots and PDF generation.

### `dashboard.py` ↔ Data Artifacts & Subprocesses
- Input data files read on load / refresh:
  * `market_snapshot.json` (latest telemetry, quant bias, risk levels, onchain metrics)
  * `market_history.json` (time-series records for charts)
  * `quant_calibration_tracker.json` (winrate calibration signals and stats)
  * `daily_report.pdf` (latest PDF report for Base64 iframe embedding)
  * `daily_report.md` (latest Markdown report for in-app viewing)
  * `free_dashboard_screenshots/` (PNG screenshots)
- Subprocess Execution:
  * Full run: `subprocess.Popen([sys.executable, "btc_market_intelligence.py"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)`
  * Fast run: `subprocess.Popen([sys.executable, "btc_market_intelligence.py", "--fast"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)`

## Code Layout
- `btc_market_intelligence.py`: Core analytical engine, data ingestion, CLI, risk calculations, self-test suite. (Owned by Milestone 1 Worker - DONE)
- `dashboard.py`: Streamlit interactive web dashboard application. (Owned by Milestone 2 Worker - IN_PROGRESS)
- `run_dashboard.bat`: Windows 1-click launcher for the dashboard. (Owned by Milestone 2 Worker - IN_PROGRESS)
- `requirements.txt`: Python package dependencies. (Owned by Milestone 2 Worker - IN_PROGRESS)
- `tests/`: Opaque-box E2E test suite (Tiers 1-4). (Owned by E2E Testing Track - DONE, 112 tests)
- `market_snapshot.json`: Current state snapshot data.
- `market_history.json`: Historical time-series data.
- `quant_calibration_tracker.json`: Winrate calibration tracker data.
- `daily_report.md`: Latest Markdown report.
- `daily_report.pdf`: Latest compiled PDF report.
- `free_dashboard_screenshots/`: Scraped market charts.
