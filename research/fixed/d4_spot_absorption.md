# D4 spot absorption check (2026-10-21)

Signal: onset of (ret_24h below the drop threshold AND spot takers net buying over 24 h). Control: onset of (same drop AND spot takers net selling). 24 h between events of each kind. Outcome: next 24 h log return of the spot close. Difference within drop-size quintiles, 95% CI by 72 h calendar-block bootstrap. Pre-registered direction: signal > control. Cost 0.12% round trip.

## Main test: drop = ret_24h below -0.25 rolling std (the state definition)

| sample | signal events | control events | signal mean | control mean | same-size difference [95% CI] | signal long after cost |
|---|---|---|---|---|---|---|
| 2020-09..2023-12 | 131 | 561 | +0.34% (59% up) | +0.14% (55% up) | +0.19% [-0.37%, +0.75%] t=0.7 | +0.22% |
| 2020-09..2023-12 without zero-fee | 95 | 444 | +0.27% (61% up) | +0.13% (55% up) | +0.11% [-0.58%, +0.75%] t=0.3 | +0.15% |
| 2024-01..now | 170 | 453 | +0.30% (58% up) | +0.05% (52% up) | +0.25% [-0.11%, +0.61%] t=1.4 | +0.18% |
| all | 301 | 1014 | +0.32% (58% up) | +0.10% (54% up) | +0.24% [-0.09%, +0.55%] t=1.5 | +0.20% |
| all without zero-fee | 265 | 897 | +0.29% (59% up) | +0.09% (54% up) | +0.21% [-0.11%, +0.54%] t=1.3 | +0.17% |

## Secondary: real drops only, ret_24h below -1.0 rolling std

| sample | signal events | control events | signal mean | control mean | same-size difference [95% CI] | signal long after cost |
|---|---|---|---|---|---|---|
| 2020-09..2023-12 | 12 | 285 | +0.07% (75% up) | +0.03% (55% up) | -0.31% [-2.22%, +1.38%] t=-0.3 | -0.05% |
| 2020-09..2023-12 without zero-fee | 9 | 235 | +0.41% (89% up) | +0.07% (56% up) | -0.63% [-2.78%, +2.82%] t=-0.5 | +0.29% |
| 2024-01..now | 30 | 246 | +0.78% (77% up) | -0.10% (50% up) | +0.93% [+0.08%, +1.85%] t=2.1 | +0.66% |
| all | 42 | 531 | +0.57% (76% up) | -0.03% (53% up) | +0.71% [-0.13%, +1.37%] t=1.9 | +0.45% |
| all without zero-fee | 39 | 481 | +0.69% (79% up) | -0.02% (53% up) | +0.79% [-0.07%, +1.47%] t=2.0 | +0.57% |