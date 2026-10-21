# Data sources (API reconnaissance 2026-10-21)

All endpoints are public, no keys, reachable from the server without geo-blocks. "Earliest" = earliest data the API
returns. Timestamps in ms unless noted. Probe scripts: LifeOS session scratchpad `recon/`.

## Phase 1 collectors (history for research)

| Collector | Endpoint | Earliest | Page | Paging / quirks | Stored as |
|---|---|---|---|---|---|
| binance_spot_bars | GET https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval={15m,1h} (fallback host https://data-api.binance.vision) | 2017-08-17 | 1000 (silent cap) | forward from startTime; array idx 0 openTime, 1-4 OHLC, 5 volume, 7 quoteVol, 8 trades, 9 takerBuyBase; strings | bars venue=binance_spot |
| binance_perp_bars | GET https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval={15m,1h} | 2019-09-08 | 1500 (1501 -> HTTP 400 and still charged) | forward from startTime; first two 1h bars are flat 10000 placeholders: drop bars before 2019-09-09 | bars venue=binance_perp |
| binance_premium | GET https://fapi.binance.com/fapi/v1/premiumIndexKlines?symbol=BTCUSDT&interval=1h | 2019-12-24 | 1500 | OHLC = premium fraction (perp vs index) | series binance.premium (close), available_at = ts + 1h |
| binance_funding | GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime=..&limit=1000 | 2019-09-10 | 1000 (1001 -> error JSON with HTTP 200) | startTime=0 is ignored (returns newest): always pass a real startTime; fields fundingTime, fundingRate | series binance.funding, ts = available_at = fundingTime |
| binance_metrics (bulk) | https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-YYYY-MM-DD.zip | 2020-09-01, daily files complete to yesterday | one CSV per day, 5-min rows | columns create_time, symbol, sum_open_interest (BTC), sum_open_interest_value (USDT), count_toptrader_long_short_ratio, sum_toptrader_long_short_ratio, count_long_short_ratio, sum_taker_long_short_vol_ratio; exact duplicate rows exist: dedupe on create_time; create_time is a "YYYY-MM-DD HH:MM:SS" UTC string | series binance.oi, binance.oi_usd, binance.top_ls_ratio, binance.ls_ratio, binance.taker_ls_vol_ratio; ts = available_at = create_time |
| binance_metrics_recent | GET https://fapi.binance.com/futures/data/openInterestHist?symbol=BTCUSDT&period=5m&startTime=..&endTime=..&limit=500 (and takerlongshortRatio, globalLongShortAccountRatio, topLongShortPositionRatio) | rolling 30 days | 500 | startTime is IGNORED unless endTime is also given; older than 30 days -> 400 | same series as bulk, fills today + days the bulk files do not have yet |
| bybit_bars | GET https://api.bybit.com/v5/market/kline?category=linear&symbol=BTCUSDT&interval=60 | 2020-03-25 | 1000 (silent cap) | newest first; [start, o, h, l, c, volume, turnover] strings; no taker split | bars venue=bybit_perp |
| bybit_oi | GET https://api.bybit.com/v5/market/open-interest?category=linear&symbol=BTCUSDT&intervalTime=1h&startTime=..&endTime=..&limit=200 | 2020-07-20 | 200 (silent cap) | newest first; page backwards by setting endTime = oldest ts - 1 (or nextPageCursor); field openInterest (BTC), timestamp | series bybit.oi; ts = available_at = timestamp |
| bybit_funding | GET https://api.bybit.com/v5/market/funding/history?category=linear&symbol=BTCUSDT&startTime=..&endTime=..&limit=200 | 2020-03-25 | 200 | newest first; endTime in the future -> empty: cap endTime at now | series bybit.funding |
| bybit_ls_ratio | GET https://api.bybit.com/v5/market/account-ratio?category=linear&symbol=BTCUSDT&period=1h&startTime=..&endTime=..&limit=500 | 2020-07-20 | 500 | newest first; buyRatio, sellRatio, timestamp; nextPageCursor is non-empty even on the last page | series bybit.ls_buy_ratio; available_at = ts + 1h |
| coinbase_bars | GET https://api.exchange.coinbase.com/products/BTC-USD/candles?granularity=3600&start=ISO&end=ISO | 2015-07-20 | 300 (301 intervals -> HTTP 400; end inclusive) | newest first; [time SECONDS, low, high, open, close, volume] - note the column order | bars venue=coinbase_spot, symbol BTC-USD |

## Phase 2 (forward collection or later research)

| Source | Notes |
|---|---|
| Binance bookDepth bulk https://data.binance.vision/data/futures/um/daily/bookDepth/BTCUSDT/ | from 2023-01-01, ~4 days missing; format not inspected yet. Gives historical futures book depth: makes the order-book factor testable. |
| Live order book | Binance spot /api/v3/depth (limit<=5000, weight 250 at 5000, 50 at 1000), fapi /fapi/v1/depth (<=1000), Bybit /v5/market/orderbook (1000/side), Coinbase /products/BTC-USD/book?level=2 (~20k levels, verify) - hourly snapshot of depth within +-0.5/1/2% |
| OKX rubik (open-interest-volume, long-short-account-ratio, taker-volume) | rolling 30 days at 1H, 180 days at 1D: collect daily or lose it. Taker-volume field order (buy/sell) unverified - do not use the split until verified. 1D rows at 16:00 UTC. |
| Deribit DVOL get_volatility_index_data | from 2021-03-24 hourly, no gaps; capped responses return the NEWEST 1000: page backwards with end_timestamp |
| Deribit option book summary | live only; put/call OI ratio computable; no historical skew |
| Deribit funding get_funding_rate_history | from 2019-04-30, cap 744 newest |
| CME BTC=F via Yahoo chart API | 1d from 2017-12-18; 1h only rolling 730 days |
| Farside ETF flows https://farside.co.uk/bitcoin-etf-flow-all-data/ | daily from 2024-01-11, one HTML table; parentheses = negative |
| On-chain | BGeometrics free: 15 req/day, 4 years, ~7-day lag (the live engine depends on it). CoinMetrics community: MVRV ratio, market cap, exchange flows from 2010-2011, page_size 10000 with start_time. Fear & Greed api.alternative.me from 2018. |

## Rate limits and caps to respect

- Binance spot weight: klines 2 per call; fapi klines 10 at limit 1500; failed requests are still charged.
- Silent caps: Binance spot klines 1000, Bybit 200/500/1000 per endpoint, Coinbase 300 (hard error above).
- Responses newest-first: Bybit, Coinbase, Deribit. Responses that return the newest N of a window: Deribit.
