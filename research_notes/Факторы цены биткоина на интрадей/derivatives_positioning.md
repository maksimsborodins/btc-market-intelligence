# Derivatives positioning factors (OI, funding, basis, long/short ratios, liquidations) as short-horizon BTC predictors

Scope note for the report writer: the search tools in this session returned very little peer-reviewed work that directly tests these factors at 1h-48h horizons. Most found material is (a) a pricing/arbitrage paper (He et al.), (b) a BIS working paper on carry and crash risk (daily/weekly+ horizon), (c) a small number of 2026 arXiv cascade-dynamics papers, (d) practitioner/vendor commentary. Where I found no source, this is stated as a gap rather than filled from memory. Evidence-quality labels used below: [PEER/WP] = working paper or journal paper; [PREPRINT] = arXiv preprint, not peer reviewed; [PRACTITIONER] = research-firm/press report, small samples; [VENDOR] = vendor marketing, no method; [DOCS] = exchange documentation.

---

## 1. Does open interest (level, change, z-score) predict direction, volatility or the size of the next move? What do studies say about OI build-ups preceding liquidation cascades?

### Takeaway
I found no rigorous (peer-reviewed or large-sample) study showing that BTC open interest level/change predicts short-horizon direction, and none that establishes OI as a volatility predictor at 1h-48h. The best available evidence on cascades (seven events, 2022-2025) says pre-cascade signals are heterogeneous: no single variable, including leverage, behaves the same way before every cascade; cascades look abrupt and shock-driven rather than a smooth, forecastable build-up. The conceptually sound use of OI is as a conditioning variable for the size/tail risk of moves, not as a directional signal.

### Cited Findings
- Seven major BTC liquidation cascades (2022-2025, including 10 Oct 2025), minute-level price and 5-minute leverage/order-flow data, 39 analysis configurations per variable per event: price showed "critical slowing down" in 5 of 7 events but not in the two sudden-news (tariff) shocks; for October 2025 the signal was in leverage rather than price but the authors call it an outlier; the only pattern present across all events with data was compression of taker order-flow variance (placebo-tested, Fisher-combined p ~ 5e-6), described as a population-level precursor, not a per-event alarm. Conclusion: single-event early-warning claims are fragile and cascades look discontinuous/shock-driven. [PREPRINT, Garcia Seuma, July 2026] — [arXiv 2607.27070](https://arxiv.org/abs/2607.27070). (The abstract did not state which exact "leverage" variable was used; do not assume it is OI.)
- Same author, Oct 2025 crash on a fully transparent on-chain venue: the cascade was deeply subcritical (branching ratio ~0.1-0.2); 88% of post-onset forced selling occurred within 30 minutes; open interest cleared by 25-70% across the events; 63% of post-onset forced selling was absorbed by the venue's backstop; the Galton-Watson model failed both of its testable predictions about the pre-cascade state; severity is attributed to shock size x "map-in-path" effect x liquidity withdrawal rather than a diverging multiplier. [PREPRINT] — [IDEAS/arXiv 2608.03616](https://ideas.repec.org/p/arx/papers/2608.03616.html)
- Order-flow toxicity: a ScienceDirect paper "Bitcoin wild moves: Evidence from order flow toxicity and price jumps" exists (International Review of Financial Analysis-type journal listing) — fetch was blocked (HTTP 403), so its findings are NOT verified here. [link](https://www.sciencedirect.com/science/article/pii/S0275531925004192)
- Futures activity vs. spot jumps (5-minute data): jump risk Granger-causes futures speculative activity, but not the reverse; no causality between futures hedging activity and jump risk (search-result summary of a ScienceDirect abstract; full text 403, not verified). [PEER, Finance Research Letters/Pacific-Basin-type journal] — [ScienceDirect S0927538X23000161](https://www.sciencedirect.com/science/article/abs/pii/S0927538X23000161). Implication if correct: activity follows moves rather than predicting them.
- Another study (search summary only): in the long run, unexpected futures open interest is negatively associated with Bitcoin volatility, while unexpected futures trading volume is positively associated; futures introduction lowered spot volatility in the short run but raised it in the long run. Daily-type data, regulated (CME) futures era — not applicable to 1h-48h Binance OI. [PEER/WP] — [arXiv 2109.15052](https://arxiv.org/pdf/2109.15052)
- Data quality: tick-by-tick data from seven exchanges (two periods in 2023) show open interest in BTC perpetual swaps is systematically misquoted by some large exchanges, to varying degrees, and delayed around forced trades. [PEER, Ledger 2024] — [arXiv 2310.14973](https://arxiv.org/pdf/2310.14973)
- Practitioner small-sample: K33 examined seven long-squeeze events after a 12.46% one-day drop in BTC perpetual OI; BTC averaged about -10% over the following 30 days from pre-liquidation level (reported as conditional event analysis from a small sample, not a rule; secondary-source summary). [PRACTITIONER] — [search summary of K33 2024 analysis](https://www.itechguides.com/can-falling-bitcoin-open-interest-predict-a-btc-crash/)
- Glassnode framing: Estimated Leverage Ratio (OI relative to exchange reserves) high levels "often coincide with BTC spot volatility"; a 2022 note called ~250,000 BTC perp OI a "powder keg for short-term volatility"; Oct 2025 note observed ~30% OI drop flushing leverage. These are descriptive/coincident, with no out-of-sample test reported. [PRACTITIONER] — [CryptoSlate on Glassnode ELR](https://cryptoslate.com/liquidations-expected-as-bitcoin-open-interest-leverage-ratio-spike-higher/)
- A commentary on Oct 2025 describes the cascade as "an accelerant, not the ignition" (liquidations amplify a trigger). [VENDOR/press] — [BeInCrypto](https://beincrypto.com/liquidation-cascade-onchain-technical-analysis/)

### Inferences
- Consistent with the trader's null result: OI measures the amount of positioning, not its sign. The cascade papers say the trigger is exogenous or abrupt (tariff news) in the biggest events, so OI alone cannot give direction; at best it conditions how far a trigger propagates (tail size).
- Recommended test design (volatility/tail target, not direction): target = forward realized range or absolute return over 4h/12h/24h (e.g. log(high/low) or |ret|), scaled by trailing volatility. Predictors: OI z-score (OI / rolling 30d median, or OI/market cap proxy), 4h/24h %change of OI, and the interaction with realized-vol regime. Compare against a baseline that already includes trailing realized volatility (HAR-type) — OI must add incremental R2/QLIKE out of sample, otherwise it is just proxying volatility clustering.
- Testable hypothesis H1 (volatility): condition = BTCUSDT OI z-score (30d window, 5-min data resampled to 1h) > +2 AND trailing 24h realized vol below its own 30d median ("quiet but crowded"). Prediction: forward 12h high-low range exceeds the unconditional 12h median range by more than a chosen margin (e.g. top-quartile range probability >= 40% vs 25% base rate). Success metric: hit-rate lift with block-bootstrap CI excluding base rate, AND positive out-of-sample incremental QLIKE/R2 vs HAR baseline on a held-out year (use 2024-2026 as OOS).
- Testable hypothesis H2 (tail/cascade): condition = 4h OI drop > X% (choose by percentile, e.g. bottom 1% of 4h OI changes) coinciding with |4h return| > 2 sigma. Prediction: next 12h realized vol remains elevated (vol persistence), tested as ratio of next-12h to prior-12h realized vol. Metric: median ratio > 1 with CI; this is a volatility-persistence claim, not directional.
- The small K33 sample (7 events, -10% over 30 days) is far outside the 1h-48h scope and too small for inference; treat as anecdote.

### Gaps
- No peer-reviewed paper found that tests Binance/aggregate BTC OI against forward 1h-48h realized volatility or direction. Searches ("open interest forecasting realized volatility bitcoin perpetual futures SSRN") returned only vendor/TradingView material.
- The ScienceDirect papers (order-flow toxicity and jumps; futures activity and jump risk) were not readable (403); their quantitative results are unverified.
- No sourced evidence on whether the OI-volatility link has decayed after 2024 spot ETFs.

---

## 2. Do extreme funding rates or basis predict reversals (crowded positioning) at 8-48 h? How strong and how stable is the effect?

### Takeaway
The strongest rigorous evidence links high carry/basis to crash risk at longer horizons (BIS, daily-to-weekly+ sample), and to arbitrage profits (He et al.), not to directional reversals at 8-48h. Funding's own information content is mostly mechanical (it tracks the perp-spot basis by design), and the arbitrage channel has decayed (annualized funding/basis compressed after 2024). Practitioner evidence on extreme negative funding is small-sample and long-horizon (90 days).

### Cited Findings
- BIS WP 1087 "Crypto Carry" (Schmeling, Schrimpf, Todorov, April 2023): crypto futures carry averages above 10% a year and can reach ~60%; driven by a volatile convenience yield from leveraged retail demand and scarce arbitrage capital; the headline result is that high carry predicts future price crashes and goes together with a higher price of crash-risk insurance; crypto futures show excess volatility relative to spot; interest-rate differentials explain little of carry. The abstract page does not state the forecast horizon or data detail. [PEER/WP, BIS] — [BIS WP 1087](https://www.bis.org/publ/work1087.htm)
- He, Manela, Ross, von Wachter, "Fundamentals of Perpetual Futures": Binance hourly data, BTC/ETH 2020-01-08 to 2024-03-11. Funding is paid every 8h and approximately equals the average futures-spot spread over the preceding 8h, with a clamp and recency weighting so tracking is imperfect. Past 120-day spot returns significantly predict the futures-spot deviation (t ~ 4.5 to 10.4; R2 up to 0.33 in Table 9). Mean absolute deviation |rho| shrinks ~11% per year (>44% over the sample). BTC arbitrage Sharpe (high-cost tier) by year: 2.26 (2020), 2.39 (2021), 0.70 (2022), 1.32 (2023). Share of time the strategy is active fell from 28.66% (2020) to 7.68% (2023). The funding channel's share of strategy returns: BTC 7.68% (2020), 15.31% (2021), -1.94% (2022); price convergence dominates. The paper tests deviations/arbitrage, not whether funding predicts spot direction. [PEER/WP; arXiv v5] — [arXiv 2212.06888](https://arxiv.org/html/2212.06888v5) (note: the fetch summarizer flagged that the introduction's "R2 above 50%" claim is not supported by Table 9; the 2024 Sharpe of 11.52 is a short partial year and likely an outlier)
- BitMEX funding: Granger causality plus GARCH models relate BitMEX funding to the bitcoin exchange rate (2019, single exchange, inverse perp, small scale). [PREPRINT] — [arXiv 1912.03270](https://www.arxiv.org/abs/1912.03270)
- K33 (Sept 2024): when the 30-day average perp funding rate flipped negative (7 times since 2018), average 90-day BTC return was 79%, median 55%. 7 episodes, overlapping, 90-day horizon, not an 8-48h effect. [PRACTITIONER] — [The Block](https://www.theblock.co/post/315831/perp-signal-bitcoin-bottom-bullish-year-end-k33)
- Structural change 2024-2026: annualized BTC basis peaked at 20-25% in 2024 and compressed to ~10% by mid-2025; the ETF-vs-CME basis trade (long spot ETF, short CME futures) unwound in 2025, with some analysts calling it structural (carry falls below risk-free + capital cost) and others cyclical; sources are press/industry, not primary data. [PRACTITIONER/press] — [sFOX](https://www.sfox.com/blog/bitcoin-etf-stress-test-arbitrage-exits/); [The Block on CME activity](https://www.theblock.co/post/396722/cme-bitcoin-futures-activity-slumps-to-14-month-low-as-basis-trade-unwind-drains-institutional-demand); [DL News](https://dlnews.com/articles/markets/how-investors-trading-bitcoin-price-amid-1b-usd-etf-outflow)
- TradingView scripts claiming funding + normalized OI identify reversals have self-reported, unverified performance. [VENDOR] — [example](https://kr.tradingview.com/script/4ZQOgvaj)

### Inferences
- Why the trader's "funding/premium alone does not predict direction after costs" is expected: funding is a smoothed lagged function of the basis, which itself is a function of past returns (He et al.: 120-day past returns explain up to 33% of deviation). So it largely re-encodes past trend and momentum. Any reversal signal must be extreme, rare, and conditional (the K33 example is a 7-event, 90-day, extreme-only signal).
- Funding carries crash/tail information (BIS) rather than first-moment information; the right target is left-tail probability or downside range, not sign of return. Mapping BIS to 8-48h horizon is an extrapolation and untested here.
- Testable hypothesis H3 (tail, 8-48h): condition = Binance BTCUSDT 8h funding in top 2% of its trailing 1-year distribution (or annualized funding > ~30-40% given post-2024 compression; calibrate by percentile not absolute level) AND premium index z-score > 2. Prediction: probability of a >= 3% drawdown (peak to trough from signal time) within 24h is higher than baseline. Success metric: lift in drawdown frequency vs base rate with block-bootstrap CI excluding 1, and a monotonic relationship across funding deciles; evaluate separately for 2021-2023 and 2024-2026 to detect decay. Expect few independent events, so require >= 30 non-overlapping signals or declare underpowered.
- H4 (contrarian direction, extremes only): same condition, prediction = negative forward 24h return. Success metric: mean return of signal bars below zero by >= 2x round-trip cost (taker 0.04% x2 + slippage) with Newey-West t < -2. Prior from the literature: low; the trader's own null result already points this way.
- Compare Binance vs Bybit vs Deribit funding dispersion as a crowding measure (cross-exchange spread) — untested here; flagged as a candidate, not evidence.

### Gaps
- No sourced study of funding extremes predicting 8-48h BTC returns. Searches for Kaiko/Glassnode/Amberdata/Paradigm/Binance Research studies of funding-predictive power returned no original quantitative study (one Kaiko/Deribit attribution was a one-line flash news item).
- BIS WP 1087 horizon and regression magnitudes not retrieved (abstract page only; full PDF https://www.bis.org/publ/work1087.pdf not read).
- No sourced estimate of how the funding-return relationship changed in 2023-2026 beyond basis compression and the arbitrage-Sharpe decay.

---

## 3. Do liquidation cascades (sharp OI drops with large price moves) mean-revert at 1-12 h? Evidence?

### Takeaway
No rigorous study found that directly tests post-cascade mean reversion of BTC price at 1-12h. What exists: in-cascade dynamics are fast (most forced selling within 30 minutes), OI clears 25-70%, and venue liquidity recovery after the October 2025 cascade was reported as well underway intraday. This supports a hypothesis of liquidity-driven overshoot and partial recovery, but the price-reversion magnitude and reliability at 1-12h is unquantified in the sources.

### Cited Findings
- 88% of post-onset forced selling occurred within thirty minutes; OI cleared 25-70% across seven events (2022-2025); the 10 Oct 2025 event was subcritical with substantial backstop absorption. [PREPRINT] — [arXiv 2608.03616 via IDEAS](https://ideas.repec.org/p/arx/papers/2608.03616.html)
- Reported Hyperliquid liquidity recovery after Oct 10, 2025: a Journal of Financial Digital Assets paper with a "two-regime recovery" framing, intraday recovery well under way by end of day (from search-result summary; the page fetch failed with a socket error, so details are unverified). [PEER (journal)] — [JFDA 1395](https://journals.lincoln.ac.nz/index.php/JFDA/article/view/1395)
- Oct 10, 2025: ~$19B liquidated in a day, the largest single-day liquidation event in crypto history, per press. [press] — [Decrypt](https://decrypt.co/344141/explaining-bitcoin-crash-liquidations-leverage)
- Post-event leverage reading: one practitioner source said Estimated Leverage Ratio remained above 0.50 post-crash (deleveraging partial); another noted 30-day annualized basis fell from 6.63% to 4.47% (market-structure observation, not a reversion test). [PRACTITIONER] — [Amberdata blog (now redirected to Kaiko after acquisition)](https://blog.amberdata.io/the-leverage-purge-how-8.55b-in-liquidations-reset-the-market); [Kaiko acquisition notice](https://www.kaiko.com/news/kaiko-acquires-amberdata-in-landmark-digital-asset-data-consolidation) (the blog article body could not be fetched; figures come from the search summary)
- Free liquidation data: Binance USD-M futures `<symbol>@forceOrder` stream pushes only the latest liquidation order per symbol within each 1000 ms window as a snapshot; no message if none occurred (so aggregate liquidated notional is a lower bound). [DOCS summary via search] — [Binance docs](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams) (the direct page fetch returned only a landing page; the arXiv 2607.27070 summary says Binance per-event liquidationSnapshot dumps were discontinued, so historical free liquidation data is unavailable and forward collection is the only free route)
- A research hit on BitMEX: daily forced liquidations averaged 3.51% for longs and 1.89% for shorts; normal-return margin models underestimate margins. [PEER/WP] — [Liquidation, Leverage and Optimal Margin in Bitcoin Futures Markets](https://physics.paperswithcode.com/paper/liquidation-leverage-and-optimal-margin-in)

### Inferences
- If most forced flow is done within ~30 min and OI has been cleared, the marginal forced seller is gone and the price impact is partly transient (liquidity withdrawal rather than information). This points to a short-lived overshoot, but only if the cascade was endogenous; for exogenous shocks (tariff news) the move may be fundamental and not revert.
- Testable hypothesis H5 (post-cascade reversion): define a cascade bar on Binance 5-min data as 1h price return below -2.5 sigma(trailing 7d, hourly) AND 1h OI change below its 2nd percentile (sharp OI drop confirming forced closing, not new shorts). Entry at close of the cascade hour + 1 bar (to avoid look-ahead), horizon 1h/3h/6h/12h. Prediction: mean forward return positive (long after long-liquidation cascade) and larger than for equally large down-moves WITHOUT OI drop (the control group). Success metric: mean return difference (cascade vs matched control) > round-trip costs, block-bootstrap CI excluding 0, at least ~30 independent events (cluster events within 6h). Mirror the test for upside short-squeeze cascades (OI drop with +2.5 sigma). Expect small sample; if fewer than 30 events, report as exploratory.
- H5b (to separate endogenous vs exogenous): split events by whether the price move started with a volume/taker-flow shock without OI build-up (exogenous) vs preceded by 24h OI z-score > 1.5 (endogenous). Reversion should concentrate in the endogenous group (prediction from the two-type cascade taxonomy in arXiv 2607.27070).

### Gaps
- No quantitative study found of BTC price mean-reversion after liquidation cascades at 1-12h; search "crypto liquidations mean reversion after cascade arXiv" returned only the cascade-dynamics preprints.
- Historical liquidation data (pre-collection) is not freely available from Binance; free alternatives for backfill were not identified in this research.

---

## 4. Do long/short ratios (retail account vs top traders) carry contrarian information?

### Takeaway
I found no independent, rigorous backtest; only vendor claims and anecdotes. The metric definitions themselves complicate interpretation (account-count vs position-weighted; structural long bias on retail venues).

### Cited Findings
- Binance defines "top traders" as roughly the top 20% of accounts by margin balance (single vendor statement, not verified against Binance docs); retail-oriented venues (Binance, Bybit, Bitget) run structurally long (ratios of 2-4x long are normal even in sideways markets) per the same vendor. [VENDOR] — [Sharpe.ai long/short ratio](https://www.sharpe.ai/futures/bitcoin/long-short-ratio)
- The top-trader account ratio is the share of top accounts net long vs net short (account count), not notional-weighted; Amberdata's changelog distinguishes Binance top-trader variants: dollar-weighted positions ratio vs account-count ratio, with 5-minute minimum granularity. [VENDOR/docs] — [Sharpe.ai](https://www.sharpe.ai/futures/binancecoin/long-short-ratio); [Amberdata docs](https://docs.amberdata.io/changelog/lsr-metric-type)
- Vendors assert opposite directional readings: one says the top-trader ratio is "more predictive" and one should align with top traders; another calls the crowd-vs-top gap a "classic contrarian signal". Neither cites a backtest. [VENDOR] — [Sharpe.ai](https://www.sharpe.ai/futures/bitcoin/long-short-ratio); [oanor](https://oanor.com/tag/contrarian)
- Single anecdote: a 2025 episode where Binance top accounts were mostly net short into the highs and heavily long during a later drop. [press] — [The Block](https://www.theblock.co/amp/post/380213/btc-perp-accounts-turn-heavily-long-as-binance-long-short-ratio-surges-to-3-87)
- Binance REST endpoints for basis, global long/short account ratio, and open interest statistics expose only the latest 30 days (limit max 500; periods include 5m...12h); see Gaps for how to get the 2020-09+ history. [DOCS] — [Binance docs](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics)

### Inferences
- A structural long bias means levels are non-stationary across time; use rolling z-scores or percentile ranks, and use the spread (retail LS minus top-trader position LS) rather than the level. Because the account-count ratio counts accounts not notional, a few whales can be invisible in the account ratio; prefer the top-trader POSITION ratio.
- Testable hypothesis H6: condition = divergence D = z(global account LS) - z(top-trader position LS) > +2 (retail crowded long, top traders less long) at 5-min sampled to 1h. Prediction: forward 4h/12h/24h return negative. Success metric: mean forward return below zero by > costs with Newey-West t < -2 in both 2020-2023 and 2024-2026 halves, and sign stable across both; include a placebo using shuffled time blocks. Prior from literature: no support found; treat as a low-prior test, and test mirrored (D < -2) as well.

### Gaps
- No academic or independent quantitative test of Binance account/top-trader LS ratios against BTC returns found. Search returned vendor pages only.
- The vendor definition of "top 20% by margin balance" is unverified against Binance documentation.

---

## 5. Liquidation heatmaps / clusters as price magnets: rigorous evidence, or anecdote?

### Takeaway
Anecdote and vendor narrative; no rigorous test found. Note that Coinglass-style heatmaps are model-based estimates (they infer liquidation prices from OI, assumed leverage tiers and entry price distribution), not observed positions, and the one rigorous venue-level analysis (October 2025, transparent on-chain venue) attributes severity partly to a "map-in-path" effect, which is a weak form of support for clusters mattering once a move is underway.

### Cited Findings
- Search for empirical tests of liquidation heatmaps as magnets returned only vendor pages (Sharpe.ai says heatmaps "often act as a magnet", no data; CoinPerps calls them a context tool, not a standalone signal; TradingView scripts disclaim that stats describe only chart history). [VENDOR] — [Sharpe.ai](https://www.sharpe.ai/futures/liquidations); [CoinPerps](https://www.coinperps.com/bitcoin-liquidation-heatmap); [Quantum Algo script](https://de.tradingview.com/scripts/liquidity-heatmap/)
- In the cascade microstructure work, severity is the product of shock, a "map-in-path" effect and liquidity withdrawal; the same paper rejects a critical-multiplier build-up story. [PREPRINT] — [arXiv 2608.03616](https://ideas.repec.org/p/arx/papers/2608.03616.html)
- Taker order-flow variance compression preceded all cascades with data, i.e. a flow signal, not a map-based signal. [PREPRINT] — [arXiv 2607.27070](https://arxiv.org/abs/2607.27070)

### Inferences
- The "magnet" claim is subject to heavy selection bias (clusters near the current price are always on the map, and price touches nearby levels often by chance). A valid test needs a null (matched-volatility random walk or shifted/mirrored cluster levels) and counting touches within horizon; screenshots from paid Coinglass would need to be digitized, which limits sample size.
- Testable hypothesis H7: from forward-collected data (Binance forceOrder stream + own snapshots of Coinglass heatmap or own estimated liquidation map from OI x leverage-tier assumption), for each 4h snapshot identify the largest cluster within +/-3% of price. Prediction: probability that price touches the cluster level within 24h exceeds the probability for a mirrored level (same distance on the other side) and for a shifted placebo level (random offset). Success metric: touch-rate difference > 10 percentage points with binomial/bootstrap p < 0.05 over >= 100 snapshots. Secondary: after touch, 1h-6h continuation vs reversal (stop-hunt hypothesis = reversal).

### Gaps
- No peer-reviewed or independent quantitative evidence found on heatmap clusters acting as magnets or on stop-hunting around them.
- Cost and method of Coinglass heatmap (the user stated paid, screenshots possible) not researched; free alternatives other than forward-collecting forceOrder are not identified.

---

## 6. Why OI/funding/premium alone fail after costs, and how to test them instead (conditioning, volatility targets, extremes only)

### Takeaway
The literature found points to these factors being (i) mechanically tied to past returns (basis/funding follow trends), (ii) informative about tail/crash risk and volatility rather than the sign of the next return, and (iii) event-heterogeneous in cascades (shock-driven, not smooth build-ups). That is consistent with the trader's null result for direction after costs and "price up + OI up + spot not buying" showing no edge. The testing approach should switch the target from direction to volatility/tail, use extreme-only conditioning, and demand out-of-sample, cost-aware, regime-split validation.

### Cited Findings
- Carry/basis is predicted by past returns (120-day spot return coefficients t = 4.5-10.4, R2 up to 0.33) and deviations shrank ~11%/year; arbitrage Sharpe fell after 2021 (BTC high-cost: 2.39 in 2021 to 0.70 in 2022, 1.32 in 2023). [PEER/WP] — [arXiv 2212.06888](https://arxiv.org/html/2212.06888v5)
- High carry predicts crashes and crash-insurance price (tail information), not average returns. [PEER/WP] — [BIS WP 1087](https://www.bis.org/publ/work1087.htm)
- No variable is event-invariant before cascades; shock-type (exogenous vs endogenous) matters; only taker order-flow variance compression appears across all events. [PREPRINT] — [arXiv 2607.27070](https://arxiv.org/abs/2607.27070)
- Exchange OI data are noisy and sometimes misquoted, so cross-exchange aggregates are unreliable and a single-exchange (Binance) series is cleaner for testing. [PEER] — [arXiv 2310.14973](https://arxiv.org/pdf/2310.14973)
- Institutional/market-structure change: ETF basis trade ramped in 2024 and unwound in 2025, annualized basis compressed from 20-25% to ~10% by mid-2025 (press-level evidence, not quantified in a primary dataset). [PRACTITIONER/press] — [sFOX](https://www.sfox.com/blog/bitcoin-etf-stress-test-arbitrage-exits/)
- "Up price + up OI + spot not buying" (perp-led rally) is commonly described as fragile, but I found no sourced test of it; the scripts that classify regimes by 7-day OI change vs 7-day price change are descriptive. [VENDOR] — [TradingView OI 7-day change](https://fr.tradingview.com/script/DSJG3e84-BTC-Futures-Open-Interest-7-day-Change-QR)

### Inferences
- Methodological checklist for the trader's tests: (1) Target: forward range / |return| / downside-tail indicator, scaled by trailing vol, and compare to a HAR baseline. (2) Conditioning: extremes only (top/bottom 1-5% by rolling percentile, not absolute levels, because funding/OI regimes drifted after 2024), plus interaction terms (OI z-score x price shock x taker imbalance). (3) Sample: split 2020-09..2023-12 vs 2024-01..2026-10 (ETF era); report decay explicitly. (4) Overlap: use non-overlapping signal clustering (cooldown >= horizon) and block bootstrap; count independent events. (5) Costs: taker fee + slippage; for direction tests require edge > 2x costs. (6) Multiple testing: with many thresholds/horizons, apply deflated Sharpe or Bonferroni/BH correction; the cascade paper's own 39-configuration design illustrates the risk. (7) Placebo: shuffled-time or mirrored signals.
- Testable hypothesis H8 (replaces the failed "price up + OI up + spot not buying" test): condition = 4h price +1.5 sigma AND 4h OI +2 sigma AND taker buy ratio > 1.3 on futures with spot volume share (Binance spot / perp volume) below its 30d 10th percentile. Prediction not for direction but for subsequent drawdown risk: probability of a >= 1.5% pullback from the local high within 12h vs unconditional. Success metric: lift >= 1.3x with CI excluding 1; if lift is absent, drop the factor.
- Do not assume direction from the combination; the supported use is (a) tail/volatility sizing (reduce size or widen stops when OI and funding are extreme), and (b) filtering other signals.

### Gaps
- Sourced evidence for the "spot not buying / perp-led rally" thesis is absent.
- No sourced evidence found on decay of OI/funding/LS effects specifically in 2023-2026 apart from basis compression and He et al.'s arbitrage decay (sample ends Mar 2024). Note that the full text of He et al. after offset 100,000 characters was not read.
- Not retrieved or confirmed: Paradigm, Binance Research, Galaxy, Coinbase Institutional, and Fed/BIS bulletin studies on leverage and liquidations (a BIS bulletin hit, bisbull66, appeared in results but its content was not opened and its relevance is unconfirmed).

---

## 7. Free data available to the trader: what the search could and could not confirm

### Takeaway
Binance REST statistics endpoints (OI history, long/short ratios, basis) only serve the latest ~30 days, so a 2020-09+ history must come from elsewhere (daily archive files, own collection). Liquidation history is not freely available; the free route is forward collection from the forceOrder stream.

### Cited Findings
- Binance REST: basis, global long/short account ratio and open interest statistics endpoints cover "latest 30 days" (OI: "latest 1 month"), max 500 rows per call, periods from 5m; periods with no trades are omitted. [DOCS] — [Binance docs](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Open-Interest-Statistics)
- data.binance.vision UM futures daily "metrics" files for BTCUSDT include open interest and long/short fields (top-trader ratio, all-accounts ratio, taker buy/sell ratio) per a GitHub issue; at the time of that issue, only a once-per-day open interest value was visible, and I could not confirm in this session whether the current files hold 5-minute rows. [GitHub issue summary] — [binance-public-data #211](https://github.com/binance/binance-public-data/issues/211)
- Amberdata long/short ratio endpoint: 5-minute granularity ("lowest granularity offered by the exchanges"). [VENDOR docs] — [Amberdata](https://docs.amberdata.io/data-dictionary/market/longshort-ratio)
- forceOrder: see Section 3 (1000 ms snapshot sampling, latest liquidation only, no messages if none). [DOCS] — [Binance docs](https://developers.binance.com/docs/derivatives/usds-margined-futures/websocket-market-streams/Liquidation-Order-Streams)

### Inferences
- The user's stated data window (Binance 5-min OI/LS/taker 2020-09+) should be verified by actually downloading the data.binance.vision metrics files and checking row frequency before designing tests; if only daily rows exist, intraday (1h-48h) tests on Binance history are impossible before own collection started, and Bybit/other sources would need to be used.
- For liquidations, start a forceOrder collector now (all-symbol `!forceOrder@arr`) writing to disk; note it under-counts (one order per second per symbol), so use it as an event flag rather than precise notional.

### Gaps
- Exact current coverage and frequency of data.binance.vision metrics files not confirmed.
- Bybit OI/funding/LS and Deribit funding history limits not researched.
- Free alternatives for historical liquidation data not found.
