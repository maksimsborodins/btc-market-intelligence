# Oligator variants

Binance BTCUSDT perp, 1h Alligator + fractals, entries from 2020-09-01, real funding, exit = fractal trail unless stated. R = result / $10 after costs. DEV = entries 2020-09..2023-12, HOLDOUT = 2024-01..now. Range colour = traffic light of the walk-forward 24h range forecast (btcmi/range_model.py) at the last hourly close before the entry; the forecast exists from 2021-02 (earlier trades are "none"). V1/V1b skip the signal when the colour differs (so the position slot is free for the next signal). V2: limit order at the fractal level after the breach, filled only on a strictly-through trade, maker fee, no slippage; the slot is busy while the order is pending. V4: 4h Alligator mouth open in the trade direction on the last completed 4h bar. V5: exit at the first 1h close beyond the 1h teeth (initial stop still applies).

## V0_base

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV 2020-09..2023 | 1274 | 31.9 | 31% | -0.047 [-1.4] | -60.3 | 0.88 | 97.4 | +0.033 [1.0] | 0.081 | 2.51% | 13% |
| HOLDOUT 2024..now | 990 | 29.4 | 30% | +0.014 [0.3] | +13.4 | 1.03 | 39.8 | +0.110 [2.3] | 0.096 | 1.84% | 16% |

## V1_only_green

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV 2020-09..2023 | 188 | 6.0 | 34% | -0.084 [-1.5] | -15.8 | 0.73 | 20.2 | -0.044 [-0.8] | 0.040 | 4.86% | 1% |
| HOLDOUT 2024..now | 337 | 10.3 | 31% | -0.042 [-0.7] | -14.1 | 0.88 | 20.0 | +0.015 [0.3] | 0.057 | 2.99% | 3% |

## V1b_only_red

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV 2020-09..2023 | 658 | 20.6 | 30% | -0.065 [-1.3] | -42.8 | 0.85 | 52.6 | +0.037 [0.8] | 0.102 | 1.90% | 22% |
| HOLDOUT 2024..now | 449 | 13.6 | 28% | +0.018 [0.2] | +8.3 | 1.04 | 40.5 | +0.143 [1.7] | 0.125 | 1.34% | 29% |

## V2a_limit_retest_4h

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV 2020-09..2023 | 1212 | 30.3 | 27% | -0.095 [-3.0] | -115.4 | 0.75 | 136.4 | -0.045 [-1.4] | 0.051 | 2.69% | 5% |
| HOLDOUT 2024..now | 958 | 28.5 | 28% | -0.014 [-0.2] | -13.3 | 0.96 | 53.4 | +0.046 [0.8] | 0.060 | 1.89% | 5% |

## V2b_limit_retest_12h

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV 2020-09..2023 | 1224 | 30.6 | 28% | -0.097 [-3.1] | -118.9 | 0.75 | 141.3 | -0.046 [-1.4] | 0.051 | 2.61% | 5% |
| HOLDOUT 2024..now | 954 | 28.4 | 28% | -0.046 [-1.0] | -43.5 | 0.88 | 55.8 | +0.016 [0.4] | 0.061 | 1.87% | 6% |

## V3_min_stop_0.95pct

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV 2020-09..2023 | 1158 | 29.0 | 32% | -0.018 [-0.5] | -20.9 | 0.95 | 59.2 | +0.042 [1.3] | 0.060 | 2.84% | 2% |
| HOLDOUT 2024..now | 888 | 26.4 | 31% | +0.012 [0.3] | +10.7 | 1.04 | 29.3 | +0.085 [2.0] | 0.073 | 2.10% | 2% |

## V4_filter_4h

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV 2020-09..2023 | 687 | 17.2 | 30% | -0.053 [-1.0] | -36.2 | 0.87 | 80.5 | +0.042 [0.8] | 0.094 | 2.30% | 20% |
| HOLDOUT 2024..now | 541 | 16.1 | 30% | +0.056 [0.7] | +30.4 | 1.13 | 21.3 | +0.162 [2.2] | 0.106 | 1.68% | 22% |

## V5_exit_teeth

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| DEV 2020-09..2023 | 1486 | 37.2 | 26% | -0.018 [-0.5] | -26.0 | 0.95 | 76.3 | +0.075 [2.0] | 0.093 | 2.15% | 17% |
| HOLDOUT 2024..now | 1225 | 36.4 | 28% | -0.010 [-0.2] | -12.1 | 0.97 | 52.2 | +0.096 [2.1] | 0.106 | 1.67% | 21% |

## V0 by range colour

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 DEV 2020-09..2023, green | 146 | 4.7 | 34% | -0.132 [-2.1] | -19.3 | 0.61 | 20.9 | -0.094 [-1.5] | 0.039 | 4.61% | 0% |
| V0 DEV 2020-09..2023, yellow | 274 | 8.6 | 29% | -0.139 [-2.4] | -38.0 | 0.65 | 46.4 | -0.076 [-1.3] | 0.063 | 2.85% | 7% |
| V0 DEV 2020-09..2023, red | 604 | 18.9 | 30% | -0.056 [-1.1] | -34.1 | 0.87 | 41.5 | +0.047 [0.9] | 0.104 | 1.82% | 22% |
| V0 DEV 2020-09..2023, none | 250 | 31.5 | 33% | +0.125 [1.2] | +31.1 | 1.36 | 10.4 | +0.193 [1.9] | 0.069 | 3.04% | 8% |
| V0 HOLDOUT 2024..now, green | 284 | 8.9 | 31% | -0.050 [-0.8] | -14.3 | 0.86 | 22.9 | +0.009 [0.1] | 0.059 | 2.91% | 3% |
| V0 HOLDOUT 2024..now, yellow | 321 | 9.6 | 34% | +0.077 [1.0] | +24.8 | 1.22 | 13.8 | +0.161 [2.0] | 0.084 | 1.90% | 7% |
| V0 HOLDOUT 2024..now, red | 385 | 11.7 | 26% | +0.007 [0.1] | +2.9 | 1.02 | 39.2 | +0.141 [1.5] | 0.134 | 1.22% | 33% |
| V0 HOLDOUT 2024..now, none | 0 | too few | | | | | | | | | |

### Control: V0's side and stop distance, random entry hour, fractal trail (5 draws per trade), by colour at the random entry

| sample | trades | per month | win | avg R net [t] | total R | PF | max DD R | avg R before costs [t] | costs R/trade | median stop | trades with costs > 15% of risk |
|---|---|---|---|---|---|---|---|---|---|---|---|
| random all | 11320 | 154.7 | 27% | -0.080 [-6.8] | -910.3 | 0.79 | 914.2 | +0.006 [0.5] | 0.086 | 2.20% | 15% |
| random DEV 2020-09..2023, green | 949 | 29.9 | 28% | -0.140 [-2.9] | -133.1 | 0.73 | 139.5 | -0.052 [-1.1] | 0.088 | 2.14% | 15% |
| random DEV 2020-09..2023, yellow | 1424 | 44.7 | 28% | -0.122 [-4.3] | -173.7 | 0.70 | 186.5 | -0.037 [-1.3] | 0.084 | 2.30% | 14% |
| random DEV 2020-09..2023, red | 2518 | 78.8 | 24% | -0.090 [-4.0] | -227.3 | 0.73 | 239.8 | -0.004 [-0.2] | 0.087 | 2.21% | 15% |
| random DEV 2020-09..2023, none | 1224 | 153.4 | 25% | -0.111 [-2.6] | -135.3 | 0.78 | 146.0 | -0.021 [-0.5] | 0.090 | 2.14% | 18% |
| random HOLDOUT 2024..now, green | 1764 | 54.0 | 27% | -0.124 [-4.0] | -219.6 | 0.71 | 220.8 | -0.039 [-1.3] | 0.085 | 2.14% | 14% |
| random HOLDOUT 2024..now, yellow | 1666 | 50.2 | 29% | -0.024 [-0.8] | -40.0 | 0.93 | 67.8 | +0.058 [2.0] | 0.082 | 2.28% | 13% |
| random HOLDOUT 2024..now, red | 1775 | 54.5 | 27% | +0.011 [0.3] | +18.7 | 1.04 | 65.5 | +0.099 [3.2] | 0.089 | 2.16% | 15% |
| random HOLDOUT 2024..now, none | 0 | too few | | | | | | | | | |

## V2a_limit_retest_4h: fill rate and the signals that did not fill

| sample | limit orders | filled | fill rate | unfilled with a V0 trade | their V0 avg R net | their V0 total R | V0 win | filled with a V0 trade | their V0 avg R net |
|---|---|---|---|---|---|---|---|---|---|
| DEV | 1349 | 1212 | 90% | 126 | +0.712 | +89.7 | 66% | 1124 | -0.131 |
| HOLDOUT | 1056 | 958 | 91% | 89 | +1.036 | +92.2 | 71% | 888 | -0.086 |

## V2b_limit_retest_12h: fill rate and the signals that did not fill

| sample | limit orders | filled | fill rate | unfilled with a V0 trade | their V0 avg R net | their V0 total R | V0 win | filled with a V0 trade | their V0 avg R net |
|---|---|---|---|---|---|---|---|---|---|
| DEV | 1307 | 1224 | 94% | 80 | +1.157 | +92.6 | 88% | 1182 | -0.126 |
| HOLDOUT | 1017 | 954 | 94% | 60 | +1.476 | +88.6 | 95% | 928 | -0.081 |
