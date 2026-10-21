# Range forecast, out-of-sample (2026-10-21)

Target: ln(max high / min low) over the next H hours, Binance BTCUSDT perp 1h. OLS refit at every calendar month start on rows whose target had ended (>= 12 months of training); features: ln of the last-6h range, last-24h range, mean of 7 and of 30 daily ranges, and a seasonal term (hour-of-week mean ranges from training data). R2 is on the log scale against the mean of the evaluated era; MAE is on the log scale. Baselines are fitted the same walk-forward way. Targets overlap (H hours), so there are no t-stats; numbers are descriptive.

## Horizon 6 h

### 2022-01..2023-12 (n = 17520)

| model | R2 (log) | MAE (log) |
|---|---|---|
| model | 0.480 | 0.411 |
| b1: ln d only | 0.281 | 0.484 |
| b2: ln m only (30d) | 0.191 | 0.509 |

80% interval coverage: 74.7% (target 80%). Mean width (log): 1.186.

Calibration (5 bins of the predicted value): | bin | n | mean predicted % | mean actual % | median actual % |
|---|---|---|---|---|
| 1 | 3504 | 0.87 | 0.94 | 0.72 |
| 2 | 3504 | 1.33 | 1.48 | 1.15 |
| 3 | 3504 | 1.69 | 1.88 | 1.55 |
| 4 | 3504 | 2.11 | 2.36 | 1.99 |
| 5 | 3504 | 3.11 | 3.50 | 2.89 |

### 2024-01..now (n = 24582)

| model | R2 (log) | MAE (log) |
|---|---|---|
| model | 0.464 | 0.367 |
| b1: ln d only | 0.200 | 0.449 |
| b2: ln m only (30d) | 0.095 | 0.476 |

80% interval coverage: 81.7% (target 80%). Mean width (log): 1.209.

Calibration (5 bins of the predicted value): | bin | n | mean predicted % | mean actual % | median actual % |
|---|---|---|---|---|
| 1 | 4917 | 0.80 | 0.88 | 0.74 |
| 2 | 4916 | 1.17 | 1.34 | 1.15 |
| 3 | 4916 | 1.48 | 1.71 | 1.43 |
| 4 | 4916 | 1.84 | 2.05 | 1.74 |
| 5 | 4917 | 2.62 | 2.91 | 2.48 |

## Horizon 24 h

### 2022-01..2023-12 (n = 17520)

| model | R2 (log) | MAE (log) |
|---|---|---|
| model | 0.409 | 0.386 |
| b1: ln d only | 0.170 | 0.456 |
| b2: ln m only (30d) | 0.176 | 0.447 |

80% interval coverage: 75.9% (target 80%). Mean width (log): 1.137.

Calibration (5 bins of the predicted value): | bin | n | mean predicted % | mean actual % | median actual % |
|---|---|---|---|---|
| 1 | 3504 | 2.14 | 2.36 | 1.81 |
| 2 | 3504 | 3.09 | 3.44 | 2.91 |
| 3 | 3504 | 3.77 | 4.10 | 3.47 |
| 4 | 3504 | 4.59 | 4.96 | 4.22 |
| 5 | 3504 | 6.33 | 6.69 | 5.62 |

### 2024-01..now (n = 24564)

| model | R2 (log) | MAE (log) |
|---|---|---|
| model | 0.400 | 0.347 |
| b1: ln d only | 0.075 | 0.431 |
| b2: ln m only (30d) | 0.104 | 0.417 |

80% interval coverage: 81.9% (target 80%). Mean width (log): 1.154.

Calibration (5 bins of the predicted value): | bin | n | mean predicted % | mean actual % | median actual % |
|---|---|---|---|---|
| 1 | 4913 | 1.96 | 2.14 | 1.80 |
| 2 | 4913 | 2.74 | 3.10 | 2.77 |
| 3 | 4912 | 3.30 | 3.68 | 3.21 |
| 4 | 4913 | 4.00 | 4.44 | 3.96 |
| 5 | 4913 | 5.31 | 5.48 | 4.85 |

## Traffic light on the 24h forecast

Share of hours by colour and mean actual next-24h range:

| colour | hours | mean pred 24h % |
|---|---|---|
| red | 20754 | 2.98 |
| yellow | 14586 | 4.02 |
| green | 12624 | 5.53 |
| none | 2160 | 6.51 |

First walk-forward prediction: 2021-02-01 00:00:00.