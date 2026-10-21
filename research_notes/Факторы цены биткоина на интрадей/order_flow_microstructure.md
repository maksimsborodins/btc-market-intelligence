# Order flow and market microstructure factors as 1h-48h predictors of Bitcoin price

Scope note for the report writer: searches were broad but most primary papers were only reachable at abstract level (many are paywalled or PDF-only). Where a claim comes from an abstract or a secondary summary, that is stated. Evidence-quality tags: [PR] peer-reviewed journal, [WP] working paper or preprint (not peer-reviewed), [PRAC] practitioner/media (anecdote, no backtest), [DOC] exchange documentation. The 2023-2026 decay question is poorly covered by rigorous sources; where nothing was found this is stated as a gap rather than filled in.

## 1. Price discovery between BTC spot and perpetual/futures markets: who leads, and has the leader changed since the Jan 2024 spot ETFs?

### Takeaway
Peer-reviewed work finds that derivatives (futures and especially offshore perpetuals) usually lead spot at minute-to-second frequency, but the result depends on sample, sampling frequency and estimator, and the lead fluctuates day to day. A 2025 preprint says the futures lead is weaker than 4-5 years earlier; I found no study that cleanly measures Binance spot vs Binance perp information shares after the January 2024 ETF launch, so "leader changed after ETFs" is an open question here.

### Cited Findings
- Alexander and Heck (J. Financial Stability, Oct 2020, minute data): perpetual swaps and futures on unregulated exchanges (Huobi, OKEx, BitMEX) are the strongest drivers of BTC price discovery; CME futures and US spot exchanges react to rather than lead them. In a multi-market model CME futures have less effect than the spot venues Bitfinex, Bitstamp, Coinbase. [PR] — [IDEAS/RePEc record](https://ideas.repec.org:443/a/eee/finsta/v50y2020ics1572308920300759.html); summary via search result of [SSRN author page](https://papers.ssrn.com/author=3583843)
- Mechanism cited in that literature: perpetuals allow leveraged long and short positions so informed traders can act without buying or borrowing the underlying; the funding payment pulls perp price back toward spot. [secondary summary of the same literature, abstract level] — [Alexander/Heck summary (Decrypt column by A. Urquhart)](https://decrypt.co/322110/professor-coin-how-crypto-derivatives-have-impacted-digital-markets)
- Frino, Gaudiosi, Webb, Zhou, "Price discovery in Bitcoin spot or futures? The jury is out", Journal of Futures Markets 45(4), April 2025: 1-second data, accounting for spot vs futures noise differences; futures generally lead spot but leadership "exhibits daily fluctuations"; futures' contribution rises sharply around macro surprises and Tether-minting tweets; conflicting earlier results are attributed to differing measures, sampling frequencies, windows, contracts and spot venues. [PR; abstract only, sample period not verified] — [Macquarie Univ. record](https://researchers.mq.edu.au/en/publications/price-discovery-in-bitcoin-spot-or-futures-the-jury-is-out/)
- Older, conflicting results: Kapar and Olmo (Dec 2017-May 2018, CBOE/CME) find futures dominate on Hasbrouck IS and Gonzalo-Granger CS; Corbet et al. (2018, 1-min CME/CBOE/spot) find price discovery focused on spot; a 2020 working paper finds CME futures have very minor effect, less than Bitfinex/Bitstamp/Coinbase. — [search-result summary citing Soton eprint](https://eprints.soton.ac.uk/426715) and [Macquarie record](https://researchers.mq.edu.au/en/publications/price-discovery-in-bitcoin-spot-or-futures-the-jury-is-out/); [Waikato WP 1913](https://repec.its.waikato.ac.nz/wai/econwp/1913.pdf)
- Plazuelo Pascual et al., "Price Discovery in Cryptocurrency Markets" (arXiv q-fin.TR, June 2025): uses Hasbrouck IS, Gonzalo-Granger and Hayashi-Yoshida; BTC futures "tend to lead overall" but high-volatility periods give mixed outcomes; ETH centralized markets lead Uniswap. Abstract does not give the BTC sample period or numbers (BTC data appear to be CME spot and futures, no perps mentioned). [WP; abstract only] — [arXiv 2506.08718](https://arxiv.org/abs/2506.08718). A search summary reports the paper says the futures lead is weaker than in analyses from 4-5 years earlier (not verified in full text) — [arXiv PDF](https://arxiv.org/pdf/2506.08718)
- Event-date example (from a search summary, source paper not identified): CME futures Hasbrouck share 0.52-0.56 on most event dates in 2024, dropping to 0.158 on 5 Aug 2024 when spot led. Treat as unverified. — [arXiv 2506.08718 search result](https://arxiv.org/pdf/2506.08718)
- Post-ETF: a paper uses 5-minute data from 11 Jan 2024 to 11 Oct 2024 to compute IS, CS and ILS between spot BTC ETFs and spot BTC; its results were not visible in what I retrieved. [Results unverified; the paper's own URL was not captured. The related earlier spot-vs-ETP paper is [Economics Letters 2023](https://www.sciencedirect.com/science/article/abs/pii/S0165176523001775)]
- Mazur and Polyzos, Journal of Alternative Investments 27(4), March 2025: early spot-ETF period, net ETF flows are a strong positive predictor of BTC price levels (R-squared 95%, levels not returns, so likely spurious-regression prone), and most BTC price changes occur outside ETF trading hours. [PR; abstract only] — [Zayed Univ. record](https://zuscholars.zu.ac.ae/works/7267)
- Practitioner claim: ~11% of a 17% 30-day rally occurred in US hours vs 3% in Asia/Europe (10x Research via CoinDesk, 2024). [PRAC] — [CoinDesk via search summary](https://coindesk-coindesk-prod.cdn.arcpublishing.com/markets/2024/02/15/bitcoins-rise-to-52k-is-driven-by-strong-us-demand-the-coinbase-price-premium-suggests)

### Inferences
- Consistent with the literature, the right prior for Binance data is that perp (about 4x spot volume per one TradingView author, anecdotal) leads spot at seconds-minutes; at 1-48 h horizons lead-lag is mostly absorbed, so a "perp leads spot" effect is unlikely to be directly tradable at hours. What may survive at hours is the flow composition (spot-driven vs leverage-driven moves).
- Mazur-Polyzos "most price changes outside ETF hours" and the practitioner US-hours claim point in opposite directions; the net implication is that testing hour-of-day (US session) conditioning in the user's data is worthwhile, not that a conclusion exists.
- Hypothesis H1 (lead-lag, low priority): Using Binance 1-min spot and perp returns, regress 1h-ahead spot return on lagged perp-minus-spot return gap (basis change). Success: out-of-sample t > 2 after costs and sign stable across 2019-2023 vs 2024-2026 splits. Expect null at 1h.

### Gaps
- No post-Jan-2024 information-share study for Binance spot vs Binance perp found; no full-text numeric results for the post-ETF spot-ETF-vs-spot paper.
- Could not retrieve Kaiko/Amberdata notes on ETF-era price discovery (search returned only a Beehiiv newsletter and unrelated pages).

## 2. Does spot CVD / taker imbalance predict returns at 1-24 h? Does spot vs perp flow divergence (absorption) matter? Is the trader's finding (24h down + Binance spot takers net buy -> +0.43% next 24h, 63% up vs 52%) consistent with known results?

### Takeaway
I found no peer-reviewed or out-of-sample evidence that spot CVD, perp CVD, or their divergence predicts BTC returns at 1-24 h; the "absorption" idea is practitioner heuristic only. The only rigorous order-flow results are contemporaneous (flow explains same-interval price change), with predictive power concentrated at sub-minute horizons plus one 2026 preprint finding opening order imbalance predicting 4-12 h returns on Binance perps.

### Cited Findings
- Practitioner framing: rising CVD while price is flat or falling = "absorption" (buying meeting hidden supply); spot CVD series built from Binance candles (spot from 2017, perps from ~2020). Heuristic, no test. [PRAC] — [bgeometrics orderflow page](https://charts.bgeometrics.com/orderflow.html)
- CryptoQuant-based commentary: negative spot-perp price delta indicates spot-led rally, a flip to positive (leveraged longs) often precedes local tops or corrections. Anecdotal, no backtest. [PRAC] — [CryptoPotato](https://cryptopotato.com/this-overlooked-binance-metric-might-predict-bitcoins-next-major-move/)
- Silantyev (Digital Finance, 2019, BitMEX XBTUSD): trade flow imbalance explains contemporaneous price change better than aggregate order flow imbalance; relationship strongly linear over sufficiently long intervals. Contemporaneous, not predictive. [PR] — [IDEAS record](https://ideas.repec.org/a/spr/digfin/v1y2019i1d10.1007_s42521-019-00007-w.html)
- Wang et al. (Applied Economics, 2021): intraday buy-sell order size imbalance, Jan 2014-Feb 2019; sell-dominated informed trading linked to lower contemporaneous returns, buy-dominated linked to higher returns only in full sample. Contemporaneous. [PR] — [IDEAS record](https://ideas.repec.org/a/taf/applec/v53y2021i28p3223-3233.html)
- Albers, Cucuringu, Howison, Shestopaloff (2021): cross-venue trade flow features give leader-lagger network; linear models explain ~10-37% of variance of 500 ms-ahead returns; passive flow is mostly reactive market-maker activity rather than information. Sub-second only. [WP] — [arXiv 2108.09750](https://arxiv.org/abs/2108.09750)
- "Quarter-Hour Effect" (arXiv, July 2026): Binance perpetual trades for six contracts; volume/volatility bursts at 1-min, 5-min and quarter-hour marks (algorithmic trading); quarter-hour opening returns predictable out of sample; opening order imbalance predicts returns over about 4-12 hours, weaker at finer clock times. Sign (momentum or reversal) and sample period not stated in abstract. [WP, very recent, abstract only] — [arXiv 2607.09426](https://arxiv.org/abs/2607.09426)
- Retail vs informed flow analogue (equities, thesis, not crypto): retail order imbalance predicted positive returns for S&P500 names but negative for meme stocks. Weak evidence, different asset. [thesis] — [Gothenburg thesis via search result](https://gupea.ub.gu.se/server/api/core/bitstreams/18f2ea73-7c64-43ac-b4dc-527ec94c4a9d/content)

### Inferences
- The trader's result (down 24h plus net spot taker buy -> +0.43% next 24 h, 63% up vs 52% base) is directionally consistent with the practitioner "absorption" story and with generic short-term reversal after large declines, but I found no published result that confirms or refutes it. Two cheap checks that the literature implies: (a) condition only on "24h down" and compare, since the +0.43%/63% could simply be daily reversal or mean-reverting-after-drawdown (BTC regime and beta to the 2020-2026 uptrend: a 52% up base rate and positive drift means a conditional-on-down-day sample often shows mean reversion on its own); (b) taker buy ratio drifts with price, because on down moves sellers hitting bids is the default, so "net buy while price falls" is a rare, partly passive-limit-sell-driven state. If the effect disappears after controlling for the unconditional "down-24h" bucket, it is reversal not flow information.
- Overlapping-window caveat: a 24h-forward return conditioned on 24h state sampled hourly has strongly autocorrelated observations; 63% vs 52% needs block bootstrap or non-overlapping daily sampling for valid significance.
- Hypothesis H2 (absorption): Condition C = BTC 24h return < -2% (or below its own tercile) AND Binance spot taker-buy ratio over the same 24h > 0.50 (or spot CVD z-score > +1) AND perp CVD z-score < 0. Outcome: forward 24h and 48 h return from non-overlapping dailies (UTC close). Success: mean excess over the "24h < -2% only" baseline of >= +0.3% with block-bootstrap p < 0.05, and same sign in 2019-2022 and 2023-2026 sub-samples, n >= 100 events.
- Hypothesis H3 (flow divergence, tests the CVD/imbalance literature gap): ranked comparison of spot-CVD-minus-perp-CVD z-score (24h) as a predictor of next 24 h return in a regression with controls (lagged 24h return, realized vol, funding rate). Success: coefficient significant with Newey-West (lag 24) t > 2 and out-of-sample (walk-forward) rank IC > 0.03.
- Hypothesis H4 (4-12 h imbalance, from the 2026 preprint): sign of taker imbalance (taker_buy/volume - 0.5) in the first 5-15 min of each quarter-hour or session open vs forward 4-12 h return on Binance perp; success: out-of-sample hit rate > 52% with t > 2, tested separately for momentum/reversal sign since the preprint abstract does not give it.

### Gaps
- No peer-reviewed test of spot CVD, perp CVD or spot-perp CVD divergence at 1-24 h found. No study of "absorption" quantified.
- Sign of the 4-12 h order-imbalance effect in the 2026 preprint unknown without full text.

## 3. Coinbase premium (Coinbase BTC-USD vs Binance BTC-USDT): does it predict returns, horizon, decay?

### Takeaway
All "Coinbase premium predicts returns" claims I found are practitioner commentary; no academic paper directly tests it as a return predictor. The cross-exchange price-gap academic literature treats gaps as arbitrage frictions, not as signals, and the premium is contaminated by USDT/USD basis and venue-structure changes.

### Cited Findings
- Practitioner use: premium (Coinbase USD price minus Binance USDT price) read as US demand; FalconX analyst called it a "reliable, confirming, and sometimes even leading indicator"; deep negative premiums preceded the Oct 2023-Mar 2024 rally; CryptoQuant analyst says rising premium coincides with continuing bull markets. [PRAC] — [CoinDesk Jul 2024](https://coindesk.com/markets/2024/07/01/bitcoins-bottom-in-price-could-be-near-or-already-in-the-coinbase-premium-index-suggests), [FalconX summary](https://theinformerpost.beehiiv.com/p/coinbase-premium-discount-could-signal-splendid-six-to-12-months-for-bitcoin-says-falconx-analyst)
- Interpretation is contested: one source says it mostly reflects US retail sentiment; another that Coinbase Pro was folded into Coinbase Advanced in early 2024, which may change what the premium measures. [PRAC] — [Cointelegraph](https://cointelegraph.com/markets/bitcoin-coinbase-premium-returns-is-90-k-btc-price-in-the-cards)
- Premium turned positive in Feb 2026 for the first time since mid-January 2025 (so it was negative or flat for ~13 months), suggesting the signal's level regime shifted in the ETF era. [PRAC, search summary] — [MEXC news summary](https://www.mexc.com/news/653819)
- Academic: FMG DP 782 "Trading and Arbitrage in Cryptocurrency Markets" shows cross-exchange BTC gaps can persist for weeks and widen when BTC appreciates sharply; gaps larger across countries than within. [WP/DP] — [FMG](https://fmg.ac.uk/publications/discussion-papers/trading-and-arbitrage-cryptocurrency-markets)
- "Bitcoin arbitrage: The role of an exchange" (Quant. Finance & Economics, 2026): tick data Bitfinex/Bitstamp/Coinbase/Kraken 2017-2021; much measured dispersion involves Bitfinex and disappears without it, attributed to fiat gateway frictions. [PR] — [AIMS Press](https://www.aimspress.com/article/doi/10.3934/QFE.2026024)
- Kang, Lawrence, Wick (2026, FMA conference): exchange-complaint days show wider BTC price gaps vs Coinbase. Gaps as outcome, not predictor. [WP] — [Greenwich eprint](https://gala.gre.ac.uk/id/eprint/53960/)
- Coinbase US-hours link: Coinbase US-session flow and spot ETF creations are both US-hours phenomena, so the premium and ETF flows are likely collinear (inference; no source).

### Inferences
- A USD-vs-USDT premium conflates (a) US demand, (b) USDT/USD basis, (c) different volume ranks between exchanges. Normalizing by rolling z-score and testing changes in the premium, not levels, is more defensible, because levels are persistent (gaps last weeks per FMG DP).
- Hypothesis H5 (premium change): Build 1h Coinbase BTC-USD close minus Binance BTC-USDT close (bps), premium_z = (premium - 30d mean)/30d std. Condition: 6h change in premium_z > +1.5. Outcome: forward 6h, 24 h returns. Success: mean forward return > unconditional by >= 0.15% (6 h) with Newey-West t > 2, stable across 2017-2022 vs 2023-2026; failure criterion: effect only present in pre-2023 data (decay) or disappears after controlling for the contemporaneous BTC return (premium merely mirrors the price move).
- Hypothesis H6 (regime): same test split by UTC hour (US session 13:30-20:00 UTC vs rest) to isolate US-demand content.

### Gaps
- No peer-reviewed return-predictability test for the Coinbase premium. Kaiko/Glassnode/CryptoQuant primary research notes not retrieved (only press summaries). Decay in 2023-2026 only supported by media/anecdote.

## 4. Order book depth and imbalance: predictive only at seconds-minutes, or also hours? Spoofing issues?

### Takeaway
Published evidence shows order book / order flow imbalance predicts at sub-second to about one-minute horizons in BTC; I found no credible evidence of hour-scale predictive power from book imbalance, and very little on spoofing in crypto in these sources.

### Cited Findings
- Jha et al. (2020), "Deep Learning for Digital Asset Limit Order Books": temporal CNN reaches 71% walk-forward accuracy at a 2-second horizon on Coinbase BTC; mid-price predictability persists "often up to a minute"; gains stop after ~10 book levels. [WP] — [arXiv 2010.01241](https://arxiv.org/pdf/2010.01241)
- Wang (2025), Bybit BTC/USDT LOB at 100 ms to seconds: input design and preprocessing matter more than model depth; simple logistic/XGBoost can match deep nets. Cumulative depth imbalances are described as often preceding short-horizon mid-price moves. [WP] — [arXiv 2506.05764](https://arxiv.org/abs/2506.05764)
- Cont-Kukanov-Stoikov OFI: linear relation between OFI and contemporaneous price change (equities), the template that crypto papers follow; contemporaneous not predictive. — [Towards Data Science summary](https://towardsdatascience.com/price-impact-of-order-book-imbalance-in-cryptocurrency-markets-bf39695246f6)
- Charles University thesis on Binance futures (BTC, ETH, LTC): various asymmetry (book imbalance) measures have statistically significant effects on returns, especially over short intervals. [thesis] — [CUNI repository](https://dspace.cuni.cz/handle/20.500.11956/200516)
- Albers et al. 2021: 500 ms-ahead only; passive flow mostly reactive market-maker activity. [WP] — [arXiv 2108.09750](https://arxiv.org/abs/2108.09750)
- Practitioner notes list order-book imbalance alongside funding and the Coinbase premium for confirming bottoms (secondhand attribution to Kaiko). [PRAC] — [blockchain.news](https://blockchain.news/flashnews/US%20spot%20demand)

### Inferences
- Book imbalance is a quote-based variable, quotes are free to cancel, so at hour horizons it is dominated by cancellations and refills; deep (e.g., within 1-5%) depth is more spoof-resistant but still unproven at hours. Binance depth archive (2023+) is snapshot-level so only coarse, slow features (depth at +/-1% and +/-5%, depth ratio bid/ask) can be tested; sub-minute imbalance cannot.
- Hypothesis H7 (slow depth imbalance): Depth_ratio = log(bid depth within 2% / ask depth within 2%) from the 2023+ archive; condition = ratio z-score (30d) in top/bottom decile; outcome: forward 1 h, 4 h, 24 h returns. Success: monotonic decile spread with Newey-West t > 2 at 1-4 h and rank IC > 0.02; expected null at 24 h. Also test depth *thinning* (total depth both sides below 20th percentile) as a predictor of forward realized volatility rather than direction, where the effect is more likely.

### Gaps
- No study of order book imbalance predicting BTC returns at 1-48 h. No crypto-specific spoofing evidence retrieved.

## 5. Intraday momentum vs reversal in BTC at 1-48 h (time-series momentum, overnight and weekend returns)

### Takeaway
Evidence is mixed but structured: intraday momentum (first part of a session predicts the last part) exists in BTC and is tied to liquidity provision and high-volume sessions; reversal also appears after large intraday price jumps and for illiquid coins; daily-horizon momentum is documented for large, liquid coins. Most samples end around 2019-2022, so decay in the ETF era is untested here.

### Cited Findings
- Wen, Bouri, Xu, Zhao (North American J. Econ. & Finance 62, 2022): high-frequency BTC data Mar 2013-May 2020 (also ETH, LTC, XRP); intraday predictability includes both momentum and reversal; momentum matches the late-informed-investor story, reversal (described as unique to crypto) matches overreaction/overconfidence; patterns change around large intraday jumps, FOMC announcements, liquidity and COVID; timing strategy beats always-long economically. [PR; abstract] — [IDEAS record](https://ideas.repec.org:443/a/eee/ecofin/v62y2022ics1062940822000833.html)
- Shen, Urquhart, Wang, "Bitcoin intraday time series momentum", Financial Review 57(2), 2022: first half-hour return predicts last half-hour return (volume-defined trading time); strongest in high volume/volatility sessions; value in timing and allocation, especially in downturns; attributed to liquidity provision rather than late-informed trading. [PR; abstract] — [Birmingham record](https://research.birmingham.ac.uk/en/publications/bitcoin-intraday-time-series-momentum/)
- Zaremba et al. (IRFA 2021) and Ficura (2023), as summarized in search results: daily/weekly reversal for illiquid/small coins, momentum for large liquid coins. Original papers not opened. [PR; secondary summary] — [search summary citing Medeniyet repository](https://earsiv.medeniyet.edu.tr/items/23a96c9f-3952-4bdf-aec5-abafb3aaab70)
- Caporale and Plastun (Springer, Financial Markets & Portfolio Mgmt, BTC/ETH/LTC 2015-2019): on days with abnormal returns, hourly returns continue in the same direction, and the momentum also shows on the day after; authors claim profitable rules. Single research group, simulated trading. [PR; abstract] — [Springer](https://link.springer.com/doi/10.1007/s11408-020-00357-1); [CESifo WP](https://cesifo.org/en/publications/2019/working-paper/momentum-effects-cryptocurrency-market-after-one-day-abnormal)
- Liu and Tsyvinski (Review of Financial Studies, 2021): strong time-series momentum in BTC/XRP/ETH at weekly horizons and attention proxies forecast returns. [PR] — [NBER w24877](https://www.nber.org/system/files/working_papers/w24877/w24877.pdf)
- Quantpedia summary of hourly Gemini data (2015-2022): hourly distribution of returns is not uniform (time-of-day/overnight anomalies exist); details not captured. [PRAC] — [Quantpedia](https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/)
- 2026 preprint: opening order imbalance predicts 4-12 h returns on Binance perps; algorithmic bursts at quarter-hour marks (sign unknown). [WP] — [arXiv 2607.09426](https://arxiv.org/abs/2607.09426)

### Inferences
- Regime-dependence (jumps, volume, FOMC) is the consistent theme, so unconditional momentum or reversal tests at 1-48 h are likely to show small t-stats; conditioning on session volume or on |return| tail is more promising than unconditional lags.
- Hypothesis H8 (1-48 h TSMOM/reversal map): for h in {1,2,4,8,12,24,48}, regress forward h-hour BTC return on trailing h-hour return (non-overlapping, plus Newey-West), separately for calm vs high-volume/high-vol regimes and for 2019-2022 vs 2023-2026. Success: sign-consistent coefficient with |t| > 2.5 in both sub-samples and a walk-forward Sharpe > 0.5 after 5 bps costs per switch. Pre-register the expectation: momentum in high-volume, high-|return| windows (Shen et al., Caporale-Plastun); reversal after a >3 sigma 1-4 h jump (Wen et al.).
- Hypothesis H9 (first-vs-last): first 30-60 min return of US session (13:30 UTC) predicts the return from 20:00 to 21:00 UTC; success: positive coefficient with t > 2 in 2024-2026 ETF era, and not simply a volume effect.

### Gaps
- No ETF-era (2024-2026) replication of intraday momentum or time-of-day effects found. No sourced overnight/weekend-return result for BTC. Full texts of Wen et al. and Shen et al. were not accessible so effect sizes are unknown.

## 6. Is the Binance taker buy volume field reliable? Wash trading and data-quality issues

### Takeaway
The taker-buy fields are documented in Binance kline responses but unexplained there (no definition or methodology); wash-trading evidence on Binance is mixed, older (2018-2022), and mostly from commercial or litigation sources, and none of it addresses taker-side flag accuracy. So reliability is "documented format, undocumented semantics, limited independent validation."

### Cited Findings
- Binance spot kline row has 12 fields, including index 9 "Taker buy base asset volume" and 10 "Taker buy quote asset volume"; the doc does not define taker buy or the calculation; time defaults to UTC. [DOC] — [Binance Spot API docs](https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints)
- Taker side by exchange convention is the aggressor (market order or crossing limit) side; I did not find Binance text stating this beyond the field name, so this is the standard convention, not a verified Binance statement.
- BTI (Blockchain Transparency Institute, 2018): out of top 25 venues only Binance and Bitfinex were not wash trading; later BTI surveillance said over 10% of Binance trading is wash trading, with top pairs like BTC and ETH 85-95% legitimate. Methodology compared order books with web-traffic data, indirect. [commercial report] — [Finance Magnates](https://www.financemagnates.com/cryptocurrency/news/blockchain-transparency-institute-finds-wash-trading-on-binance), [BTI revival](https://www.financemagnates.com/cryptocurrency/exchange/bti-report-revives-allegations-of-crypto-wash-trades/)
- A study finding only 10 of 200 exchanges report true volumes put Binance among them; a 2022 Forbes study named Binance, MEXC and Bybit among firms operating with little regulatory oversight. [secondary] — [Kitco](https://www.kitco.com/news/article/2022-08-26/fake-bitcoin-trading-volumes-continue-plague-crypto-industry)
- Binance.US litigation alleges wash trading by Sigma Chain accounts from 2019 to June 2022: allegations in a complaint, not findings. — [CryptoSlate](https://cryptoslate.com/unlawful-practices-hit-top-cryptocurrency-exchanges-including-binance/)

### Inferences
- Wash trades by definition have both sides controlled by one actor, so they add near-zero net taker imbalance noise but inflate total volume; the imbalance ratio (buy/total) is biased toward 0.5, i.e. attenuated, rather than directionally biased. This would make signals conservative, not spurious (reasoning, no source).
- The more probable data-quality risks for the user's pipeline: kline-based imbalance is aggregated per bar so it cannot separate iceberg/market-maker vs genuine aggressors; possible fragmentation of volume across quote currencies (BTCUSDT vs other stablecoin pairs) and across USDT-margined vs COIN-margined perps (not sourced; check in the user's own data). A robustness check: reconstruct taker imbalance from aggTrades `isBuyerMaker` for sample months and compare to kline field (should match exactly if kline derives from the same stream).
- Hypothesis H10 (data validation): for 10 random days across 2019-2026, compare kline taker_buy_base_volume to sum of aggTrades with isBuyerMaker=false; success: relative error < 0.1%; also compare Binance spot imbalance to Coinbase imbalance (Coinbase trade side) at 1h: correlation > 0.3 indicates a common information component.

### Gaps
- No academic paper on accuracy of Binance kline taker fields; no current (2024-2026) Binance wash-trading audit found. Binance's own definition of "taker buy" not in the retrieved doc page.

