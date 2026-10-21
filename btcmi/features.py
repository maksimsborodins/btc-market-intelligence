"""The market picture: open interest + spot/futures divergence + volume, point-in-time.

One row per decision time T on an hourly grid, where T is the close of an hourly bar. Every value in a row is computed
only from data that was available at T:
- bars: the bar ending at T and earlier (bar ts + 1h <= T);
- series: the last value with available_at <= T (as-of join), and never older than its staleness limit.

Forward returns (the research targets) are added separately by `add_targets` and are the only columns that look past T.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from btcmi.db import read_bars, read_series

HOUR_MS = 3_600_000
WINDOWS_H = (1, 4, 24)
HORIZONS_H = (1, 4, 12, 24, 48)
ZSCORE_LOOKBACK_H = 30 * 24
# Deadband for "up / down / flat" of price and OI, in units of the rolling std of that change. Fixed a priori,
# never fitted on returns: states must not be tuned on the data they are evaluated on.
DIRECTION_DEADBAND = 0.25

POSITIVE_ONLY = {"binance.oi", "bybit.oi", "binance.ls_ratio", "bybit.ls_buy_ratio"}
SERIES_STALENESS_H = {
    "binance.oi": 1,
    "bybit.oi": 2,
    "binance.premium": 1,
    "binance.funding": 9,
    "bybit.funding": 9,
    "binance.ls_ratio": 1,
    "bybit.ls_buy_ratio": 2,
}


def _hourly_bars(conn, venue: str, symbol: str, start_ms=None, end_ms=None) -> pd.DataFrame:
    """Hourly bars re-indexed by their close time T (= ts + 1h) on a gapless hourly grid: a missing bar is a NaN
    row, so shift(k) and rolling(k) always mean k hours, never k stored rows."""
    bars = read_bars(conn, venue, symbol, "1h", start_ms, end_ms)
    if bars.empty:
        return bars
    bars = bars.copy()
    bars["T"] = bars["ts"].astype("int64") + HOUR_MS
    bars = bars.set_index("T").drop(columns=["ts"])
    grid = pd.Index(np.arange(bars.index.min(), bars.index.max() + HOUR_MS, HOUR_MS, dtype="int64"), name="T")
    return bars.reindex(grid)


def asof_series(conn, metric: str, grid: pd.Index, start_ms=None, end_ms=None) -> pd.Series:
    """Value of `metric` known at each grid time: last observation with available_at <= T, dropped when older
    than SERIES_STALENESS_H. Observations are ordered by available_at, so a late publication is used only after
    it was published."""
    s = read_series(conn, metric, None if start_ms is None else start_ms - 48 * HOUR_MS, end_ms)
    out = pd.Series(np.nan, index=grid, dtype="float64", name=metric)
    if s.empty or len(grid) == 0:
        return out
    if metric in POSITIVE_ONLY:
        # Binance bulk metrics contain isolated 0.0 open interest points between ~92k BTC neighbours: feed errors
        s = s[s["value"] > 0]
    s = s.sort_values(["available_at", "ts"])
    left = pd.DataFrame({"T": np.asarray(grid, dtype="int64")})
    right = s[["available_at", "value"]].rename(columns={"available_at": "T"}).astype({"T": "int64"})
    right["seen_at"] = right["T"]
    merged = pd.merge_asof(left, right, on="T", direction="backward")
    limit_ms = SERIES_STALENESS_H.get(metric, 2) * HOUR_MS
    stale = (merged["T"] - merged["seen_at"]) > limit_ms
    merged.loc[stale, "value"] = np.nan
    out[:] = merged["value"].to_numpy()
    return out


def _rolling_z(x: pd.Series, lookback: int = ZSCORE_LOOKBACK_H) -> pd.Series:
    """z-score of x[T] against the trailing window ending at T (inclusive: x[T] is known at T)."""
    mean = x.rolling(lookback, min_periods=lookback // 2).mean()
    std = x.rolling(lookback, min_periods=lookback // 2).std()
    return (x - mean) / std.replace(0, np.nan)


def _direction(change: pd.Series, lookback: int = ZSCORE_LOOKBACK_H) -> pd.Series:
    """+1 / 0 / -1 with a deadband of DIRECTION_DEADBAND rolling standard deviations (past data only)."""
    std = change.rolling(lookback, min_periods=lookback // 2).std()
    d = pd.Series(0, index=change.index, dtype="float64")
    d[change > DIRECTION_DEADBAND * std] = 1
    d[change < -DIRECTION_DEADBAND * std] = -1
    d[change.isna() | std.isna()] = np.nan
    return d


def build_picture(conn, start_ms: int | None = None, end_ms: int | None = None) -> pd.DataFrame:
    """Hourly decision grid with the picture features. Index: decision time T (epoch ms, UTC)."""
    spot = _hourly_bars(conn, "binance_spot", "BTCUSDT", start_ms, end_ms)
    if spot.empty:
        raise ValueError("no binance_spot 1h bars in the database")
    perp = _hourly_bars(conn, "binance_perp", "BTCUSDT", start_ms, end_ms).reindex(spot.index)
    cb = _hourly_bars(conn, "coinbase_spot", "BTC-USD", start_ms, end_ms).reindex(spot.index)
    grid = spot.index

    df = pd.DataFrame(index=grid)
    df.index.name = "T"
    df["close"] = spot["close"]

    # Signed taker flow per bar, as a share of the bar's volume: (buy - sell) = 2 * taker_buy - volume
    spot_flow = 2 * spot["taker_buy_volume"] - spot["volume"]
    perp_flow = 2 * perp["taker_buy_volume"] - perp["volume"]

    # Open interest in BTC: Binance (5-min metrics) + Bybit (1h). Aggregate only where both are known.
    oi_bin = asof_series(conn, "binance.oi", grid, start_ms, end_ms)
    oi_byb = asof_series(conn, "bybit.oi", grid, start_ms, end_ms)
    df["oi_binance"] = oi_bin
    df["oi_total"] = oi_bin + oi_byb

    df["premium"] = asof_series(conn, "binance.premium", grid, start_ms, end_ms)
    df["cb_premium"] = cb["close"] / spot["close"] - 1
    df["funding"] = asof_series(conn, "binance.funding", grid, start_ms, end_ms)
    df["funding_z"] = _rolling_z(df["funding"], 90 * 24)
    df["ls_ratio"] = asof_series(conn, "binance.ls_ratio", grid, start_ms, end_ms)

    for w in WINDOWS_H:
        sv = spot["volume"].rolling(w).sum()
        pv = perp["volume"].rolling(w).sum()
        df[f"ret_{w}h"] = np.log(df["close"] / df["close"].shift(w))
        df[f"oi_chg_{w}h"] = df["oi_total"] / df["oi_total"].shift(w) - 1
        df[f"oi_bin_chg_{w}h"] = df["oi_binance"] / df["oi_binance"].shift(w) - 1
        df[f"spot_delta_{w}h"] = spot_flow.rolling(w).sum() / sv
        df[f"perp_delta_{w}h"] = perp_flow.rolling(w).sum() / pv
        df[f"delta_diff_{w}h"] = df[f"spot_delta_{w}h"] - df[f"perp_delta_{w}h"]
        sq = spot["quote_volume"].rolling(w).sum()
        pq = perp["quote_volume"].rolling(w).sum()
        df[f"spot_share_{w}h"] = sq / (sq + pq)
        total_q = sq + pq
        # rows are hours: the norm is the mean w-hour volume over the previous 30 days
        df[f"vol_ratio_{w}h"] = total_q / total_q.shift(w).rolling(ZSCORE_LOOKBACK_H, min_periods=ZSCORE_LOOKBACK_H // 2).mean()
        df[f"premium_chg_{w}h"] = df["premium"] - df["premium"].shift(w)
        df[f"cb_premium_avg_{w}h"] = df["cb_premium"].rolling(w).mean()
        for col in (f"oi_chg_{w}h", f"spot_delta_{w}h", f"perp_delta_{w}h", f"delta_diff_{w}h", f"premium_chg_{w}h"):
            df[f"{col}_z"] = _rolling_z(df[col])

    df["premium_z"] = _rolling_z(df["premium"])
    df["cb_premium_z"] = _rolling_z(df["cb_premium"])
    df = add_states(df)
    return df


def add_states(df: pd.DataFrame) -> pd.DataFrame:
    """Readable states per window, the way the user reads the market. Categories, not scores."""
    for w in WINDOWS_H:
        p = _direction(df[f"ret_{w}h"])
        o = _direction(df[f"oi_chg_{w}h"])
        spot_buy = df[f"spot_delta_{w}h"] > 0
        spot_leads = df[f"delta_diff_{w}h"] > 0

        oi_state = pd.Series(None, index=df.index, dtype="object")
        oi_state[(p == 1) & (o == 1)] = "long_buildup"        # price up, OI up: new longs
        oi_state[(p == -1) & (o == 1)] = "short_buildup"      # price down, OI up: new shorts
        oi_state[(p == 1) & (o == -1)] = "short_covering"     # price up, OI down: shorts closing
        oi_state[(p == -1) & (o == -1)] = "long_liquidation"  # price down, OI down: longs closing
        oi_state[(p == 0) | (o == 0)] = "flat"
        df[f"oi_state_{w}h"] = oi_state

        driver = pd.Series(None, index=df.index, dtype="object")
        driver[(p == 1) & spot_buy & spot_leads] = "rise_spot_led"
        driver[(p == 1) & ~spot_buy] = "rise_spot_selling"    # price up while spot takers are net sellers
        driver[(p == -1) & ~spot_buy & ~spot_leads] = "drop_spot_led"
        driver[(p == -1) & spot_buy] = "drop_spot_buying"     # price down while spot takers are net buyers
        driver[(p == 1) & spot_buy & ~spot_leads] = "rise_mixed"
        driver[(p == -1) & ~spot_buy & spot_leads] = "drop_mixed"
        driver[p == 0] = "flat"
        driver[p.isna() | df[f"spot_delta_{w}h"].isna() | df[f"delta_diff_{w}h"].isna()] = None
        df[f"driver_{w}h"] = driver

        combo = pd.Series(None, index=df.index, dtype="object")
        rise_perp_oi_up = (p == 1) & (o == 1) & ~spot_buy
        drop_perp_oi_up = (p == -1) & (o == 1) & spot_buy
        combo[rise_perp_oi_up] = "rise_on_leverage"           # the user's main reading: rise on perps, spot not buying
        combo[drop_perp_oi_up] = "drop_on_leverage"
        combo[(p == 1) & spot_buy & spot_leads & (o != 1)] = "rise_on_spot"
        combo[(p == -1) & ~spot_buy & ~spot_leads & (o != 1)] = "drop_on_spot"
        # NaN compares as False, so ~spot_buy is True for a missing delta: blank those rows
        combo[p.isna() | o.isna() | df[f"spot_delta_{w}h"].isna() | df[f"delta_diff_{w}h"].isna()] = None
        df[f"combo_{w}h"] = combo
    return df


def add_targets(df: pd.DataFrame) -> pd.DataFrame:
    """Forward log returns of the Binance spot close over each horizon. Look-ahead by construction: research only."""
    out = df.copy()
    for h in HORIZONS_H:
        out[f"fwd_{h}h"] = np.log(out["close"].shift(-h) / out["close"])
    return out


FEATURE_COLUMNS = (
    [f"ret_{w}h" for w in WINDOWS_H]
    + [f"{c}_{w}h{z}" for w in WINDOWS_H for c in ("oi_chg", "spot_delta", "perp_delta", "delta_diff", "premium_chg") for z in ("", "_z")]
    + [f"{c}_{w}h" for w in WINDOWS_H for c in ("spot_share", "vol_ratio", "cb_premium_avg", "oi_bin_chg")]
    + ["premium", "premium_z", "cb_premium", "cb_premium_z", "funding", "funding_z", "ls_ratio"]
)
STATE_COLUMNS = [f"{c}_{w}h" for w in WINDOWS_H for c in ("oi_state", "driver", "combo")]
