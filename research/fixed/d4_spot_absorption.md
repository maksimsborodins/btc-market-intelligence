# D4 spot absorption check (2026-10-21)

Drop onsets: ret_24h below -0.25 rolling std, first hour of the episode, 24 h between events. Signal: spot takers net buying over the same 24 h. Outcome: next 24 h log return of the spot close. Cost 0.12% round trip.

| sample | signal events | control events | signal mean | control mean | difference [95% CI] | same-size difference | signal long after cost |
|---|---|---|---|---|---|---|---|
| 2020-09..2023-12 | 89 | 492 | +0.21% (54% up) | +0.22% (55% up) | -0.01% [-0.75%, +0.71%] t=-0.0 | -0.02% | +0.09% |
| 2020-09..2023-12 without zero-fee | 65 | 393 | +0.14% (58% up) | +0.22% (55% up) | -0.08% [-0.93%, +0.75%] t=-0.2 | -0.10% | +0.02% |
| 2024-01..now | 111 | 377 | +0.33% (56% up) | +0.02% (52% up) | +0.31% [-0.18%, +0.81%] t=1.2 | +0.33% | +0.21% |
| all | 200 | 869 | +0.28% (55% up) | +0.13% (54% up) | +0.15% [-0.28%, +0.58%] t=0.7 | +0.15% | +0.16% |
| all without zero-fee | 176 | 770 | +0.26% (57% up) | +0.12% (54% up) | +0.14% [-0.30%, +0.60%] t=0.6 | +0.15% | +0.14% |

Exploratory add-on (not a pre-registered test): signal events split by OI over the same 24 h

| OI over 24 h | events | mean next 24 h | up |
|---|---|---|---|
| OI down | 107 | +0.29% | 55% |
| OI up/flat | 93 | +0.27% | 55% |