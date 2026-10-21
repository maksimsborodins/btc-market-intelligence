"""Event studies: signal events against control events of the same size, with calendar-time block bootstrap.

Events are onsets (first hour a condition holds, then `block_h` hours blocked), one trade each. Signal and control
events can overlap in time, and events cluster in turbulent weeks, so the CI resamples calendar blocks of the shared
time axis: everything that happened in one block (signal and control together) is drawn or left out together.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

HOUR_MS = 3_600_000


def onsets(cond: pd.Series, block_h: int) -> np.ndarray:
    """First hour of each episode of `cond`, at least block_h hours after the previous event."""
    c = cond.fillna(False).to_numpy(dtype=bool)
    out = np.zeros(len(c), dtype=bool)
    next_free = -1
    for i in np.flatnonzero(c):
        if i >= next_free and (i == 0 or not c[i - 1]):
            out[i] = True
            next_free = i + block_h
    return out


def stratified_diff(ev: pd.DataFrame, block_h: int, rng: np.random.Generator, strata: int = 5,
                    resamples: int = 5000, min_per_cell: int = 3) -> dict:
    """Signal minus control within size strata, weighted by signal events per stratum.

    ev: one row per event, index = event time (epoch ms), columns y (outcome), signal (bool), size (stratifier).
    Strata are quantiles of `size` within `ev` itself, so a sub-period gets its own edges.
    Returns point, 95% CI, t (point / bootstrap sd), event counts and the number of strata used."""
    ev = ev[ev["y"].notna() & ev["size"].notna()]
    out = {"diff": math.nan, "lo": math.nan, "hi": math.nan, "t": math.nan,
           "n_signal": int(ev["signal"].sum()), "n_control": int((~ev["signal"]).sum()), "strata": 0}
    if out["n_signal"] < min_per_cell or out["n_control"] < min_per_cell:
        return out
    q = pd.qcut(ev["size"], strata, labels=False, duplicates="drop").to_numpy()
    k = int(np.nanmax(q)) + 1
    blocks = ((np.asarray(ev.index, dtype="int64") - int(ev.index.min())) // (block_h * HOUR_MS)).astype(int)
    blocks = np.unique(blocks, return_inverse=True)[1]
    nb = blocks.max() + 1
    sig = ev["signal"].to_numpy(dtype=bool)
    y = ev["y"].to_numpy(dtype="float64")
    # per (block, stratum) sums and counts, for signal and control
    cells = {}
    for name, m in (("s", sig), ("c", ~sig)):
        idx = blocks[m] * k + q[m]
        cells[name + "_sum"] = np.bincount(idx, weights=y[m], minlength=nb * k).reshape(nb, k)
        cells[name + "_cnt"] = np.bincount(idx, minlength=nb * k).reshape(nb, k).astype("float64")

    def stat(s_sum, s_cnt, c_sum, c_cnt):
        ok = (s_cnt >= min_per_cell) & (c_cnt >= min_per_cell)
        d = np.where(ok, s_sum / np.maximum(s_cnt, 1) - c_sum / np.maximum(c_cnt, 1), 0.0)
        w = np.where(ok, s_cnt, 0.0)
        return (d * w).sum(axis=-1) / np.where(w.sum(axis=-1) > 0, w.sum(axis=-1), np.nan), ok

    totals = [cells[c].sum(axis=0) for c in ("s_sum", "s_cnt", "c_sum", "c_cnt")]
    point, ok = stat(*totals)
    picks = rng.integers(0, nb, size=(resamples, nb))
    boot, _ = stat(*(cells[c][picks].sum(axis=1) for c in ("s_sum", "s_cnt", "c_sum", "c_cnt")))
    boot = boot[~np.isnan(boot)]
    lo, hi = np.percentile(boot, [2.5, 97.5])
    sd = boot.std(ddof=1)
    out.update(diff=float(point), lo=float(lo), hi=float(hi), t=float(point / sd) if sd > 0 else math.nan,
               strata=int(ok.sum()))
    return out
