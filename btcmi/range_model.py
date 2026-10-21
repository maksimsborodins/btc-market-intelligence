"""Range forecast ("H1"): how wide will BTC trade over the next 6 / 24 hours.

Target: ln(max high / min low) over the next H hourly bars of the Binance perp. Model: OLS of ln(target) on the log of
recent ranges (last 6 h, last day, mean of the last 7 / 30 days) and a seasonal term (typical range of the coming hours
for their hour of the week). Walk-forward: refit at every calendar month start on rows whose target window had already
ended, so a forecast never sees data from its own future. A traffic light ranks the 24 h forecast against the previous
365 days of forecasts.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btcmi.strategies import HOUR_MS, load_15m, resample

FEATURES = ("r6", "d", "w", "m", "seas")
MIN_TRAIN_MONTHS = 12
LIGHT_WINDOW_H = 365 * 24
LIGHT_MIN_H = 90 * 24


def hourly(conn) -> pd.DataFrame:
    """Binance perp 1h bars (same bars as the Oligator), gapless index = bar open (ms)."""
    return _grid(resample(load_15m(conn), 60))


def _grid(b: pd.DataFrame) -> pd.DataFrame:
    if b.empty:
        return b
    return b.reindex(np.arange(b.index.min(), b.index.max() + HOUR_MS, HOUR_MS, dtype="int64"))


def _roll_range(b: pd.DataFrame, n: int) -> pd.Series:
    """ln(max high / min low) over the n bars ending at each bar; NaN if any bar of the window is missing."""
    hi = b["high"].rolling(n, min_periods=n).max()
    lo = b["low"].rolling(n, min_periods=n).min()
    return np.log(hi / lo)


def future_range(b: pd.DataFrame, horizon: int) -> pd.Series:
    """ln(max high / min low) over bars t+1..t+horizon (t = close of bar t); NaN when the window is incomplete."""
    b = _grid(b)
    return _roll_range(b, horizon).shift(-horizon)


def _log(s: pd.Series) -> pd.Series:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(s)
    return out.where(np.isfinite(out))


def features(b: pd.DataFrame) -> pd.DataFrame:
    """ln of the last-6h range (r6), last-24h range (d), mean of 7 / 30 non-overlapping 24h ranges (w, m).
    Row t uses bars <= t only."""
    b = _grid(b)
    r6, d24 = _roll_range(b, 6), _roll_range(b, 24)
    blocks = lambda k: sum(d24.shift(24 * i) for i in range(k)) / k   # noqa: E731  (NaN propagates)
    return pd.DataFrame({"r6": _log(r6), "d": _log(d24), "w": _log(blocks(7)), "m": _log(blocks(30))})


def _slot(ts: np.ndarray) -> np.ndarray:
    """Hour of the week (UTC) of the bar that opens at ts."""
    return ((ts // HOUR_MS) + 72) % 168


def _seasonal_table(b: pd.DataFrame, horizon: int, end_ms: int) -> np.ndarray:
    """For each hour-of-week slot of bar t: ln of the summed mean 1h ln range of the next `horizon` slots, with the
    slot means taken from bars that closed by end_ms."""
    ts = b.index.to_numpy()
    lr = np.log(b["high"] / b["low"]).to_numpy()
    ok = np.isfinite(lr) & (ts + HOUR_MS <= end_ms)
    slot = _slot(ts)
    cnt = np.bincount(slot[ok], minlength=168)
    mean = np.bincount(slot[ok], weights=lr[ok], minlength=168) / np.maximum(cnt, 1)
    mean[cnt == 0] = np.nan
    ahead = sum(np.roll(mean, -k) for k in range(1, horizon + 1))
    return np.log(ahead)


def _ms(t: pd.Timestamp) -> int:
    return int(round(t.tz_localize("UTC").timestamp() * 1000)) if t.tzinfo is None else int(round(t.timestamp() * 1000))


def _month_starts(lo_ms: int, hi_ms: int) -> list[int]:
    ms = pd.date_range(pd.Timestamp(lo_ms, unit="ms").normalize().replace(day=1), pd.Timestamp(hi_ms, unit="ms"),
                       freq="MS")
    return [_ms(m) for m in ms]


def walk_forward(b: pd.DataFrame, horizon: int, cols: tuple[str, ...] = FEATURES,
                 min_train_months: int = MIN_TRAIN_MONTHS) -> tuple[pd.DataFrame, dict]:
    """Monthly refit. Returns (frame indexed by decision time = close of bar t in ms with pred, lo, hi (80% interval)
    and target, all in ln units; {month start ms: coefficients (intercept first)})."""
    b = _grid(b)
    ts = b.index.to_numpy()
    dec = ts + HOUR_MS
    f = features(b)
    y = future_range(b, horizon).pipe(_log).to_numpy()
    slot = _slot(ts)
    base = {k: f[k].to_numpy() for k in ("r6", "d", "w", "m")}
    valid_feat = np.isfinite(np.column_stack([base[k] for k in ("r6", "d", "w", "m")])).all(axis=1)
    first_ok = dec[valid_feat][0] if valid_feat.any() else dec[-1]
    first_ok_ts = pd.Timestamp(first_ok, unit="ms")
    earliest = _ms(first_ok_ts + pd.DateOffset(months=min_train_months))
    months = [s for s in _month_starts(int(ts[0]), int(dec[-1])) if s >= earliest]
    months.append(months[-1] + 32 * 86_400_000 if months else 0)
    rows, fits = [], {}
    for s, s_next in zip(months[:-1], months[1:]):
        seas = _seasonal_table(b, horizon, s)[slot]
        x_all = np.column_stack([np.ones(len(ts))] + [seas if c == "seas" else base[c] for c in cols])
        finite = np.isfinite(x_all).all(axis=1)
        train = finite & np.isfinite(y) & (dec + horizon * HOUR_MS <= s)
        if train.sum() < 500:
            continue
        beta, *_ = np.linalg.lstsq(x_all[train], y[train], rcond=None)
        res = y[train] - x_all[train] @ beta
        q10, q90 = np.quantile(res, [0.1, 0.9])
        fits[s] = beta
        now = finite & (dec >= s) & (dec < s_next)
        pred = x_all[now] @ beta
        rows.append(pd.DataFrame({"pred": pred, "lo": pred + q10, "hi": pred + q90, "target": y[now]}, index=dec[now]))
    out = pd.concat(rows) if rows else pd.DataFrame(columns=["pred", "lo", "hi", "target"])
    return out, fits


def traffic_light(pred: pd.Series) -> pd.Series:
    """Rank of each forecast among the previous 365 days of forecasts (past only, >= 90 days needed):
    lowest third red, highest third green, else yellow; "none" without enough history."""
    p = pred.to_numpy(dtype="float64")
    out = np.full(len(p), "none", dtype=object)
    for i in range(LIGHT_MIN_H, len(p)):
        if not np.isfinite(p[i]):
            continue
        past = p[max(0, i - LIGHT_WINDOW_H):i]
        past = past[np.isfinite(past)]
        if len(past) < LIGHT_MIN_H:
            continue
        rank = ((past < p[i]).sum() + 0.5 * (past == p[i]).sum()) / len(past)
        out[i] = "red" if rank < 1 / 3 else "green" if rank > 2 / 3 else "yellow"
    return pd.Series(out, index=pred.index)


def pct(x):
    """Percent move from the model's log scale: x = ln(ln(max/min)), so max/min - 1 = exp(exp(x)) - 1."""
    return (np.exp(np.exp(x)) - 1) * 100


def history(b: pd.DataFrame) -> pd.DataFrame:
    """Walk-forward forecasts for both horizons with the traffic light, indexed by decision time (ms)."""
    p6, _ = walk_forward(b, 6)
    p24, _ = walk_forward(b, 24)
    h = pd.DataFrame({"pred_6h_pct": pct(p6["pred"]), "pred_24h_pct": pct(p24["pred"]),
                      "pred_24h": p24["pred"]})
    h["color"] = traffic_light(h["pred_24h"].reindex(p24.index)).reindex(h.index).fillna("none")
    return h


def forecast_now(conn) -> dict:
    """Forecast for the next 6 / 24 hours from the latest closed hourly bar, fitted on all data with a complete target."""
    b = hourly(conn)
    out = {}
    wf24, _ = walk_forward(b, 24)
    for h in (6, 24):
        beta, q, x_now, t_now = _fit_all(b, h)
        pred = float(x_now @ beta)
        out[f"pred_{h}h_pct"] = float(pct(pred))
        out[f"lo_{h}h_pct"] = float(pct(pred + q[0]))
        out[f"hi_{h}h_pct"] = float(pct(pred + q[1]))
        out["time"] = t_now
        if h == 24:
            hist = wf24["pred"].copy()
            hist.loc[t_now] = pred
            out["color"] = str(traffic_light(hist.sort_index()).iloc[-1])
    return out


def _fit_all(b: pd.DataFrame, horizon: int):
    ts = b.index.to_numpy()
    dec = ts + HOUR_MS
    f = features(b)
    y = future_range(b, horizon).pipe(_log).to_numpy()
    seas = _seasonal_table(b, horizon, int(dec[-1]))[_slot(ts)]
    x = np.column_stack([np.ones(len(ts))] + [seas if c == "seas" else f[c].to_numpy() for c in FEATURES])
    fin = np.isfinite(x).all(axis=1)
    train = fin & np.isfinite(y)
    beta, *_ = np.linalg.lstsq(x[train], y[train], rcond=None)
    q = tuple(np.quantile(y[train] - x[train] @ beta, [0.1, 0.9]))
    last = int(np.flatnonzero(fin)[-1])
    return beta, q, x[last], int(dec[last])

