# BTC Market Intelligence: research-first rebuild

## Goal (agreed with the user 2026-10-21)

Not signals and not auto-trading: **one more factor for the user's own decisions.** The user reads the market through
the combination of **open interest + spot/futures divergence + volume** and found it informative. The system must:

1. show that picture clearly at the moment of a decision (scalp 1-12 h, intraday/swing 12-48 h);
2. test on history what each reading of the picture has meant for price afterwards (and say when it means nothing);
3. join it with the user's own trades: how the user does when the picture is with / against the trade.

Everything else the old engine computes (composite Quant Bias, ATR "trading plans", on-chain, ETF, macro, Gemini
report) is out of scope for now. On-chain/ETF can return later as slow context if it earns a place.

The existing engine (`btc_market_intelligence.py --fast`, `market_snapshot.json`) keeps working for the LifeOS
briefing until the new output replaces it.

## Why (findings of the 2026-10-20 review)

- Quant Bias is a hand-weighted sum that was never validated. Its reconstructible part (1d VWAP20 + 24h spot CVD) has
  a correlation of +0.085 with the next 24 h on one year of data, 52-55% hit rate against a 52% base, unstable between
  halves. 35 of 100 points come from a single unstored order-book snapshot.
- The calibration tracker cannot measure anything (7 signals, NEUTRAL counted as a win, "24 h" scored 52-104 h later).

## Data (history depth from the API reconnaissance, see docs/DATA_SOURCES.md)

| Series | Source | History | Use |
|---|---|---|---|
| Spot bars with taker buy volume (15m, 1h) | Binance spot | 2017-08 | price, spot volume, spot delta |
| Perp bars with taker buy volume (15m, 1h) | Binance USD-M | 2019-09 | perp volume, perp delta |
| Perp bars (1h) | Bybit linear | 2020-03 | volume (no taker split) |
| Open interest (1h) | Bybit | 2020-07 | OI, the long series |
| Open interest (5m-1h) | Binance futures/data API: 30 days; data.binance.vision daily metrics: TBD | | OI, aggregated with Bybit |
| Funding (8h) | Binance, Bybit, Deribit | 2019-2020 | positioning heat |
| Premium index (perp vs index, 1h) | Binance | TBD | basis |
| Long/short account ratio (1h) | Bybit | 2020-07 | crowd positioning |
| Coinbase BTC-USD bars (1h) | Coinbase | 2015-07 | Coinbase premium vs Binance |
| OKX OI, taker volume | OKX rubik | rolling 30 d (1h) / 180 d (1d) | forward collection only |
| Order book depth +-1% | Binance, Bybit, Coinbase | none | forward collection only (hourly) |

## Storage: `data/market.db` (SQLite, WAL, not in git)

All timestamps are UTC epoch milliseconds at bar start.

```sql
CREATE TABLE bars (
  venue TEXT, symbol TEXT, interval TEXT,           -- 'binance_spot','BTCUSDT','1h'
  ts INTEGER, open REAL, high REAL, low REAL, close REAL,
  volume REAL, quote_volume REAL, taker_buy_volume REAL, trades INTEGER,
  PRIMARY KEY (venue, symbol, interval, ts)
);
CREATE TABLE series (
  metric TEXT,          -- 'bybit.oi', 'binance.funding', 'binance.premium_index', 'book.binance_spot.bid_ask_1pct'
  ts INTEGER, value REAL,
  available_at INTEGER, -- when the value was knowable; research reads only available_at <= decision time
  PRIMARY KEY (metric, ts)
);
CREATE TABLE collector_runs (collector TEXT, started INTEGER, finished INTEGER, rows INTEGER, error TEXT);
```

Collectors are idempotent (upsert), resume from the last stored ts, page backwards where an API returns the newest
N rows, check silent caps (Bybit 200/1000, Deribit 744/1000), and log to `collector_runs`.
Runner: `python -m btcmi.collect [--backfill] [--only name]`, scheduled hourly once stable.

## The picture (features, point-in-time)

For window w in {15m, 1h, 4h, 24h}, computed only from data available at the decision time:

| Block | Features |
|---|---|
| Price | return over w, position in the 24h range |
| Open interest | OI change over w (Binance+Bybit aggregate, % and z-score vs 30 days) |
| Who leads | spot taker delta / spot volume; perp taker delta / perp volume; spot share of total volume; spot delta minus perp delta |
| Basis | perp premium vs index (level, change over w, z-score); Coinbase premium vs Binance (level, change) |
| Heat | funding (current, 3-day mean, z-score), long/short account ratio |
| Volume | total volume vs 30-day same-hour average |

**States** combine them the way the user reads the market, e.g. price up + OI up + spot delta weak = "perp-driven
rise"; price down + OI down = "long liquidation"; price up + OI down = "short covering"; price up + spot leads +
Coinbase premium positive = "spot-driven rise". The state list is a small, readable table in code; each state is
evaluated like a feature.

## Research engine (written by Opus)

For each feature and state, horizons h in {1h, 4h, 12h, 24h, 48h}:

1. Decision times: every hour (all), plus the user's sessions separately (US session 16:30-23:00 Riga).
2. Target: forward log return of Binance spot close over h; also the share of outcomes where price first moved
   1 ATR(1h) in the predicted direction before 1 ATR against (closer to how a trade is managed).
3. Statistics: Spearman IC; mean forward return per quintile / per state; hit rate vs base rate; block bootstrap
   CI (block = h) because overlapping horizons are dependent.
4. Walk-forward: quintile edges fitted on the past only (expanding window, monthly refit); results reported on the
   following unseen month.
5. Stability: per calendar quarter and per regime (trend up / down / range).
6. Acceptance: CI of the walk-forward result excludes 0, same sign in >= 75% of quarters, and the effect is larger
   than costs (0.12% round trip). Rejected features and states are reported with their numbers.

## Output

- `/btc` in Telegram and a block in the morning briefing: the current picture in plain words per window
  (e.g. "4h: rise on perps, OI +2.1%, spot not buying, premium rising"), and for each state its measured history
  ("after this state: 12 h later price lower in 58% of cases, n = 214, CI 51-64%") or "no measurable edge".
- Later: alerts when the picture changes, and a chart page (price, OI, basis, spot vs perp delta on one screen).

## Journal link (personal edge)

Closed trades from LifeOS (Trading Journal + BingX positions for exact entry times). For each trade: the picture at
entry. Report win rate and average R by state and by "picture with / against the trade". Needs ~50 trades for more
than descriptive numbers; the report says so.

## Compatibility with LifeOS

`core/btc_market.py` in LifeOS reads `market_snapshot.json` after `btc_market_intelligence.py --fast`. The new output
is added as a separate command/file and wired into LifeOS in one change.

## Work split

| Step | Owner |
|---|---|
| API reconnaissance -> docs/DATA_SOURCES.md | Haiku x4 (done) + Opus summary |
| Storage + collectors | Sonnet from this document; Opus reviews and runs the backfill |
| Collector tests | Sonnet/Haiku following the first test |
| Features and states | Opus (point-in-time correctness is the main risk) |
| Research engine and report | Opus |
| /btc output, briefing block, LifeOS wiring | Opus design, Sonnet code, Opus deploy |
| Journal link | Opus |
