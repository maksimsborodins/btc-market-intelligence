"""Honest evaluation of the picture: does a feature or a state say anything about price afterwards?

Rules (docs/REBUILD.md, "Research engine"):
- Overlapping horizons make neighbouring observations dependent, so every confidence interval is a block bootstrap
  with block length = horizon.
- Continuous features: Spearman IC, plus a walk-forward quintile test. Quintile edges and the sign (does a high value
  mean up or down?) are taken only from data before each month; the month is scored after that. Costs are charged on
  every active observation.
- States have no fitted parameters; each is compared with the base rate of the same sample, per quarter for stability.
- Everything tested is counted and reported, rejected results included.
"""

from __future__ import annotations

import json
import math
import zoneinfo
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from btcmi.features import FEATURE_COLUMNS, HORIZONS_H, STATE_COLUMNS

COST = 0.0012                 # round trip: 0.10% taker fees + 0.02% slippage, in log-return units
BOOTSTRAP_RESAMPLES = 1000
# Hundreds of feature x horizon x subset tests: a 95% interval would accept ~5% of pure noise. 99% plus the
# stability rules below keeps the false-acceptance rate low (checked by the pure-noise end-to-end test).
CI_PERCENTILES = (0.5, 99.5)
MIN_TRAIN_DAYS = 180
MIN_STATE_N = 100
MIN_QUARTERS = 6              # out-of-sample quarters needed before anything can be accepted
MIN_INDEPENDENT = 30          # active observations counted at most once per horizon
QUARTER_CONSISTENCY = 0.75


def block_hours(horizon_h: int) -> int:
    """Bootstrap block length in hours. Features persist (24 h windows) and horizons overlap, so neighbouring rows
    are dependent over max(horizon, 1 day); blocks of 4x that keep the interval honest (the 1x version accepted
    8 features on a pure random walk)."""
    return 4 * max(horizon_h, 24)
RIGA = zoneinfo.ZoneInfo("Europe/Riga")
US_SESSION_RIGA = (16.5, 23.0)  # decision times 16:30-23:00 Riga


def us_session_mask(index: pd.Index) -> np.ndarray:
    t = pd.to_datetime(np.asarray(index, dtype="int64"), unit="ms", utc=True).tz_convert(RIGA)
    hours = t.hour + t.minute / 60
    return (hours >= US_SESSION_RIGA[0]) & (hours < US_SESSION_RIGA[1])


def _block_ids(n: int, block: int) -> np.ndarray:
    return np.arange(n) // max(1, block)


def block_bootstrap_mean(values: np.ndarray, block: int, rng: np.random.Generator,
                         resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[float, float, float]:
    """Mean of the non-NaN values and its CI by resampling contiguous time blocks with replacement.
    `values` is a full hourly series in time order with NaN where there is no observation, so a block covers real
    time, not consecutive observations (dropping NaN first would glue distant episodes into one block)."""
    v = np.asarray(values, dtype="float64")
    ok = ~np.isnan(v)
    if not ok.any():
        return math.nan, math.nan, math.nan
    ids = _block_ids(len(v), block)
    sums = np.bincount(ids, weights=np.where(ok, v, 0.0))
    counts = np.bincount(ids, weights=ok.astype("float64"))
    keep = counts > 0
    sums, counts = sums[keep], counts[keep]
    k = len(sums)
    picks = rng.integers(0, k, size=(resamples, k))
    means = sums[picks].sum(axis=1) / counts[picks].sum(axis=1)
    lo, hi = np.percentile(means, CI_PERCENTILES)
    return float(v[ok].mean()), float(lo), float(hi)


def independent_count(active: np.ndarray, horizon_h: int) -> int:
    """Active observations counted at most once per horizon window (overlapping outcomes are one observation)."""
    count, next_free = 0, -1
    for i in np.flatnonzero(active):
        if i >= next_free:
            count += 1
            next_free = i + horizon_h
    return count


def block_bootstrap_ic(x: np.ndarray, y: np.ndarray, block: int, rng: np.random.Generator,
                       resamples: int = BOOTSTRAP_RESAMPLES) -> tuple[float, float, float, int]:
    """Spearman IC (Pearson of full-sample ranks) with a block-bootstrap CI. x and y are full hourly series in time
    order with NaN outside the sample, so blocks cover real time."""
    ok = ~(np.isnan(x) | np.isnan(y))
    ids = _block_ids(len(x), block)[ok]
    ids = np.unique(ids, return_inverse=True)[1]
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 50:
        return math.nan, math.nan, math.nan, n
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    parts = [np.bincount(ids, weights=w) for w in (rx, ry, rx * rx, ry * ry, rx * ry)]
    cnt = np.bincount(ids).astype("float64")

    def corr(sx, sy, sxx, syy, sxy, c):
        cov = sxy / c - (sx / c) * (sy / c)
        vx = sxx / c - (sx / c) ** 2
        vy = syy / c - (sy / c) ** 2
        return cov / np.sqrt(vx * vy)

    ic = float(corr(*(p.sum() for p in parts), cnt.sum()))
    picks = rng.integers(0, len(cnt), size=(resamples, len(cnt)))
    boot = corr(*(p[picks].sum(axis=1) for p in parts), cnt[picks].sum(axis=1))
    lo, hi = np.nanpercentile(boot, CI_PERCENTILES)
    return ic, float(lo), float(hi), n


@dataclass
class FeatureResult:
    feature: str
    horizon_h: int
    subset: str
    n: int
    ic: float
    ic_lo: float
    ic_hi: float
    ic_quarters_same_sign: float
    wf_active: int
    wf_hit_rate: float
    wf_mean_after_cost: float
    wf_lo: float
    wf_hi: float
    wf_quarters_positive: float
    accepted: bool


@dataclass
class StateResult:
    state_column: str
    state: str
    horizon_h: int
    subset: str
    n: int
    mean_fwd: float
    base_mean: float
    excess: float
    excess_lo: float
    excess_hi: float
    up_rate: float
    base_up_rate: float
    quarters_same_sign: float
    first_part_excess: float
    last_part_excess: float
    edge_after_cost: float
    accepted: bool


def _quarter_labels(index: pd.Index) -> np.ndarray:
    t = pd.to_datetime(np.asarray(index, dtype="int64"), unit="ms", utc=True)
    return np.asarray(t.year * 10 + t.quarter)


def _share_same_sign(values: list[float], sign: float) -> float:
    vals = [v for v in values if not math.isnan(v)]
    if not vals or sign == 0 or math.isnan(sign):
        return math.nan
    return sum(1 for v in vals if np.sign(v) == np.sign(sign)) / len(vals)


def walk_forward_quintiles(x: pd.Series, y: pd.Series, horizon_h: int) -> pd.Series:
    """Out-of-sample position per decision time: +1 / -1 in the outer quintiles, 0 otherwise.
    For each calendar month, edges come from feature values before the month, and the sign from the IC of pairs whose
    outcome was already known before the month (T + horizon <= month start). Nothing from the month itself is used."""
    t = pd.to_datetime(np.asarray(x.index, dtype="int64"), unit="ms", utc=True)
    months = pd.Series(t.to_period("M"), index=x.index)
    position = pd.Series(np.nan, index=x.index)
    first = t[0] if len(t) else None
    horizon_ms = horizon_h * 3_600_000
    for month in months.unique():
        month_start_ms = int(month.to_timestamp().tz_localize("UTC").value // 1_000_000)
        if first is None or (month_start_ms - first.value // 1_000_000) < MIN_TRAIN_DAYS * 86_400_000:
            continue
        past_x = x[x.index < month_start_ms].dropna()
        known = (x.index + horizon_ms) <= month_start_ms
        pairs = pd.DataFrame({"x": x[known], "y": y[known]}).dropna()
        if len(past_x) < 500 or len(pairs) < 500:
            continue
        sign = np.sign(pairs["x"].rank().corr(pairs["y"].rank()))
        if sign == 0 or math.isnan(sign):
            continue
        lo_edge, hi_edge = np.quantile(past_x, [0.2, 0.8])
        in_month = (months == month).to_numpy()
        xm = x[in_month]
        pos = pd.Series(0.0, index=xm.index)
        pos[xm >= hi_edge] = sign
        pos[xm <= lo_edge] = -sign
        pos[xm.isna()] = np.nan
        position[in_month] = pos
    return position


def _quarter_sign_share(values: pd.Series, reference_sign: float) -> tuple[float, int]:
    """Share of calendar quarters whose mean has the reference sign, and the number of quarters with data."""
    v = values.dropna()
    if v.empty:
        return math.nan, 0
    q = _quarter_labels(v.index)
    means = [float(v[q == label].mean()) for label in np.unique(q) if (q == label).sum() >= 20]
    return _share_same_sign(means, reference_sign), len(means)


def evaluate_feature(df: pd.DataFrame, feature: str, horizon_h: int, subset: str, mask: np.ndarray,
                     rng: np.random.Generator, position: pd.Series | None = None) -> FeatureResult:
    y_col = f"fwd_{horizon_h}h"
    x_all, y_all = df[feature], df[y_col]
    if position is None:
        position = walk_forward_quintiles(x_all, y_all, horizon_h)
    block = block_hours(horizon_h)

    # IC on the subset, kept on the full hourly time axis (NaN outside the subset)
    x = x_all.where(mask)
    y = y_all.where(mask)
    ic, lo, hi, n = block_bootstrap_ic(x.to_numpy(), y.to_numpy(), block, rng)
    q = _quarter_labels(x.index)
    per_q = []
    for label in np.unique(q):
        pair = pd.DataFrame({"x": x[q == label], "y": y[q == label]}).dropna()
        if len(pair) >= 100:
            per_q.append(pair["x"].rank().corr(pair["y"].rank()))
    ic_q = _share_same_sign(per_q, ic)

    # Walk-forward out-of-sample result, NaN where there is no position
    pos = position.where(mask)
    active = ((pos != 0) & pos.notna() & y.notna()).to_numpy()
    pnl = pd.Series(np.where(active, pos * y - COST, np.nan), index=df.index)
    wf_mean, wf_lo, wf_hi = block_bootstrap_mean(pnl.to_numpy(), block, rng)
    hit = float(((pos * y)[active] > 0).mean()) if active.any() else math.nan
    wf_q, n_quarters = _quarter_sign_share(pnl, 1.0)
    independent = independent_count(active, horizon_h)

    accepted = bool(
        n_quarters >= MIN_QUARTERS and independent >= MIN_INDEPENDENT
        and not math.isnan(wf_lo) and wf_lo > 0
        and not math.isnan(wf_q) and wf_q >= QUARTER_CONSISTENCY
        and not math.isnan(ic_q) and ic_q >= QUARTER_CONSISTENCY
        and not math.isnan(lo) and (lo > 0 or hi < 0)
    )
    return FeatureResult(feature, horizon_h, subset, n, ic, lo, hi, ic_q, int(active.sum()), hit,
                         wf_mean, wf_lo, wf_hi, wf_q, accepted)


def evaluate_states(df: pd.DataFrame, state_col: str, horizon_h: int, subset: str, mask: np.ndarray,
                    rng: np.random.Generator) -> list[StateResult]:
    y_col = f"fwd_{horizon_h}h"
    in_sample = mask & df[state_col].notna().to_numpy() & df[y_col].notna().to_numpy()
    if not in_sample.any():
        return []
    y = df[y_col].where(in_sample)
    states = df[state_col].where(in_sample)
    base_mean = float(y.mean())
    base_up = float((y.dropna() > 0).mean())
    block = block_hours(horizon_h)
    valid_index = y.dropna().index
    cut = valid_index[int(len(valid_index) * 0.7)]
    q_all = _quarter_labels(df.index)
    results = []
    for state in sorted(states.dropna().unique()):
        is_state = (states == state).to_numpy()
        n = int(is_state.sum())
        if n < MIN_STATE_N:
            continue
        excess_series = pd.Series(np.where(is_state, y - base_mean, np.nan), index=df.index)
        excess, lo, hi = block_bootstrap_mean(excess_series.to_numpy(), block, rng)
        # per quarter: state mean minus that quarter's base mean
        q_ex = []
        for label in np.unique(q_all[is_state]):
            in_q = q_all == label
            s_rows = y[in_q & is_state]
            if len(s_rows) >= 20:
                q_ex.append(float(s_rows.mean() - y[in_q].mean()))
        same = _share_same_sign(q_ex, excess)
        early = df.index < cut
        first = float(y[is_state & early].mean() - y[early].mean())
        last = float(y[is_state & ~early].mean() - y[~early].mean())
        edge = abs(excess) - COST
        accepted = bool(
            len(q_ex) >= MIN_QUARTERS and independent_count(is_state, horizon_h) >= MIN_INDEPENDENT
            and not math.isnan(lo) and (lo > 0 or hi < 0)
            and not math.isnan(same) and same >= QUARTER_CONSISTENCY
            and np.sign(first) == np.sign(last) == np.sign(excess)
            and edge > 0
        )
        results.append(StateResult(state_col, str(state), horizon_h, subset, n, float(y[is_state].mean()),
                                   base_mean, excess, lo, hi, float((y[is_state] > 0).mean()), base_up, same,
                                   first, last, float(edge), accepted))
    return results


def run_research(df: pd.DataFrame, seed: int = 7) -> dict:
    """df: build_picture() + add_targets(). Returns a JSON-serialisable report."""
    rng = np.random.default_rng(seed)
    subsets = {"all_hours": np.ones(len(df), dtype=bool), "us_session": us_session_mask(df.index)}
    features = [f for f in FEATURE_COLUMNS if f in df.columns and df[f].notna().sum() > 1000]
    feature_results, state_results = [], []
    for h in HORIZONS_H:
        positions = {f: walk_forward_quintiles(df[f], df[f"fwd_{h}h"], h) for f in features}
        for name, mask in subsets.items():
            for f in features:
                feature_results.append(evaluate_feature(df, f, h, name, mask, rng, positions[f]))
            for s in STATE_COLUMNS:
                if s in df.columns:
                    state_results.extend(evaluate_states(df, s, h, name, mask, rng))
    t = pd.to_datetime(np.asarray(df.index, dtype="int64"), unit="ms", utc=True)
    return {
        "period": [str(t[0]), str(t[-1])],
        "rows": len(df),
        "cost_round_trip": COST,
        "tests": {"features": len(feature_results), "states": len(state_results)},
        "features": [asdict(r) for r in feature_results],
        "states": [asdict(r) for r in state_results],
    }


def _pct(v: float) -> str:
    return "n/a" if v is None or (isinstance(v, float) and math.isnan(v)) else f"{v * 100:+.2f}%"


def summarize(report: dict, top: int = 15) -> str:
    """Readable markdown summary: accepted results first, then the strongest rejected ones."""
    lines = [
        f"# Research report",
        f"Period {report['period'][0]} - {report['period'][1]}, {report['rows']} hourly rows, "
        f"round-trip cost {report['cost_round_trip'] * 100:.2f}%.",
        f"Tested: {report['tests']['features']} feature x horizon x subset, {report['tests']['states']} state x horizon x subset.",
        "",
    ]
    states = sorted(report["states"], key=lambda r: -abs(r["excess"]) if r["excess"] == r["excess"] else 0)
    acc_s = [r for r in states if r["accepted"]]
    lines.append(f"## States accepted: {len(acc_s)}")
    lines.append("| state | window | horizon | subset | n | excess vs base | 99% CI | up-rate / base | quarters same sign |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in acc_s[:top]:
        lines.append(f"| {r['state']} | {r['state_column']} | {r['horizon_h']}h | {r['subset']} | {r['n']} | {_pct(r['excess'])} | "
                     f"{_pct(r['excess_lo'])}..{_pct(r['excess_hi'])} | {r['up_rate']:.1%} / {r['base_up_rate']:.1%} | {r['quarters_same_sign']:.0%} |")
    feats = sorted(report["features"], key=lambda r: -(r["wf_mean_after_cost"] if r["wf_mean_after_cost"] == r["wf_mean_after_cost"] else -1))
    acc_f = [r for r in feats if r["accepted"]]
    lines += ["", f"## Features accepted (walk-forward, after costs): {len(acc_f)}",
              "| feature | horizon | subset | IC [CI] | IC quarters same sign | active | hit | mean after cost [CI] |",
              "|---|---|---|---|---|---|---|---|"]
    for r in acc_f[:top]:
        lines.append(f"| {r['feature']} | {r['horizon_h']}h | {r['subset']} | {r['ic']:+.3f} [{r['ic_lo']:+.3f}, {r['ic_hi']:+.3f}] | "
                     f"{r['ic_quarters_same_sign']:.0%} | {r['wf_active']} | {r['wf_hit_rate']:.1%} | "
                     f"{_pct(r['wf_mean_after_cost'])} [{_pct(r['wf_lo'])}, {_pct(r['wf_hi'])}] |")
    lines += ["", "## Strongest rejected features (by walk-forward mean after cost)",
              "| feature | horizon | subset | IC [CI] | quarters | hit | mean after cost [CI] |", "|---|---|---|---|---|---|---|"]
    for r in [r for r in feats if not r["accepted"]][:top]:
        lines.append(f"| {r['feature']} | {r['horizon_h']}h | {r['subset']} | {r['ic']:+.3f} [{r['ic_lo']:+.3f}, {r['ic_hi']:+.3f}] | "
                     f"{r['ic_quarters_same_sign']:.0%} | {r['wf_hit_rate']:.1%} | {_pct(r['wf_mean_after_cost'])} [{_pct(r['wf_lo'])}, {_pct(r['wf_hi'])}] |")
    return "\n".join(lines)


def save(report: dict, path_json, path_md) -> None:
    with open(path_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=float)
    with open(path_md, "w", encoding="utf-8") as f:
        f.write(summarize(report))
