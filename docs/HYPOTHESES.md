# Hypothesis protocol and round 1 (draft, waiting for the user's confirmation)

Exploratory screening (research.py, 1000 tests) found no directional edge in OI, taker flow, premium, funding or
long/short ratios on 1–48 h. From here every test is a pre-registered hypothesis, fixed in this file before it runs.

## Protocol

1. **Fixed before the run:** condition, horizon, outcome, control and the predicted direction. A result in the
   opposite direction rejects the hypothesis; it is never flipped into the opposite trade.
2. **Events are onsets** (first hour the condition holds, then the horizon blocked), one trade each. The control is
   the same situation without the ingredient under test, matched on size: strata of the size variable within the
   sample (`btcmi.events.stratified_diff`), or nearest-neighbour matching with a caliper of 0.25 sigma where the
   size effect is steep (cascades). Events with no comparable control are dropped (common support).
3. **CI:** calendar-block bootstrap on the shared time axis, block >= 2x horizon (72 h for 24 h outcomes), so
   overlapping signal and control events and clustered weeks are resampled together.
4. **Acceptance (all required):**
   - one-sided t >= 2.5 in the predicted direction (Holm over the round's <= 5 hypotheses is about the same);
   - same sign in both eras, 2020-09..2023-12 and 2024-01..now, with t >= 1.5 in 2024+;
   - economically useful after the 0.12% round trip: >= +0.15% per trade for 12–24 h, >= +0.10% for 1–6 h.
   Volatility hypotheses replace the last item with a forecast-skill threshold (H1, H4).
5. Secondary variants (another threshold, another window) are reported as such and never accepted on their own.
6. Every run, rejected ones included, is kept in research/.

## Round 1 (proposed 2026-10-21)

| # | Hypothesis | Definition | Accepted when |
|---|---|---|---|
| H1 | Range forecast for the traffic light | Target log(High/Low) over the next 6 h and 24 h. Model: HAR on log range (last 1 h, 24 h, 7 d) + 2 Fourier pairs of the New York hour + share of the window in the US cash session + share on weekends + macro release (CPI/FOMC/NFP) inside the window; later + Deribit DVOL. Quantile regression tau = 0.5 and 0.3; monthly expanding refit from 365 days, training rows purged H hours before the month | Out-of-sample 2024+: MAE of log range and QLIKE at least 10% below "same as the last H hours", Diebold–Mariano with 48 h blocks t >= 2.5; tau quantiles calibrated within +-5 points |
| H2 | Long-liquidation flush reverts | Onset of a 1 h return < -2.5 sigma with 1 h OI change z < -1.5 (forced closing). Control: same-size hours (caliper 0.25 sigma) with OI change > -0.5 sigma. Up moves are a separate hypothesis | Long over the next 4 h and 12 h beats the matched control (protocol 4); confirmed by OLS y ~ flush + r + r^2 with time-clustered errors |
| H3 | US open and ETF fixing window | (a) The high or low of 16:30–17:15 Riga survives to 23:00 more often than the extreme of a random 45-min window of the session; (b) the day's 13:30–22:00 UTC move fades after the 15:00–16:00 ET fixing | (a) >= 10 points above the random-window rate, both eras; (b) protocol 4, direction: against the session move |
| H4 | Compression with high OI → bigger range | 24 h realized vol in its bottom 15% (90-day window) and OI z in the top 15% | Next 24 h range >= 1.2x the range after the same compression with OI z in the middle 50%, CI of the ratio above 1, both eras |
| H5 | Macro release ranges | CPI, FOMC, NFP since 2021: range in the 1 h and 4 h after the release vs the same hour on non-release days; split by OI z above / below 1 | Descriptive (dashboard calendar numbers); a direction claim only if it passes protocol 4 |

Traffic-light thresholds are not fitted on returns: minimum stop = cost / max share of risk the cost may take
(0.12% / 15% = 0.8%), and the range a trade needs follows from the user's stop and target. The user's real stop
widths and order types are needed to fix them.
