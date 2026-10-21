# Capital-flow, on-chain and sentiment factors as predictors of BTC price (1 h to a few days; slower context)

Method note: research done 2026-10-21 via web search and fetch. Many academic items were available only as abstracts, SSRN pages or search-tool summaries, so effect sizes are given only where I actually saw them. Items I could not verify are in Gaps. Evidence quality tags: [peer-reviewed], [working paper/thesis], [vendor], [blog/news].

## 1. US spot Bitcoin ETF flows: do they predict next-day BTC returns, or follow price?

### Takeaway
Daily ETF flows are strongly contemporaneous with BTC returns and are persistent, but the best 2025-26 evidence says flows mostly CHASE past returns (reverse causality). Evidence that flows add incremental next-day predictive power beyond past returns is conflicting: one SSRN working paper says yes (with a reversal caveat), one thesis and one vendor study say no/weak. Treat ETF flows as a weak, unproven 1-48 h predictor; they are mainly a confirmation/context variable.

### Cited Findings
- Mazur & Polyzos, "Spot Bitcoin ETFs: The Effect of Fund Flows on Bitcoin Price Formation", Journal of Alternative Investments 27(4), Mar 2025 [peer-reviewed]: net flows are a "strong predictor of bitcoin price levels" (R-squared 95%), daily flows often exceed $500m, most BTC price changes occur outside ETF trading hours, and a BTC price increase "leads to abnormal ETF trading volume". The page does not show a causality test; the 95% R-squared is on price LEVELS (non-stationary, likely spurious-regression-prone), sample is only the first several weeks after launch. — [ZU Scholars abstract](https://zuscholars.zu.ac.ae/works/7267)
- Guliyev & Ahmadova, "From Flows to Value: Cointegration Between Bitcoin Spot ETF Assets and Bitcoin Price" (Ledger, Pitt) [peer-reviewed]: long-run cointegration between ETF assets and BTC price; cointegration shows co-movement not direction (I could not fetch the full text; certificate error). — [Ledger page](https://ledger.pitt.edu/ojs/ledger/article/view/393) (known only via search summary)
- FalconX research blog, Oct 2024 [vendor/blog], ~10 months of daily data from 2024-01-11: contemporaneous correlation of 7-day changes r = 0.30 (<10% variance explained); Granger test F = 8.48, p = 0.004 (flows -> price); VAR one-day-lag coefficient of prior-day flows on price change = 0.027 vs price momentum 0.802; impulse response of a flow shock peaks at ~1.2% price rise around day 3-4 then fades; authors note price rises may dampen inflows, no out-of-sample tests, no hit rates, stationarity assumption questionable. — [FalconX](https://www.falconx.io/newsroom/what-can-spot-etf-flows-tell-us-about-the-trajectory-of-bitcoin-prices-a-preliminary-statistical-investigation)
- Boon Chuan Lim, "The Price Impact of Spot Bitcoin ETF Flows" (SSRN 6592830) [working paper]: five largest US spot ETFs, Jan 2024 - Apr 2025; flows explain 21% of daily return variation (t = 8.99), predict next-day returns (Newey-West t = 3.12), bidirectional feedback loop (returns also cause subsequent flows); after controlling for future flows, individual flow shocks "reverse significantly" (author calls this a flow-persistence illusion). Seen only via search-tool summary (SSRN returned 403). — [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6592830)
- Concordia University thesis, "The Impact of Bitcoin ETF Flows on Price Dynamics: Evidence from the Post-Approval Era" [thesis, unreviewed]: 494 trading days (Jan 2024 - Dec 2025); BTC returns Granger-predict subsequent ETF flows (p < 0.001), i.e. performance chasing; publicly observable flow data carry no incremental predictive information for future returns once past returns are controlled; flows explain at most 1.77% of BTC return variance. Seen via search-tool summary (fetch failed on certificate). — [Concordia Spectrum](https://spectrum.library.concordia.ca/id/eprint/997714/)
- Bitwise Europe research (global Bitcoin ETP flows, % of AuM) [vendor]: strongest driver of flows is own persistence (lagged-flow coefficient ~0.64) plus BTC's recent return (cross-correlation ~+0.19 with performance leading flows by one day, ~+0.16 at lag 0); correlations of flows with SPY/QQQ/TLT/GLD are near zero (+0.04, +0.06, -0.01, -0.03); VIX/MOVE weak (-0.10/-0.11); authors say returns and flows are "jointly intertwined" and their own Granger text is internally inconsistent. Sample dates not stated. — [Bitwise](https://bitwiseinvestments.eu/blog/crypto-research/bitcoin-etp-series-part-2/)
- Volmex working paper (2024) [working paper]: net ETF flows show no significant link with realized volatility, but IBIT-specific flows do; larger IBIT inflows associated with larger downward BTC price spikes (seen via search summary only). — [Volmex PDF](https://volmex.finance/Cryptocurrency-Market-Dynamics-Following-the-Approval-of-Bitcoin-ETFs.pdf)
- Ecoinometrics newsletter claims monthly flows explain ~75% of price moves [blog; no causal test seen] — [Ecoinometrics](https://ecoinometrics.substack.com/p/bitcoin-returns-and-etf-flows-correlation)
- Mechanism hint: most BTC price change happens outside US ETF trading hours (Mazur & Polyzos above), so a given day's ETF flow (struck at US close, published after) partly reflects what BTC already did overnight and intraday.

### Inferences
- Because daily flow is determined at/after US close and BTC trades 24/7, the flow figure for day t is largely a function of BTC return during day t-1/t. A next-day regression of return(t+1) on flow(t) must control for return(t); the thesis says the effect disappears, Lim says a small effect remains and then reverses. Net: likely small, unstable, possibly mean-reverting at the 1-3 day horizon.
- 95% R-squared and "cointegration" results are level-on-level and say nothing about tradable returns prediction.
- Testable hypothesis H-ETF1: using only Farside daily total net flow F(t) published after US close of day t, regress BTC return from 00:00 UTC day t+1 to t+1 close (and t+1..t+3) on F(t) standardized by 20-day rolling std, controlling for BTC return of day t and of the preceding 3 days, using HAC errors. Success = coefficient on F(t) significant (|t|>2.5, accounting for multiple lags tested) in expanding-window out-of-sample on 2024-01-11..2026-10 AND directional hit rate on |F|>1.5 std days >55% net of 10 bp round-trip costs. Prior: more likely to fail.
- Hypothesis H-ETF2 (conditional / divergence): days with large inflow (>+1.5 std) but BTC return of that day < 0 (flow "absorbs" selling) vs. large outflow with positive price; test 24-72 h forward return vs unconditional. Pure speculation; no study found testing this.
- Verdict: ETF flows are a marginal/unproven factor for 1-48 h; plausible use is as a regime filter (5-10 day cumulative flows), not as an entry trigger.

### Gaps
- Could not access full text of Lim (SSRN), Concordia thesis, Guliyev & Ahmadova, Mazur & Polyzos; lag orders, stationarity treatment and out-of-sample design unverified.
- No peer-reviewed study found that tests flows with intraday timestamps (e.g. returns from US close to next day's open).
- No source found specifying how the sign/size of the flow-return relationship changed in 2025-26 (post Oct-2025 drawdown).

## 2. Stablecoin supply growth and mints (USDT/USDC)

### Takeaway
No credible evidence that stablecoin mints predict BTC returns at 1-48 h in a tradable way. Academic event studies find issuance FOLLOWS market downturns and shows small/inconsistent abnormal returns; vendor claims of stablecoin supply "leading" BTC are episode-based and slow (weeks-months), and probably reflect common liquidity or reverse causality. One intraday paper reports USDT exchange net inflows positively predict BTC returns at 1-2 h, which is the only short-horizon positive lead, but it is a different variable (exchange-deposited USDT, not mints) and I could not verify effect sizes.

### Cited Findings
- Ante, Fiedler & Strehle (2020), BRL Working Paper [working paper]: 565 stablecoin issuances of >= $1m, 7 stablecoins, Apr 2019 - Mar 2020; issuances follow market downturns ("negative price trend stops on the day before issuance"); USDT issuances show positive abnormal returns in the 24 h BEFORE issuance, HUSD/BUSD show significant positive abnormal returns AFTER; issuance size not significant; authors suggest arbitrage around peg deviations as a possible explanation, conclude stablecoins help price discovery. — [BRL summary](https://www.blockchainresearchlab.org/2020/06/24/how-do-stablecoin-issuances-affect-cryptocurrency-markets/); [BRL project page](https://www.blockchainresearchlab.org/portfolio/the-influence-of-stablecoin-issuances-on-cryptocurrency-markets/)
- Wei (2018), Economics Letters 171 [peer-reviewed]: Tether issuances did not affect subsequent Bitcoin returns (but did affect volume); daily data, Granger/VAR. — [IDEAS](https://ideas.repec.org/a/eee/ecolet/v171y2018icp19-22.html)
- Griffin & Shams (2020), Journal of Finance 75(4) [peer-reviewed]: Tether-funded purchases follow market drops and are associated with large BTC price increases, attributed to one large actor on Bitfinex; contested by critics (dip-buying/arbitrage) and denied by Bitfinex. This is a 2017-18 sample with a different market structure. — [SSRN 3195066](https://papers.ssrn.com/abstract=3195066); critique summarized in [Inverse / The Block coverage](https://www.theblock.co/post/7800/was-bitcoin-really-manipulated)
- Lyons & Viswanath-Natraj (2020) [working paper]: no systematic price effect of issuance; links to arbitrage — cited via [BRL WP No. 11](https://www.blockchainresearchlab.org/wp-content/uploads/2020/05/The_Influence_of_Stablecoin_Issuances_on_Cryptocurrency_Markets_BRL_Working_Paper_No_11.pdf)
- Chi, Chu & Hao, "Return and Volatility Forecasting Using On-Chain Flows in Cryptocurrency Markets", arXiv 2411.06327 (v2 Sep 2025) [working paper]: BTC/ETH/USDT on-chain flow data 2017-2023, 1-6 h intervals; USDT net inflows into exchanges positively predict BTC and ETH returns at several intervals (strongest at 1 and 2 h per search summary) and negatively predict BTC volatility at 6 h; BTC net inflows generally lack predictive power for BTC returns (except at 4 h). Effect sizes, out-of-sample results and costs NOT seen (PDF not extractable). — [arXiv abs](https://arxiv.org/abs/2411.06327)
- A 2025 survey notes the discrepancies across stablecoin-issuance studies likely stem from data granularity and method differences — [arXiv 2507.13883](https://arxiv.org/pdf/2507.13883)
- Survey also states that some studies argue stablecoin issuance is a reaction to crypto demand in bull markets rather than a cause — [arXiv 2507.13883](https://arxiv.org/pdf/2507.13883) (via search summary)
- CryptoQuant 2025 [vendor]: claims rising ERC-20 stablecoin supply (record >$160bn) preceded BTC upward moves in the 2021 bull market and 2024-25 recovery; no backtest; BTC then fell sharply from the Oct-2025 record above $125k (Nov 2025) despite record supply. — [FXStreet/CryptoQuant summaries via search](https://www.mexc.com/news/204707)
- Glassnode (2023) [vendor]: frames stablecoin supply growth as capital entering crypto; Stablecoin Supply Ratio (SSR) low = more buying power. No tested forecast. — [The Block](https://www.theblock.co/post/260640/total-stablecoin-supply-growth-signals-increased-capital-inflow-analysts-say)

### Inferences
- Mints are largely demand-driven (customers deposit USD, Tether/Circle mint) and often occur after drawdowns and for non-BTC uses (payments, DeFi, T-bill yield, emerging-market dollar demand), so the signal-to-noise for BTC at 1-48 h is poor, and post-2023 stablecoin supply growth is dominated by non-trading demand (inference; no source).
- Slow variant: 30-day stablecoin supply growth as a liquidity-regime context variable (weeks-months), not a trigger.
- Testable H-STB1: on dates of USDT Treasury mints >= $500m (public on-chain, timestamped to the minute — can be used without look-ahead), compute BTC return over +1 h/+4 h/+24 h vs matched non-mint hours and condition on prior-24 h return < 0. Success = mean abnormal return >0 with t>3 and >15 bp after costs. Prior: fails; ex-ante expected effect ~0 post-2020.
- Testable H-STB2 (more promising per Chi et al.): hourly net USDT inflow into major exchanges (requires labelled exchange-address data; paid/hard) vs next 1-2 h BTC return. Cannot be done on free data; needs CryptoQuant/Glassnode/Kaiko-grade labels.
- Verdict: stablecoin supply/mints: not useful for 1-48 h with free data; slow context only.

### Gaps
- No post-2022 peer-reviewed study of stablecoin supply growth vs BTC returns found; nothing on USDC specifically except an indirect 2026 USDC-depeg study summarized in search (returns Granger-cause depegs, not vice versa; not independently verified).
- Chi et al. effect sizes and out-of-sample performance unknown.
- Free data source for exchange-labelled USDT flows not identified.

## 3. Exchange inflows/outflows, reserves, whale transfers to exchanges

### Takeaway
Evidence is weak and mostly vendor-based. No peer-reviewed study found showing that BTC exchange inflows (including whale deposits) predict BTC returns at hours-days. The better-supported relationship is with VOLATILITY/volume, not direction. Exchange reserves are a slow-moving context variable, and the ETF era (custody via Coinbase Custody etc., off-exchange flows) likely weakened the interpretability of exchange reserves.

### Cited Findings
- Chi et al. (arXiv 2411.06327): BTC exchange net inflows generally lack predictive power for BTC returns at 1-6 h (exception: 4 h); BTC net inflows are negatively associated with BTC volatility across intraday intervals (as summarized in abstract). — [arXiv](https://arxiv.org/abs/2411.06327)
- Herremans & Low, arXiv 2211.08281 [working paper]: whale-alert tweets plus CryptoQuant daily data feed a transformer to forecast next-day volatility spikes; reportedly beats comparison models on extreme spikes; daily frequency, treats wallet-to-exchange transfers as bearish. Predicts volatility, not direction. — [arXiv](https://arxiv.org/pdf/2211.08281)
- Hazen, Philadelphia Fed Working Paper 26-42 [working paper]: whale alerts (BTC, ETH, WBTC) produce a brief ~24 h spike in BTC volatility, strongest after WBTC alerts; non-whale investors move in the same direction as whales. — [Philadelphia Fed](https://www.philadelphiafed.org/the-economy/banking-and-financial-markets/how-do-large-sophisticated-cryptocurrency-trades-impact-broader-defi-market-dynamics)
- Chainalysis study reported by Cointelegraph [vendor]: trading whales did not intensify volatility; they were net buyers in major 2017 and 2018 declines. — [Cointelegraph](https://cointelegraph.com/news/study-bitcoin-whales-are-not-responsible-for-volatility)
- CryptoQuant user guide "Whale Dumping" preset [vendor]: heuristic that high whale-linked inflow indicators imply bearish/sideways BTC; gives a threshold but no backtest or accuracy figure. — [CryptoQuant guide](https://dataguide.cryptoquant.com/quick-start/whale-dumping)
- CryptoQuant Exchange Whale Ratio (top-10 inflows / total inflows) hit 0.64 in 2026 (highest since 2015) read as bearish; a mid-2026 CryptoQuant report says rising average deposit size has been a stronger bearish signal than inflow volume; these are interpretive commentary without outcome statistics. — [FXStreet/CryptoQuant, Jul 2026](https://www.fxstreet.com/cryptocurrencies/news/bitcoin-whale-deposits-rise-as-exchange-inflows-flash-bearish-warning-cryptoquant-202607030103)
- Santiment commentary: inflow spikes "not preceded by a big outflow" tend to lead to price corrections; anecdotal. — [Santiment insights](https://insights.production.internal.santiment.net/read/how-bitcoin-s-exchange-inflow-and-large-transactions-can-easily-signal-profit-taking-opportunities-6278)
- Glassnode 2023: whale-origin volume accounts for ~41% of total exchange inflow volume (descriptive; shows dominance of few entities, and explains why the ratio is noisy). — [Glassnode Week On-chain 30/2023](https://insights.glassnode.com/the-week-onchain-week-30-2023)
- Coin Metrics: exchange flow metrics were overhauled with a daily human quality-control review and API status labels flagging manually reviewed/revised observations — i.e. the series is revised after the fact. — [Coin Metrics release note](https://coinmetrics.io/?p=2382)
- A Spark glossary quote of "0.47 correlation between net exchange inflows and next-day volatility" has no cited source; do not use. — [Spark](https://www.spark.money/glossary/whale)

### Inferences
- Big problems: (1) exchange address labelling is proprietary and incomplete, deposits to an exchange are often internal wallet shuffles or market-maker/arbitrage movements, and large OTC/custody moves are not sales; (2) depositors can sell, hedge a long via perps, or lend; (3) revised labels create look-ahead in historical backtests of vendor data (CoinMetrics note above); (4) post-2024 spot ETF custody and exchange-listed futures reduce relevance of exchange reserves (inference; no source found quantifying).
- Because the evidence points to volatility rather than direction, a more defensible use is a volatility-regime/risk-sizing flag: large inflow/whale ratio spike -> expect elevated 24 h range.
- Testable H-EXF1 (free data, CoinMetrics community native-unit exchange inflows; daily): flag days where aggregate exchange inflow (BTC) is above its 90-day 95th percentile, test next-day |return| and next-day realized range vs unconditional (volatility prediction) and next 1-3 day signed return. Success = realized range ratio >1.2 with p<0.01 on the 2024-2026 sample; for direction, require negative mean return with t < -2.5 and hit rate >55% on non-overlapping events after 10 bp costs. Caveat: use as-first-published (flash) snapshots only — capture snapshots daily going forward, because historical pulls are revised.
- Verdict for signed direction at 1-48 h: not supported. For volatility timing: weakly plausible, worth a test.

### Gaps
- No peer-reviewed BTC-specific study of exchange netflow/reserve -> returns at hourly/daily horizon located.
- No documentation found for CoinMetrics "flash" flags in community data (see section 6).
- No quantification of how ETF custody changed exchange-reserve signal quality.

## 4. On-chain cycle metrics: SOPR / STH-SOPR, MVRV, MVRV Z-score, NUPL, realized price

### Takeaway
MVRV, MVRV Z, NUPL and realized price are slow valuation/cycle metrics: evidence supports them only over multi-month horizons and few cycles (essentially 3-4 independent tops/bottoms). SOPR/STH-SOPR is the only one in the group with a plausible days-scale behaviour (profit/loss realisation resets), but I found no rigorous test of its days-horizon predictive power and sources warn that signals are regime-dependent. None should be used as 1-48 h triggers.

### Cited Findings
- Grobys, Näsman & Sandretto (Elsevier, 2026) [peer-reviewed per search summary]: NUPL, MVRV Z-score and CVDD cycle-timing rules over three cycles (2013-2025) outperform buy-and-hold and Monte Carlo random-entry strategies; SOPR not included; cycle backtest, not clean out-of-sample; very few independent observations. — via search summary (primary page not fetched); related thesis: [Ca' Foscari master thesis](https://unitesi.unive.it/retrieve/cfabbce7-876c-4e67-acf2-0ee10c311c8d/Master_Thesis%20VRABII%20SIMION%20and%20FASANO%20GIOVANNI.pdf) reports similar results for NUPL and MVRV Z long signals vs buy-and-hold, also few cycles.
- Baquero & Menezes, "Bitcoin's Power Law: Weak Structure, Strong Forecasts", arXiv 2605.21316: walk-forward out-of-sample evaluation shows the in-sample best model (K=3 multi-sigmoid) is among the worst out-of-sample at long horizons — an overfitting caution. A search-tool summary also claimed this paper's Granger tests at 7-60 day lags show the asymmetry favours price -> on-chain metric (price leads metrics); I could NOT verify that from the PDF (text not extractable), so treat as unconfirmed. — [arXiv](https://arxiv.org/pdf/2605.21316)
- Glassnode docs, STH-SOPR: defined over spent outputs younger than 155 days; value spent divided by value created; "more reflexive" than SOPR with larger peaks/troughs; 155 days is a convention; transactions with lifespan < 1 h filtered (as aSOPR); no thresholds, latency or backtest given. — [Glassnode STH-SOPR guide](https://docs.glassnode.com/further-information/metric-guides/sopr/sth-sopr)
- Glassnode SOPR guide: in bear markets SOPR typically < 1 during local capitulations; a "reset" to 1 is not always required (2017 aSOPR went months without it, per FXStreet coverage). — [Glassnode SOPR guide](https://docs.glassnode.com/further-information/metric-guides/sopr/sopr-spent-output-profit-ratio); [FXStreet](https://www.fxstreet.com/amp/cryptocurrencies/news/bitcoin-bullish-outlook-intact-on-touching-40-000-again-but-glassnodes-sopr-hints-at-healthy-correction-202101150346)
- Personal blog rules (e.g. STH-SOPR 0.97 buy, 1.0 reset) exist but are unsourced/unverified — do not rely: [example](https://sites.google.com/view/decentralised-news/home/the-sopr-metric-explained)
- Glassnode on MVRV/SOPR: historically accurate patterns but no formal out-of-sample tests presented — [Glassnode Insights](https://insights.glassnode.com/dissecting-bitcoins-unrealised-on-chain-profit-loss)

### Inferences
- MVRV = market cap / realized cap; MVRV Z uses full-history std of market cap; both are by construction slow (realized cap changes slowly) and in-sample extreme thresholds (Z>7 tops, Z<0 bottoms) have decayed in each cycle (Z-tops fell from ~12 in 2013 to ~7 in 2021, ~3 in 2024-25) — this is general knowledge, not sourced here; treat thresholds as unstable. Horizon: weeks to months; at 1-48 h they add nothing beyond price itself (they are price-divided-by-slow-variable, so daily change is nearly perfectly correlated with the price return).
- SOPR/STH-SOPR is a function of the BTC price relative to cost basis of recently moved coins, so it is mechanically correlated with recent returns (reverse causality). Plausible days-scale effect: STH-SOPR dropping below 1 (capitulation) then crossing back above 1 as a local regime filter in bull phases, lasting days to a few weeks. Evidence quality: practitioner lore only.
- Testable H-SOPR1 (BGeometrics free tier, daily, ~7-day delayed -> BACKTEST ONLY, not live): in the 2022-2026 sample, condition on STH-SOPR < 0.99 followed by close above 1.00; measure BTC forward 3, 7, 14 d return vs all days; success = mean excess > 2% at 7 d, t>2.5 with non-overlapping events, N reported (expect N < 20, i.e. not statistically meaningful). Live use requires paid data.
- Testable H-MVRV1: not for 1-48 h. For slower context: Z-score/ratio percentile bucket vs 90-day forward return; success = monotone decile pattern out-of-sample on a walk-forward basis. Expect it to be mostly a regime label.
- Verdict: MVRV, MVRV Z, NUPL, realized price: NOT useful for 1-48 h (explicit). SOPR/STH-SOPR: not useful at hours; maybe a days-weeks regime filter but unproven, with a mechanical dependency on price.

### Gaps
- No rigorous out-of-sample study of SOPR/STH-SOPR at 1-14 day horizons found.
- Primary page for Grobys et al. 2026 not fetched; claims are from search summary.
- Could not verify price->metric Granger direction in arXiv 2605.21316.

## 5. Fear & Greed index and social sentiment: contrarian value at 1-7 days after costs

### Takeaway
Evidence is mixed and mostly low-quality. The alternative.me index is itself built from price-derived inputs (volatility 25%, momentum/volume 25%, dominance 10%, plus social 15%, Google Trends 10%), so it largely restates recent price action. The best available practitioner evidence suggests extremes are informative mostly on the greed side ("sell the greed") and only over longer horizons; peer-reviewed studies show both momentum-like and contrarian results and none credibly demonstrates a net-of-cost 1-7 day edge. Social sentiment predicts mainly at sub-hour to 24 h frequencies with effects too small to trade.

### Cited Findings
- Index construction (alternative.me): volatility 25%, market momentum/volume 25%, social media 15% (Twitter; Reddit not yet in live index), surveys 15% (currently paused), dominance 10%, Google Trends 10%; updated daily; free API with attribution; exact update time not stated on the page. — [alternative.me](https://alternative.me/crypto/fear-and-greed-index/)
- Virtus Interpress (Corporate Ownership & Control, 2024) [peer-reviewed, low-tier journal]: ARDL/ECM on monthly 2016-2021 data; index has positive long-run and short-run effect on returns (momentum-like, not contrarian). — [Virtus](https://virtusinterpress.org/How-does-the-Bitcoin-Sentiment-Index-of-Fear-Greed-affect-Bitcoin-returns.html)
- Springer chapter [peer-reviewed book chapter]: 20 large non-stablecoin cryptos 2018-2021; contrarian strategies on the Crypto Fear & Greed Index may beat passive holding (abstract-level; costs not stated in what I saw). — [IDEAS](https://ideas.repec.org/h/spr/eurchp/978-3-031-36286-6_16.html)
- Review of Behavioral Finance 2024: Granger tests of F&G on BTC/ETH returns (abstract only; findings not seen). — [Emerald](https://emerald.com/insight/content/doi/10.1108/RBF-08-2023-0224)
- Santiment-hosted news analysis, Jul 2026 [vendor/blog]: eight years of data, "sell the greed" holds better than "buy the fear," especially at extreme euphoria (page fetch failed; numbers not seen). — [analysis link](https://san-1510.aid.brainsum.com/news/analysis/cryptos-favourite-adage-half-fails-bitcoin-hits-extreme-fear)
- Guegan et al. (StockTwits, ~1m messages) [peer-reviewed per summary]: sentiment relates to Bitcoin returns up to 15-minute frequency, disappears at lower frequencies, effect too small for economic profit. — via [search summary result](https://isidore.science/document/10670/1.8a15e4d00e2c21a356028e9e7690629c9b7fa7ef)
- Mai et al. (2015, Royal Society Open Science): social-media-based BTC strategies profitable after risk and trading costs (2013-14 sample, early market) — via [search summary](https://ar5iv.labs.arxiv.org/html/1506.01513) (this link is a different arXiv ID; treat the citation as unverified).
- Haase et al. (2025, Electronic Markets): 28,000+ explicit crowd buy/sell recommendations from X, Reddit, Stocktwits, Telegram predict short-term moves mainly for small-cap/recently negative-return coins; out-of-sample strategy has better risk-adjusted returns — [IDEAS](https://ideas.repec.org/a/spr/elmark/v35y2025i1d10.1007_s12525-025-00815-6.html). BTC is large-cap, so the finding is weaker for BTC.
- Gao et al. (2021): bullish sentiment foreshadows higher BTC return and volatility within 24 h (via search summary; primary not verified). A Norwegian thesis found Twitter sentiment follows price, no Reddit-price link — [BI Open](https://biopen.bi.no/bi-xmlui/handle/11250/3035684?show=full)
- Baquero survey/preprint "Bitcoin Price Prediction: Peer-Reviewed Evidence and Social Media Discourse": daily predictability real but does not extend to hourly or monthly horizons and may not survive costs (search summary). — [arXiv 2606.00071](https://arxiv.org/pdf/2606.00071)

### Inferences
- Because the index contains price-based components (>=60% by weight: volatility, momentum/volume, dominance), "extreme fear" is largely "BTC fell hard recently"; any contrarian edge is essentially short-term-reversal/capitulation-bounce, which can be tested directly on price without the index.
- Hypothesis H-FG1: for F&G <= 20 (or <=15) at daily value d, buy at the next 00:00 UTC (not same-day, to respect publication time), hold 3 and 7 days; short side F&G >= 80 symmetrical. Success = mean forward return exceeds unconditional by >1.5% over 7 d, t>2.5 on non-overlapping events (cluster events within 10 days), after 10 bp costs, in 2018-2026 walk-forward; require a result for the 2024-2026 subsample separately (ETF era). Expect N small (tens), outcome uncertain; "greed" side more plausible per Santiment analysis.
- Hypothesis H-FG2: 1-3 day change in F&G (e.g. fall by >25 points within 3 days) as a capitulation indicator for 24-72 h rebound; compare to a pure price filter (3-day return < -8%). If the F&G rule does not beat the price-only rule, drop it.
- Social sentiment (Twitter/Reddit volume): intraday effects exist in the literature but tiny and require paid real-time feeds and robust bot filtering; not usable with the free data stack.
- Verdict: F&G is not a validated 1-48 h predictor; at 3-7 days the extremes are the only place a conditional edge could be found; social sentiment not useful for 1-48 h without paid feeds.

### Gaps
- Did not obtain numeric forward-return tables for F&G buckets from any primary source.
- No ETF-era (2024-2026) peer-reviewed sentiment test found.
- Mai et al. citation and Gao et al. figures not verified at the primary source.

## 6. Publication lag and look-ahead risk (what can be used without look-ahead)

### Takeaway
Only data with a known, immutable timestamp is safe. Farside flows are post-close estimates (can be revised); CoinMetrics community values for recent days can be revised and exchange flow metrics have a documented revision process; BGeometrics free tier excludes the latest 7 days for MVRV/SOPR/NUPL/realized price, so it cannot be used live. The Fear & Greed daily value is available daily with an unspecified update time and revisions are not documented, so historical backtests must lag it conservatively.

### Cited Findings
- Farside: table is automated and "speed-first," includes estimates and "is likely to contain errors," draws on issuer websites and third-party providers; no stated posting schedule found. Third-party prediction markets that resolve on Farside treat a day as final once all issuers have published, and resolve on available data if an issuer is still missing 2 days later (market rules, not Farside's). — [Farside Bitcoin ETF flow table](https://farside.co.uk/?p=997)
- BGeometrics (bitcoin-data.com) free tier: 8 requests/hour, 15/day; free data covers the last 4 years, daily; changelog v1.7 (Sep 2026) says the most recent 7 days of MVRV, SOPR, NUPL and Realized Price endpoints require a paid plan; free/unauthenticated calls receive the latest data outside that 7-day window; `/last` returns `delayed: true`; terms warn data may have delays or inaccuracies. The 7-day restriction appears only in the changelog; verify on the live API. — [BGeometrics changelog](https://portal.bgeometrics.com/bguser/changelog); [free features](https://portal.bgeometrics.com/bguser/free-features.html); [terms](https://bgeometrics.com/terms)
- Coin Metrics: exchange-flow metrics have a daily human QC process and an API with status labels marking observations manually reviewed and revised; Community data includes MVRV Free Float and aggregate exchange flows. — [Coin Metrics exchange flows release](https://coinmetrics.io/?p=2382); [community data expansion](https://coinmetrics.io/?p=8064)
- Alternative.me: daily update; API `limit=0` returns full history; exact intraday update time not on page. — [alternative.me](https://alternative.me/crypto/fear-and-greed-index/)

### Inferences
- Farside daily flow for US day t is known only after the US close (evening ET, up to ~next morning for late issuers); the earliest tradable point is the next day's session start, by which time much of the next-day move overlaps. In backtests, shift flow by at least +1 day and treat its value as of first publication (scrape-and-store snapshots going forward).
- CoinMetrics: record each value with its fetch timestamp; do not backtest on a fresh pull of the whole history as if it had been known in real time.
- BGeometrics free values lag 7 days: suitable only for research/context, never for 1-48 h decisions.
- F&G: in backtests, use day d's value only for trades starting d+1 00:00 UTC unless the publication time is verified.
- Summary of usability for 1-48 h with free data: ETF flows (usable only as lagged context and day+1 test), exchange flows (CoinMetrics daily, snapshot-needed), MVRV ratio (CoinMetrics; slow context only), MVRV Z/NUPL/SOPR (BGeometrics; research only), F&G (usable, but redundant with price).

### Gaps
- Farside publication time of day and revision frequency: not found in sources.
- CoinMetrics "flash" label documentation and exact latency of community data: no source found despite two searches (coverage page redirected; FAQ not retrieved).
- Alternative.me update time (UTC) and any historical value revisions: not documented in what I fetched.

## 7. Decay and regime change 2023-2026 (ETF era)

### Takeaway
Evidence consistently indicates that flow information shifted from on-chain/exchange venues to regulated vehicles (ETF, futures) after Jan 2024, and that price-driven (reverse-causal) behaviour is prominent in ETF flows. I found no source that directly measures the decay of exchange-flow or stablecoin-mint signals over 2023-2026; these claims are inference.

### Cited Findings
- ETF flow data in the post-approval era: performance chasing dominates; flows have little incremental predictive content once lagged returns are in the model (Concordia thesis), flows own persistence plus last-day BTC return are the only robust drivers (Bitwise) — see section 1 sources.
- Most BTC price change occurs outside ETF hours (Mazur & Polyzos) — [ZU Scholars](https://zuscholars.zu.ac.ae/works/7267)
- Stablecoin supply reached record highs yet BTC fell sharply after Oct-2025 record, per the CryptoQuant-linked coverage — [coverage](https://www.mexc.com/news/204707)
- Whale deposit signals still widely published by CryptoQuant in 2026 as bearish (Exchange Whale Ratio 0.64, highest since 2015), no outcome data — [FXStreet Jul 2026](https://www.fxstreet.com/cryptocurrencies/news/bitcoin-whale-deposits-rise-as-exchange-inflows-flash-bearish-warning-cryptoquant-202607030103)

### Inferences
- Any test must be split pre-2024 vs post-2024 samples; a signal that works only in 2017-2023 (e.g. Chi et al. sample ends 2023) cannot be assumed to survive.
- Overall ranking for 1-48 h BTC trading usefulness with the free stack (my judgment): (1) none strong; (2) exchange inflow spikes for volatility timing; (3) ETF flow as lagged regime filter; (4) F&G extremes as 3-7 d context; (5) stablecoin mints, MVRV/NUPL/MVRV Z, social sentiment: not useful for this horizon.

### Gaps
- No source quantifying decay of exchange-flow or stablecoin signals in 2024-2026.
- No independent 2026 peer-reviewed update on ETF flow predictability after the Oct-2025 drawdown.
