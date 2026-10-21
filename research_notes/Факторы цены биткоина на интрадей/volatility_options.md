# Volatility and options-market factors as short-horizon (1 h to a few days) predictors of BTC price and volatility

Research date: 2026-10-21. Evidence-quality tags used below:
- [A] peer-reviewed or working paper with a stated sample and method (abstract or full text actually read).
- [B] thesis, single unreviewed study, or paper known only from secondary summaries.
- [C] practitioner/vendor/news commentary without a reproducible method.
- [M] from my own background knowledge, NOT verified in this session (no URL). Treat as unverified.

Overall caveat for the report writer: the web-search tool returned mostly summaries; several primary papers were not retrievable (PDF binary, 403). Where only a secondary summary was seen, it is flagged. I found NO rigorous, published, out-of-sample test of DVOL, the IV-RV spread, put/call ratio or max pain as short-horizon (<=1 week) BTC return predictors. The evidence base for this whole topic is thin; most "signals" are untested lore.

---

## 1. Does DVOL level/change or the IV-RV spread (variance risk premium) predict next-day / next-week BTC returns or realized volatility?

### Takeaway
DVOL is a 30-day forward-looking implied vol index; BTC's variance risk premium (IV above RV) is positive on average and larger in calm regimes, but I found no rigorous published test that DVOL or the IV-RV spread predicts next-day/next-week BTC returns, and only weak/ambiguous evidence about its incremental value for forecasting realized volatility over HAR-type benchmarks. This area is best treated as "hypothesis to test on own data", not "established".

### Cited Findings
- Definition: Deribit describes DVOL as a 30-day annualized implied volatility measure built from the options smile across relevant expiries, forward-looking. A 2023 Deribit research note flagged a rising implied/realized ratio as a sign that options price in more near-term volatility than recently realized. (Seen via search summary only, not the page itself.) — [Deribit Insights](https://insights.deribit.com/?p=44171), [Deribit Insights](https://insights.deribit.com/?p=1813) [C]
- Practitioner conversion rule: divide DVOL by about 20 to get the implied 1-day move in % (DVOL 100 -> about 5%/day); the exact factor is sqrt(365) = 19.1 for a 365-day calendar. — [TradingView idea on DVOL](https://www.tradingview.com/ideas/dvol) [C]
- Vendor definition of VRP = DVOL minus trailing 30-day realized vol of daily log returns (Binance candles); this is a comparison, not a forecast test. — [Oanor DVOL/VRP API](https://www.oanor.com/tag/dvol) [C]
- Bitcoin VIX construction: Alexander and Imeraj built a model-free (VIX-style variance swap) Bitcoin implied-vol index from >7 million Deribit option prices at 15-min sampling, Mar 2019 - Mar 2020, and studied its variance risk premium. Abstract details of results were not retrievable (403). — [Sussex repository](https://sro.sussex.ac.uk/id/eprint/91094/), [Sussex figshare](https://sussex.figshare.com/articles/journal_contribution/The_Bitcoin_VIX_its_variance_risk_premium/23306975) [A, results unread]
- Magnitude of BTC VRP (Deribit options Jul 2017 - Dec 2022, 27-day options): annualized risk-neutral variance 0.72 vs physical variance 0.58, i.e. BVRP = 0.14 overall; 0.12 in the high-vol regime, 0.17 in the low-vol regime. Risk-neutral variance 0.86 (HV) vs 0.46 (LV); physical 0.74 (HV) vs 0.29 (LV). Regimes found by Ward clustering of risk-neutral densities; variance explains ~69% of cluster separation. The paper reports NO forecasting regressions — it is descriptive and uses full-sample (not out-of-sample) clustering. The paper's own sample sizes are internally inconsistent (1,992 vs 1,301 days). — [Almeida, Grith, Miftachov, Wang, arXiv 2410.15195v2](https://arxiv.org/html/2410.15195v2) [A, descriptive]
- Same authors' line of work: the ~2% S&P 500 VRP comparison is cited for scale (BTC VRP far larger). — [HU Berlin edoc: Pricing Kernels and Risk Premia implied in Bitcoin Options](https://edoc.hu-berlin.de/18452/27204) [A, secondary summary]
- Volatility forecasting benchmarks: a Deribit-based horserace (BTC spot, HIST/EMA/ARCH/GARCH/EGARCH) finds GARCH and EGARCH much better than HIST/EMA in- and out-of-sample; implied vol appears only in a delta-hedged trading strategy that trades the spread between the GARCH forecast and option-implied vol and reports robust profits. NOTE: a search-engine summary claimed this paper shows "option implied volatility does not forecast future realized volatility well" — the abstract I fetched does NOT say that; treat that claim as unverified. Sample period not shown in the retrieved abstract. — [arXiv 2010.07402](https://arxiv.org/abs/2010.07402) [A]
- HAR-RV with jumps on Bitcoin futures (Dutta 2024): jump-induced volatility adds incremental information beyond the Bitcoin implied volatility index (so the index is used as a benchmark; standalone accuracy not reported in what I saw). — [Springer, Annals of Data Science (s40745-024-00517-4)](https://link.springer.com/article/10.1007/s40745-024-00517-4), [Osuva PDF](https://osuva.uwasa.fi/bitstream/10024/16910/2/Osuva_Dutta_2024.pdf) [A, summary only]
- HAR beats GARCH for BTC realized-vol forecasting (Aganin et al., HSE Economic Journal 2023); a 5-day BTC RV HAR benchmark has adjusted R2 of only ~9.3% (15.5% with a prediction-market signal added) in a 2026 arXiv paper — useful as a reminder that incremental R2 for 5-day RV is small. — [HSE](https://ej.hse.ru/article/view/29162), [arXiv 2604.01431](https://arxiv.org/pdf/2604.01431) [A]
- A late-Oct-2025 DVOL spike above 70% is reported by a secondary source (MEXC news), with the note that DVOL staying rich vs RV means option sellers earn carry. — [MEXC news](https://www.mexc.com/news/148177) [C]

### Inferences
- Because DVOL has a fixed 30-day horizon, its information for a 1h-3d horizon is mostly "current level of the vol state". It will largely overlap with trailing RV (volatility persistence). Any edge must come from the DVOL-minus-HAR-forecast residual, not from DVOL alone. I'd expect DVOL level to add modest, not large, R2 to a HAR model for 1-5 day RV (inference; no test found).
- The VRP being larger in calm regimes (0.17 vs 0.12) implies that "DVOL high relative to RV" is the normal state in quiet markets; the spread's information content for direction is likely nil-to-small. Direction effects, if any, would come through vol spikes coinciding with sell-offs (leverage effect; contemporaneous, not predictive).
- DVOL changes coincide with price moves (negative correlation with returns in selloffs), so a naive lead-lag test between DVOL change and next-hour return may only capture microstructure lag (DVOL computed from option quotes updating slower than perp/spot). Needs strict timestamp alignment and test on non-overlapping horizons.

### Testable hypotheses (concrete)
- H1a (vol forecast, 24h): Using hourly DVOL (2021-03 onward) and hourly BTC perp/spot returns, estimate a walk-forward HAR-RV baseline for next-24h realized vol (sum of squared hourly returns). Add regressor X = log(DVOL/sqrt(365) daily-equivalent) minus log(trailing 7d RV daily-equivalent). Success: out-of-sample QLIKE (or MSE on log-RV) improvement vs HAR baseline with Diebold-Mariano |t| > 2, stable across 3 subperiods (2021-22, 2023, 2024-26). Expected sign: positive (higher implied than realized -> RV rises toward it), but magnitude likely small.
- H1b (vol forecast, 3d/7d): same as H1a but horizons 72h and 168h; compare gain in OOS R2; expect larger gain at longer horizons because DVOL horizon is 30d.
- H1c (direction, 24h): Spearman IC between 24h DVOL change (z-scored over rolling 90d) and the NEXT 24h return (start measurement 1h after DVOL observation to avoid lag artifacts). Success: |IC| >= 0.05 with Newey-West |t| >= 3 (stringent because of multiple testing) and same sign in at least 3 of 4 years. Prior: expect null.
- H1d (spike fade): after a DVOL 24h jump above its rolling 95th percentile, the following 72h RV is lower than the pre-spike DVOL implied value (i.e., IV overshoot). Success metric: median (RV_72h_annualized / DVOL_at_spike) < 0.9 with bootstrap CI excluding 1 and mean-reversion in DVOL of >= X vol points over 3d.

### Gaps
- No peer-reviewed out-of-sample test of DVOL predicting next-day/next-week BTC returns or RV found.
- The Alexander-Imeraj Bitcoin VIX abstract/results were not retrievable (403), so their VRP sign/size and predictive content are unknown here.
- No 2024-2026 study of DVOL changes after ETF launch; no data on whether the VRP shrank after IBIT options (launched late 2024 per task statement; not verified by source here).

---

## 2. Options expiries: pinning / max-pain effects and volatility around Deribit expiries (Friday 08:00 UTC; monthly/quarterly)

### Takeaway
There is one recent peer-reviewed-style study (Weiss et al., Finance Research Letters, 2026) finding an intraday pre-expiry dip followed by a reversal in a specific high-open-interest, negative-gamma condition (sample 2021-2023), but I could only see press summaries, and a 2026 single-expiry check by a news outlet did not confirm it under public data. Max-pain "pinning" for BTC has only anecdotal and mixed commentary support — no rigorous test found.

### Cited Findings
- Settlement mechanics: Deribit options settle Friday 08:00 UTC; delivery price is a time-weighted average of Deribit's index over the last 30 minutes (so a single-print manipulation is dampened, and any "pinning" would act in the 07:30-08:00 window). — [Decrypt](https://decrypt.co/376752?amp=1), [Yahoo/crypto options article](https://finance.yahoo.com/news/3-16-billion-crypto-options-052603341.html) [C, via search summary]
- Weiss et al., "Bitcoin option expiration, gamma exposure, and intraday price reversals", Finance Research Letters vol. 107 (Sept 2026), art. 110340 (DOI 10.1016/j.frl.2026.110340). As described in press: 1,059 Deribit expiry days Jan 2021 - Dec 2023, 5-minute returns; statistically significant tendency for BTC to FALL in the hour before expiry and REVERSE over the following two hours when at-the-money open interest is in the top decile; strongest when a reconstructed cumulative gamma proxy is negative; the market-maker proxy is built from contract trade history with trade-initiator assumptions (not from total OI or put/call ratio), following a related SSRN methodology paper (10.2139/ssrn.5012508, which I could not open: 403). I could not access the paper itself; effect sizes are unknown. — [CryptoSlate (study cited)](https://cryptoslate.com/?p=561776), [CryptoSlate: 2.24B expiry teased a reversal](https://cryptoslate.com/bitcoins-2-24-billion-friday-options-expiry-teased-a-reversal-then-gave-it-back-within-hours/) [B]
- CryptoSlate's own test on a Sept 2026 Friday expiry: BTC fell 0.16-0.18% from 07:00 to 08:00 UTC, rose ~0.19-0.21% by 09:00, then slipped back; by 10:00 UTC all three venues (Deribit perp, Coinbase, Kraken) were slightly below expiry-time levels. The journalist could not match the study's top-decile ATM-OI condition with public data, and three model dashboards (Optionly, CryptoGamma, ByKaranteli) did not show negative cumulative gamma near spot. One source dates this expiry Sept 11, another refers to Sept 25 — date unreconciled. A single event is not a test. — [CryptoSlate](https://cryptoslate.com/?p=561776), [CoinAlertNews](https://coinalertnews.com/news/2026/09/11/bitcoin-ethereum-options-expiry) [C]
- Max pain: no academic study found. Deribit's CEO has described max pain as a "gravitational pull" at major expiries; a Greeks.live 2023 piece said expirations stayed near max pain for an extended period; other outlets noted BTC far from max pain at a June expiry (e.g. well below a $72,000 max pain), and a news item citing Deribit says recent quarterly expiries have not consistently shown strong pinning. — [Benzinga](https://www.benzinga.com/markets/cryptocurrency/24/12/42655154/84000-is-bitcoins-worst-case-options-trading-firm-ceo-says), [Radom](https://www.radom.com/insights/bitcoin-has-yet-to-reach-the-anticipated-72000-level-as-a-significant-10-billion-in-options-approach-their-expiration-date), [FXStreet](https://www.fxstreet.com/amp/cryptocurrencies/news/bitcoin-options-worth-530-million-set-to-expire-on-friday-without-bear-market-end-in-sight-202308040840) [C]
- Equity analogue for pinning: from memory, Ni, Pearson and Poteshman (2005) found US stocks cluster at strikes with large open interest on expiration dates — NOT verified in this session (search did not return it) [M].
- Equity analogue for hedging flows: Baltussen, Da, Lammers, Martens (JFE 2021) show intraday momentum (first part of day predicts last 30 min) across 60+ futures 1974-2020, attributed to gamma hedging by option market makers and leveraged ETFs; reverses over following days. — [Hedging Demand and Market Intraday Momentum (Alpha Architect / EUR)](https://alphaarchitect.com/hot-topic-does-gamma-hedging-actually-affect-stock-prices/), [EUR repository](https://pure.eur.nl/en/publications/hedging-demand-and-market-intraday-momentum/) [A, summary]
- Alexander, Deng, Feng, Wan (J. Financial Markets 2023): Deribit tick data; ATM option prices largely set by volatility traders; OTM options by volatility and directional informed traders; directional effects strongest during the 2021 bubble; market makers manage inventory/imbalance better as volume grows. Relevant as evidence that option order flow carries some information, but it is not an expiry study. — [arXiv 2109.02776](https://arxiv.org/pdf/2109.02776), [IDEAS](https://ideas.repec.org/a/eee/finmar/v63y2023ics1386418122000544.html) [A]

### Inferences
- If the Weiss et al. effect is real it sits entirely inside a ~3-hour window (07:00-10:00 UTC Friday) on a subset of expiries (top-decile ATM OI, negative gamma): so even a significant effect would affect a small fraction of days. A generic "expiry day" dummy will likely dilute it.
- The study's sample (2021-2023) ends before US spot-ETF options (IBIT options launched late 2024 per the task brief) grew; Deribit's share of BTC options OI fell (see section 6), so the same condition measured only on Deribit may now represent a smaller part of total hedging flow. The Sept 2026 non-confirmation is consistent with decay but is a sample of one.
- Max-pain pinning evidence is anecdotal and subject to survivorship/narrative bias (media remember the hits). A proper test needs a placebo (random strike) comparison.

### Testable hypotheses (concrete)
- H2a (pre-expiry dip and rebound): On every Deribit Friday expiry (weekly/monthly/quarterly separately), compute r1 = log(P_08:00 / P_07:00) and r2 = log(P_10:00 / P_08:00) using Deribit index or Coinbase 1-min data. Compare to the same windows on non-expiry Fridays (and on other Fridays' 08:00 as placebo). Success: mean(r1) < 0 and mean(r2) > 0 with block-bootstrap |t| >= 2.5, stronger on monthly/quarterly expiries and robust in 2024-2026 subsample; economic threshold: |mean| > 15 bps (fees/slippage).
- H2b (expiry volatility): Realized vol of 5-min returns in 07:30-09:00 UTC on expiry Fridays divided by same-window RV on non-expiry Fridays (and same-window RV on Thursdays). Success: ratio > 1.2 with permutation p < 0.05; check whether quarterly (last Friday of Mar/Jun/Sep/Dec) ratio > weekly ratio.
- H2c (max-pain pinning, forward only): Snapshot Deribit book summary (OI per strike) at T-24h and T-2h for each future expiry; compute max pain M. Test |S_settle - M|/S versus |S_settle - K_random|/S with K_random drawn from strikes with similar OI rank; success: median distance to M is lower than random strikes with permutation p < 0.05 over >= 30 monthly/quarterly expiries. Also test drift: sign(M - S_T-24h) predicts sign(S_settle - S_T-24h) with hit rate > 55% (binomial p < 0.05). Note: needs live data collection since historical OI is not free; sample of 30 monthly expiries needs ~2.5 years — so also use weekly expiries (weekly max pain over many more events) and treat monthly as a subsample.
- H2d (backfill option using expired-instrument prices): the task notes expired option price history exists per instrument; use it to reconstruct per-expiry traded volume by strike (rather than OI) as a volume-based max-pain proxy for past expiries, and test H2c's distance metric on 2021-2026.

### Gaps
- Could not access the FRL paper or the SSRN methodology paper; effect size (bps), hit rates, and whether the effect persists post-2023 are unknown.
- No rigorous BTC max-pain study found.
- No systematic dataset of realized volatility around expiry vs non-expiry Fridays found.

---

## 3. Dealer gamma exposure (GEX): measurable effects in BTC, and how to estimate it from public data

### Takeaway
Theory (long gamma dampens, short gamma amplifies) is well established in equities (intraday momentum literature), but BTC GEX evidence is limited to one gated study of expiry reversals (Weiss et al., 2026) and vendor/case-study material (Glassnode) with no backtest. GEX is not observable — it requires assumptions about dealer sign — and Deribit-only GEX now covers a smaller fraction of total BTC options exposure.

### Cited Findings
- Mechanism and regimes: when dealers are net long options (positive GEX) they sell rallies / buy dips (dampen); when net short (negative GEX) they buy rallies / sell dips (amplify). — [Glassnode: Tracking Volatility Regimes - Gamma Exposure Heatmap](https://research.glassnode.com/gamma-exposure-heatmap) [C]
- Glassnode estimates BTC dealer GEX with an "internal methodology" using a taker-flow approach (the page doesn't give formulas; Deribit appears to be the data source). Case-study readings (published Feb 2026): Aug-Nov 2025 mostly negative total GEX alongside a decline from ~120k to ~80k; Dec 2025-Jan 2026 positive GEX with choppy consolidation around ~85k "gamma walls"; late Jan 2026 negative again. The author suggests zero-crossings in total GEX may mark volatility inflection points, but explicitly calls it a limited case study with no backtest, hit rate or statistical validation. — [Glassnode](https://research.glassnode.com/gamma-exposure-heatmap) [C]
- Estimation caveat: Deribit publishes aggregate OI, not who is long/short; gamma-flip levels therefore depend on an assumption of which side dealers hold; some models infer it from trade-initiator (taker) flow. — [CryptoSlate](https://cryptoslate.com/?p=565159), [CryptoSlate](https://cryptoslate.com/?p=561776) [C]
- Weiss et al. (FRL 2026) is the only BTC study found that conditions on a reconstructed cumulative-gamma proxy built from trade history: intraday reversal is strongest when the proxy is negative (see section 2). [B]
- Equity evidence: Baltussen et al. show the sign of gamma-hedging flows creates intraday momentum in 60+ futures, consistent with hedging of short-gamma positions; the effect reverts over following days. — [Alpha Architect](https://alphaarchitect.com/hot-topic-does-gamma-hedging-actually-affect-stock-prices/), [EUR](https://pure.eur.nl/en/publications/hedging-demand-and-market-intraday-momentum/) [A, summary]
- Vendor pages claim RV undershoots IV in positive-gamma stretches and the reverse in negative gamma, without sample or method shown. — [FlashAlpha BTC GEX](https://flashalpha.com/stock/btc) [C]; note these pages cover ETFs (e.g. IBIT-like funds), not Deribit.
- Dealer positioning is inferred, not observed (Glassnode disclaimer). — [Glassnode](https://research.glassnode.com/gamma-exposure-heatmap) [C]

### Inferences
- A defensible public-data GEX proxy: for each Deribit strike/expiry, gamma_i = BS_gamma(S, K, T, sigma_i) with sigma_i = mark_iv from the book summary; GEX = sum over i of OI_i * gamma_i * S^2 * 0.01 * sign_i, with sign_i from an assumption (common retail-flow assumption: dealers long puts? or short calls/long puts -- conventions differ; sign must be tested, not assumed). Alternative sign-free "gross gamma" = sum OI*gamma (magnitude only) plus the flip level; and a trade-based sign from the taker side of each trade (Deribit trade feed gives direction), which is what the Weiss/Glassnode approaches roughly do.
- Gamma matters most for short, near-the-money expiries (gamma ~ 1/sqrt(T)); weekly/0-1 day-to-expiry ATM OI dominates GEX on Thursday-Friday, which makes the expiry window (section 2) the natural test bed.
- The ETF-options migration means Deribit-only GEX may be a partial and biased measure (IBIT options OI exceeded Deribit's in early 2026; see section 6), and IBIT options hedging happens through ETF/CME/spot channels on US market hours (inference, no source).

### Testable hypotheses (concrete)
- H3a (forward-only, needs live collection): Snapshot book summaries hourly; compute gross gamma and a signed GEX proxy. Test whether next-24h realized vol (5-min returns) is lower when proxy GEX is in the top tercile vs bottom tercile after controlling for DVOL and trailing RV. Success: coefficient on GEX tercile significant at |t| >= 2.5 on at least 6 months of data (about 4000 hourly obs, ~180 daily obs, so effective n small; use daily obs and HAC SEs); effect >= 10% relative difference in RV.
- H3b (trade-based gamma): using Deribit historical trades, reconstruct taker-signed cumulative gamma for 0-7 day options, per Weiss et al.'s approach, and replicate their expiry-window reversal on 2021-2026 with a post-2024 split. Success: reversal effect in post-2024 sample of same sign and at least half the magnitude of 2021-2023.
- H3c (flip level): distance of spot to the nearest gamma-flip strike (in % of spot) as a predictor of next-24h absolute return; success: monotonic relation with Spearman >= 0.08 and p < 0.01 out-of-sample.

### Gaps
- No peer-reviewed validation of GEX as a BTC volatility predictor outside the expiry window.
- Glassnode's exact methodology and any hit-rate not public.
- No free historical OI-by-strike data on Deribit, so any GEX study before data collection starts must use trade-based reconstruction.

---

## 4. Skew / risk reversals (25-delta RR) and put/call ratios: do they predict returns?

### Takeaway
One 2026 SMU PhD dissertation finds that Deribit 25-delta risk reversals (and butterflies) predict BTC returns, but mainly at 30-180 day option tenors and a 90-day return horizon, with a signal that weakened around 2024. There is no evidence found for put/call ratio predicting short-horizon returns; commentary is contradictory (the same ratio has been called both bullish and bearish).

### Cited Findings
- Dissertation: Meng Hwee Neo (supervisor Jianfeng Hu), SMU, May 2026, "Bitcoin options risk-reversal predictability": daily Deribit data Apr 2021 - Dec 2025, 1,723 observations. In the primary 25-delta, 90-day specification the RR coefficient is significant at 1% in a 13-variable regression with Newey-West errors; most delta/tenor combinations significant, mainly in the 30-180-day tenor range; butterfly spread also predictive; adding controls raised t-stats (RR 1.91 -> 3.73; BF 2.13 -> 2.34). Around the start of 2024 (spot ETF approval, bull market, regulation) the predictive signal of the smile weakened, which the author reads as consistent with the adaptive markets hypothesis. I only saw the abstract; the return horizon in the abstract is the 90-day specification; the sign and short-horizon (<1 week) performance are not stated in what I saw. — [SMU Institutional Knowledge](https://ink.library.smu.edu.sg/etd_coll/887) [B]
- Pricing context: BTC skew behaves differently from equities — Deribit notes that BTC options often show positive skew for both calls and puts (calls can trade at a premium in rallies). — [Deribit Insights: Weekly commentary - it's all about skew](https://insights.deribit.com/industry/weekly-commentary-its-all-about-skew/) [C]
- Amberdata blog on reading RR/BF and the structural sign of the vol surface (the page redirected to the Kaiko-Amberdata news page and could not be read). — [Amberdata blog](https://blog.amberdata.io/the-smile-why-cryptos-skew-tells-a-story-equity-markets-never-will) [C, unread]
- LuxAlgo summary states research on risk reversals as directional signals is mixed and that they are better read as positioning/event-pricing; a KuCoin explainer claims RR-spot divergences lead trend reversals with no rigorous backing. — [LuxAlgo](https://www.luxalgo.com/library/concept/risk-reversals/), [KuCoin](https://www.kucoin.com/knowledge-base/Analysis/what-is-volatility-skew-analysis-in-crypto) [C]
- Put/call: Rouxelin et al. (Bitcoin futures options) report put/call volume ratio ~0.5 for BTC vs ~2 for S&P 500 options and that ATM call IV is positively related to BTC returns (contemporaneous, lottery-demand interpretation; not predictive). — [FGV abstract (Rouxelin)](https://eventos.fgv.br/sites/eventos.fgv.br/files/arquivos/u1314/abstract_florent_rouxelin.pdf) [A, abstract]
- Analyst claims: The Block has run pieces calling the Deribit put/call ratio both a bullish indicator and a bearish indicator in different periods; January 2024 commentary read a rising put share ahead of expiry as bearish; none include tests. — [The Block (bullish)](https://www.theblock.co/post/259818/bitcoins-put-call-options-ratio-a-bullish-indicator-for-the-market-says-analyst), [The Block (bearish)](https://www.theblock.co/post/274421/bitcoin-put-call-options-ratio-is-a-bearish-indicator-for-the-market-says-analyst) [C]
- Informed-flow link: Alexander et al. (2023) find OTM option prices reflect directional information from informed traders, strongest in the 2021 bubble — a plausible channel for RR predictiveness, but not a predictive-return test. — [arXiv 2109.02776](https://arxiv.org/pdf/2109.02776) [A]
- IBIT put/call context: Cointelegraph notes IBIT options show heavy put buying as protection with some call selling (hedging read, no testing). — [Cointelegraph](https://regional-front.cointelegraph.com/markets/bitcoin-options-under-fire-as-covered-calls-take-center-stage) [C]

### Inferences
- The only quantitative support (SMU) concerns long tenors and a long return horizon; for 1h-3d horizons the evidence is essentially absent. RR from short-dated (1-7 day) options mixes event-hedging (expiry, macro, FOMC) with directional demand and is likely noisier.
- Put/call OI ratio is a stock variable dominated by hedging/structured positions (covered-call sellers, put hedges); put/call volume is a flow variable and noisier. With contradictory commentary and no test, prior for short-horizon predictive power is low.
- Data constraint: Deribit's book summary gives live mark_iv per instrument, so 25-delta RR/BF can be computed going forward only; historical reconstruction is expensive (invert IV from expired-instrument prices).

### Testable hypotheses (concrete)
- H4a (RR, forward): Collect hourly 7-day and 30-day 25d RR (= IV(25d call) - IV(25d put)) from book summary; test whether a 24h change in RR (z-scored over 60d) predicts the next 24h and 72h BTC return. Success: Spearman IC >= 0.06 with HAC |t| >= 2.5 over >= 9 months, with consistent sign; a long/short tercile strategy gross Sharpe > 1 after 5 bps/trade costs.
- H4b (RR as vol predictor): Absolute RR level (or butterfly) as predictor of next 72h RV beyond DVOL. Success: OOS QLIKE improvement vs HAR+DVOL model with DM |t| > 2.
- H4c (put/call OI): daily put/call OI ratio (Deribit book summary) and its 7-day change vs next 24h/72h return; success: |IC| >= 0.05 with |t| >= 2.5, and the reversal sign (high put share -> positive next return) tested as the contrarian alternative. Expectation: null.
- H4d (backfill): reconstruct 7-day ATM IV and approximate RR on selected days from expired-instrument trade prices by inverting Black-Scholes (use the index price at trade time) — to extend H4a backwards at least to 2023-2024 and check the SMU post-2024 weakening at short tenors.

### Gaps
- SMU thesis: sign of the RR coefficient, short-horizon results and out-of-sample performance not seen; thesis not peer-reviewed.
- No study of put/call ratio predictiveness for BTC found.
- No free historical skew (as per task); Amberdata page unreadable.

---

## 5. Volatility regimes, clustering and compression -> expansion: evidence and a robust definition

### Takeaway
Volatility clustering/long memory in BTC is well documented, so "calm tends to follow calm, turbulence turbulence" for horizons of hours to days; but the folk idea that a low-vol compression predicts an imminent large move rests on anecdotal or hand-picked media examples with no out-of-sample test I could find, and gives no direction.

### Cited Findings
- Persistence: BTC high-frequency volatility shows long-lasting persistence with significantly autocorrelated squared/absolute returns over long lags; Component-GARCH best in-sample; BTC's intraday pattern lacks the typical equity/FX U-shape. — [Aalto thesis: Characteristics of Bitcoin Volatility at High Frequency](https://aaltodoc.aalto.fi/items/5e9415b1-e0e0-4d4c-bb56-88c7f1ef8b6b) [B]
- HAR-type models are the standard benchmark: HAR-RV captures heterogeneity/long memory (Bouri et al. 2020, hourly BTC Jul 2017 - Jun 2019); HAR beats GARCH on BTC (Aganin et al. 2023); jumps and structural breaks improve forecasts (EFM paper; Zhang Nottingham dissertation); a 2020-2025 multi-crypto HAR study finds the daily component dominates for BTC/ETH. — [Bouri et al. 2020 (Pretoria)](https://repository.up.ac.za/bitstream/handle/2263/76318/Bouri_Forecasting_2020.pdf?sequence=1), [HSE](https://ej.hse.ru/article/view/29162), [Nottingham](https://eprints.nottingham.ac.uk/57681), [vLex: jumps and structural breaks](https://eu.vlex.com/vid/forecasting-the-volatility-of-1049450990) [A, summaries]
- A 2026 arXiv preprint compares a long-memory Markov volatility model with HAR-RV on BTC realized variance from 1-minute Bitstamp data (Jan 2012 - Jan 2025), in- and out-of-sample (results not read). — [arXiv 2607.25189](https://arxiv.org/pdf/2607.25189) [A, unread]
- Regime structure in options: in the low-vol cluster, risk-neutral variance is 0.46 vs physical 0.29 (VRP 0.17), in the high-vol cluster 0.86 vs 0.74 (VRP 0.12) — implied vol overstates calm-regime variance more in relative terms (full sample, not out-of-sample). — [arXiv 2410.15195v2](https://arxiv.org/html/2410.15195v2) [A]
- Compression lore: CoinDesk pieces say weekly Bollinger Bandwidth near ~0.20 preceded volatility bursts in 2012, 2015, 2016 and 2018 (and a late-2023 episode); thresholds vary across sources (0.1 daily, 15, 20%), the signal gives no direction, examples look cherry-picked, and I found no out-of-sample backtest. — [CoinDesk Oct 2023](https://coindesk-coindesk-prod.cdn.arcpublishing.com/markets/2023/10/18/bitcoin-bollinger-bandwidth-signals-wild-price-swings-ahead/), [CoinDesk Aug 2024](https://coindesk.com/markets/2024/08/01/bitcoin-indicator-that-forewarned-late-2023-volatility-explosion-is-lighting-up-again), [FXCM](https://www.fxcm.com/au/insights/bitcoin-may-be-setting-up-for-a-significant-move/) [C]

### Inferences
- Because volatility is persistent AND mean-reverting around a slowly moving mean, "compression -> expansion" is partly a statistical truism (vol is below its mean, so it tends to rise); the real question is whether the conditional probability of a large move exceeds what a plain mean-reverting HAR/GARCH model already implies. That requires the test to be benchmarked against a vol model, not against the unconditional base rate.
- Robust definition of compression (to be tested): combine three measures to avoid single-indicator artifacts: (i) realized-vol percentile: 24h (or 72h) RV from 5-min returns in its lowest 10th percentile of the trailing 180 days; (ii) implied-vol percentile: DVOL in the lowest 10th-15th percentile of the trailing 180 days (DVOL gives forward-looking confirmation and is available hourly since 2021-03); (iii) duration: condition held for >= 24h consecutive (reduces noise). Use rolling-window percentiles (not full-sample) to avoid look-ahead; compare Bollinger bandwidth/ATR percentile as robustness checks.
- Large move definition: next-24h (or 72h) absolute return or high-low range exceeds 2x the trailing median range, or realized vol in the next window exceeds 1.5x the compression-window RV.
- Because vol regimes shifted around 2024 (ETF flows, lower unconditional vol), percentile-based (adaptive) thresholds beat absolute thresholds.

### Testable hypotheses (concrete)
- H5a: Condition C = [DVOL percentile (rolling 180d) <= 10 AND 24h RV percentile <= 10 for >= 24h consecutive]. Outcome: next-72h range |high-low|/open > 2 x trailing 180d median 72h range. Success: P(outcome | C) at least 2x the unconditional frequency and above what a walk-forward HAR-based prediction implies (compare via logistic regression with HAR forecast as control; the compression flag's coefficient must have |z| > 2.5) in each of 2021-22, 2023, 2024-26 subsamples; event count >= 30 non-overlapping episodes (cluster by 72h).
- H5b (direction neutrality check): After C, test whether sign of the first 4h breakout (close beyond the compression-window range) predicts the following 24h direction. Success: hit rate > 55% with binomial p < 0.05 over >= 40 events; expectation: null/weak.
- H5c (vol clustering baseline): confirm HAR-RV 24h forecast OOS R2 vs a naive "yesterday's RV" baseline on 2021-2026, and report the drop (if any) in R2 post-2024 as the benchmark for H1/H5.

### Gaps
- No rigorous published out-of-sample test of compression -> expansion for BTC; no standard definition.
- Recent (2024-2026) evidence on whether BTC volatility clustering has weakened with institutionalization not found.

---

## 6. Changes and decay 2023-2026 (options volume growth, ETF options) and free-data feasibility

### Takeaway
The BTC options market became larger and more institutional, and a significant share of exposure migrated from Deribit to US-listed IBIT options (crossing in April 2026, reversing in May 2026), so Deribit-only signals (max pain, GEX, put/call) capture a shrinking and time-varying share of total hedging flow; the only academic evidence on structural change (SMU) shows weakened smile-based predictability around 2024.

### Cited Findings
- Scale: Deribit BTC options OI ~ $45B and IBIT options ~ $7B in July 2025; $57B total BTC options exposure reported July 2025. — [The Block, Jul 2025](https://www.theblock.co/news/markets/2025-07-30-bitcoin-options-exposure-tops-57-billion-amid-soaring-institutional-hedging-demand-364442) [C]
- Migration: by late Sept 2025 IBIT options OI nearly $38B vs Deribit $32B; IBIT reached 52% of total BTC options OI in January 2026 (all-time high for a single venue); Deribit's share fell below 39% in early 2026; April 2026: IBIT options OI $27.61B edged past Deribit $26.90B (Volmex); May 21, 2026: Deribit back on top at $31.3B vs IBIT $27B. Sources differ on exact numbers and dates (the July 2025 "$45B" vs Sept 2025 "$32B" Deribit figures are mutually inconsistent in dollar level, likely different measurement dates/notional definitions) — treat as approximate. — [KuCoin blog](https://www.kucoin.com/blog/th-ibit-options-oi-vs-deribit-wall-street-bitcoin), [Whale Alert story](https://whale-alert.io/stories/dcb701f9a91f66/Deribit-Bitcoin-options-open-interest-rises-to-313B-topping-BlackRock-IBIT-ahead-of-a-625B-expiry), [KuCoin 2026](https://www.kucoin.com/fil/blog/ae-Blackrock-IBIT-Options-Growth-Overtakes-Deribit-in-2026), [CoinPerps stats](https://www.coinperps.com/learn/crypto-options-statistics) [C]
- SMU thesis reports weaker smile-based predictive signals around the start of 2024 (ETF approval, bull market, regulation). — [SMU](https://ink.library.smu.edu.sg/etd_coll/887) [B]
- Weiss et al. sample ends Dec 2023, i.e. before IBIT options; a single Sept 2026 expiry check did not reproduce the expected condition under public data. — [CryptoSlate](https://cryptoslate.com/?p=561776) [B/C]
- Expiry flow commentary persists in news (e.g. $10B-$30B notional "expiry" headlines around Dec 2025 quarterly), but these are narratives without systematic tests. — [Whale Alert story on Dec 26 expiry](https://whale-alert.io/stories/c171d6c91f2d/Bitcoin-stuck-in-85k90k-range-as-27B-options-expiry-on-Dec-26-expiry-skew-and-gamma-suggest-resolution-toward-mid90k-max-pain-96k) [C]

### Inferences
- Treat 2021-2023 and 2024-2026 as separate samples in every backtest; report a pre/post-Nov-2024 (IBIT options launch) split. Expect effects estimated on early samples to be smaller later (adaptive markets / crowding / more passive vol selling via covered-call ETFs, inference).
- Additional timing consideration (inference, no source): US-listed IBIT options expire Friday around US market close (16:00 ET), a different clock from Deribit's 08:00 UTC; consider an additional event window around US monthly expiry (third Friday) rather than only Deribit's.
- Free-data plan consistent with the brief: (1) DVOL hourly since 2021-03 supports H1, H5 with full history; (2) expired-instrument price/trade history supports H2 and (with IV inversion) a reconstruction of H4 for selected dates; (3) live book summary requires start of logging now for H2c, H3a, H4a, H4c (max pain, gross gamma, put/call OI, mark_iv skew); decisions on these signals will be possible only after ~6-12 months of accumulated data.
- Multiple-testing risk: this note proposes ~15 hypotheses; use a pre-registered holdout (e.g., 2025-07 onward) and require |t| >= 3 (or Benjamini-Hochberg adjustment) before trading anything.

### Gaps
- No primary-source data (SEC/OCC/Deribit) for options OI and volumes; all migration figures come from news/aggregators and are internally inconsistent in places.
- No study of how the VRP, skew predictability, or expiry effects changed after IBIT options launch beyond the SMU abstract.
- IBIT option expiry timing and its interaction with Deribit flows is my inference only.
