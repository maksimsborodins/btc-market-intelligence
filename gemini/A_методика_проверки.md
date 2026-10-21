# Независимая проверка методики бэктеста (BTC, горизонты 1–48 ч)

Ты — опытный квант-исследователь и рецензент. Ниже код и результаты исследовательского движка, который проверяет,
дают ли метрики рынка BTC (открытый интерес, расхождение спота и фьючерсов, объёмы, базис, премия Coinbase,
ставка финансирования) преимущество на горизонтах 1, 4, 12, 24, 48 часов. Автор кода — другая ИИ-модель.
Твоя задача — найти, где этим цифрам НЕЛЬЗЯ верить. Не хвали, ищи ошибки.

## Контекст
- Трейдер вручную торгует BTC-перпетуалы (BingX), скальп 1–12 ч и интрадей/свинг 12–48 ч, американская сессия, Рига.
- Цель системы — не автоторговля, а «ещё один фактор» для решений: показать картину рынка и сказать, что исторически
  означало каждое состояние.
- Данные (SQLite): Binance spot/perp свечи 15m/1h с taker buy volume (2020+), 5-минутный открытый интерес Binance
  (архив data.binance.vision, 2020-09+), премия перпа (premiumIndexKlines), funding, Bybit OI (1h, 2020-07+),
  Coinbase 1h. У каждого значения в таблице series есть `available_at` — момент, когда значение стало известно.
- Решение принимается в момент T = закрытие часовой свечи. Цели: форвардная лог-доходность спота Binance за h часов.
- Правила принятия (после того как тест на чистом шуме поймал 8 ложных принятий в первой версии):
  блоки бутстрепа 4·max(h, 24 ч) в реальном времени, 99% интервалы, ≥ 6 кварталов вне выборки, ≥ 30 независимых
  наблюдений, знак стабилен в ≥ 75% кварталов, обе половины истории одного знака, эффект > комиссий 0.12%.
- Тесты: на чистом случайном блуждании принимается ≤ 1 результата; заложенный в синтетику эффект находится;
  изменение данных «после» T не меняет ни одной цифры «до» T.

## Что ответить (структурированно, по-русски)
1. **Утечки будущего (look-ahead):** есть ли места, где признак в момент T использует данные после T
   (включая rolling-окна, z-score, деление на объём, as-of join, staleness, выбор квантилей и знака в walk-forward,
   разметку состояний с deadband). Укажи строку/функцию и почему.
2. **Статистика:** корректны ли block bootstrap на «дырявом» ряду (NaN вне состояния), подсчёт независимых
   наблюдений, правило принятия для состояний (у них нет обучаемых параметров — нужен ли walk-forward?),
   поправка на множественные проверки (1000 тестов, 99% CI). Чего не хватает (например, FDR, deflated Sharpe,
   placebo/перестановочные тесты)?
3. **Найденный результат:** «цена за 24 ч упала, при этом рыночные покупатели на споте Binance в плюсе» →
   следующие 24 ч +0.43% к базе, рост в 63% против 52%. Насколько ему верить? Какие контрольные проверки обязательны
   (сравнение с просто «цена упала за 24 ч», режимы рынка, перекрытие эпизодов, зависимость от 2020–2021)?
4. **Почему «рост на плечах» (цена ↑, OI ↑, спот не покупает) мог не найтись,** даже если эффект есть:
   слишком грубое определение, неправильный горизонт, неправильная цель (направление вместо волатильности)?
   Как переформулировать проверку.
5. **Конкретные исправления кода** (короткие патчи или псевдокод), в порядке важности.
6. **Что бы ты проверил следующим** на этих данных, если цель — преимущество для ручного трейдера на 1–48 ч.

Если что-то в коде тебе непонятно без остальных файлов — так и скажи, не додумывай.


## Признаки и состояния (`btcmi\features.py`)

```python
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
    """Hourly bars re-indexed by their close time T (= ts + 1h)."""
    bars = read_bars(conn, venue, symbol, "1h", start_ms, end_ms)
    if bars.empty:
        return bars
    bars = bars.copy()
    bars["T"] = bars["ts"].astype("int64") + HOUR_MS
    return bars.set_index("T").drop(columns=["ts"])


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
        df[f"vol_ratio_{w}h"] = total_q / total_q.shift(w).rolling(ZSCORE_LOOKBACK_H // w, min_periods=10).mean()
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
        driver[(p == 1) & ~spot_buy] = "rise_perp_led"        # price up while spot takers are net sellers
        driver[(p == -1) & ~spot_buy & ~spot_leads] = "drop_spot_led"
        driver[(p == -1) & spot_buy] = "drop_perp_led"        # price down while spot takers are net buyers
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

```


## Движок проверки (`btcmi\research.py`)

```python
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

```


## Тесты движка (`tests_btcmi\test_research.py`)

```python
"""Point-in-time correctness of the picture and sanity of the research statistics (offline, synthetic data)."""

import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from btcmi import db
from btcmi.features import HOUR_MS, add_targets, asof_series, build_picture, FEATURE_COLUMNS
from btcmi.research import (
    block_bootstrap_ic, block_bootstrap_mean, run_research, us_session_mask, walk_forward_quintiles,
)

START = 1_700_000_000_000 // HOUR_MS * HOUR_MS  # 2023-11-14, hour aligned


def _bars(venue, symbol, closes, taker_share, start=START):
    rows = []
    for i, c in enumerate(closes):
        vol = 100.0
        rows.append({
            "venue": venue, "symbol": symbol, "interval": "1h", "ts": start + i * HOUR_MS,
            "open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
            "volume": vol, "quote_volume": vol * c, "taker_buy_volume": vol * taker_share[i], "trades": 10,
        })
    return rows


def _series(metric, values, lag_h=0, start=START):
    return [{"metric": metric, "ts": start + i * HOUR_MS, "value": v, "available_at": start + (i + lag_h) * HOUR_MS}
            for i, v in enumerate(values)]


class TempDb(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.conn = db.connect(os.path.join(self.dir.name, "t.db"))
        self.addCleanup(self.conn.close)

    def fill(self, n=24 * 60, seed=1):
        rng = np.random.default_rng(seed)
        closes = 30000 * np.exp(np.cumsum(rng.normal(0, 0.004, n)))
        spot_share = np.clip(0.5 + rng.normal(0, 0.05, n), 0.05, 0.95)
        perp_share = np.clip(0.5 + rng.normal(0, 0.05, n), 0.05, 0.95)
        oi = 80000 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
        db.upsert_bars(self.conn, _bars("binance_spot", "BTCUSDT", closes, spot_share))
        db.upsert_bars(self.conn, _bars("binance_perp", "BTCUSDT", closes * 1.0002, perp_share))
        db.upsert_bars(self.conn, _bars("coinbase_spot", "BTC-USD", closes * 1.0005, spot_share))
        db.upsert_series(self.conn, _series("binance.oi", oi))
        db.upsert_series(self.conn, _series("bybit.oi", oi * 0.6))
        db.upsert_series(self.conn, _series("binance.premium", rng.normal(0, 1e-4, n), lag_h=1))
        db.upsert_series(self.conn, _series("binance.funding", np.full(n, 1e-4)))
        return n


class TestPointInTime(TempDb):
    def test_asof_respects_publication_time(self):
        # value for hour 0 is published 3 hours later: it must not be visible at T = hour 1 or 2
        db.upsert_series(self.conn, [{"metric": "binance.funding", "ts": START, "value": 7.0,
                                      "available_at": START + 3 * HOUR_MS}])
        grid = pd.Index([START + k * HOUR_MS for k in range(1, 6)])
        s = asof_series(self.conn, "binance.funding", grid)
        self.assertTrue(np.isnan(s.iloc[0]) and np.isnan(s.iloc[1]))
        self.assertEqual(s.iloc[2], 7.0)

    def test_stale_values_are_dropped(self):
        db.upsert_series(self.conn, [{"metric": "binance.oi", "ts": START, "value": 5.0, "available_at": START}])
        grid = pd.Index([START, START + HOUR_MS, START + 3 * HOUR_MS])
        s = asof_series(self.conn, "binance.oi", grid)  # binance.oi staleness limit: 1 h
        self.assertEqual(list(s.iloc[:2]), [5.0, 5.0])
        self.assertTrue(np.isnan(s.iloc[2]))

    def test_future_data_does_not_change_the_past(self):
        n = self.fill()
        before = build_picture(self.conn)
        cut = START + (n // 2) * HOUR_MS
        # rewrite everything after the cut: bars that close after the cut and series published after it
        self.conn.execute("UPDATE bars SET close = close * 1.5, taker_buy_volume = volume WHERE ts + ? > ?", (HOUR_MS, cut))
        self.conn.execute("UPDATE series SET value = value * 3 WHERE available_at > ?", (cut,))
        self.conn.commit()
        after = build_picture(self.conn)
        cols = [c for c in before.columns if not c.startswith("fwd_")]
        a = before.loc[before.index <= cut, cols]
        b = after.loc[after.index <= cut, cols]
        pd.testing.assert_frame_equal(a, b)
        self.assertFalse(before.loc[before.index > cut, "close"].equals(after.loc[after.index > cut, "close"]))

    def test_rise_on_leverage_state(self):
        n = 24 * 40
        closes = np.concatenate([np.full(n - 4, 30000.0), 30000 * np.array([1.003, 1.006, 1.009, 1.012])])
        spot_share = np.concatenate([np.full(n - 4, 0.5), np.full(4, 0.3)])   # spot takers selling into the rise
        perp_share = np.concatenate([np.full(n - 4, 0.5), np.full(4, 0.7)])
        rng = np.random.default_rng(3)
        closes[: n - 4] *= np.exp(rng.normal(0, 0.002, n - 4))
        oi = np.concatenate([80000 * np.exp(rng.normal(0, 0.001, n - 4)), 80000 * np.array([1.01, 1.02, 1.03, 1.04])])
        db.upsert_bars(self.conn, _bars("binance_spot", "BTCUSDT", closes, spot_share))
        db.upsert_bars(self.conn, _bars("binance_perp", "BTCUSDT", closes, perp_share))
        db.upsert_series(self.conn, _series("binance.oi", oi))
        db.upsert_series(self.conn, _series("bybit.oi", oi * 0.5))
        df = build_picture(self.conn)
        last = df.iloc[-1]
        self.assertEqual(last["combo_4h"], "rise_on_leverage")
        self.assertEqual(last["oi_state_4h"], "long_buildup")
        self.assertEqual(last["driver_4h"], "rise_perp_led")

    def test_missing_flow_gives_no_state(self):
        self.fill(n=24 * 40)
        self.conn.execute("DELETE FROM bars WHERE venue = 'binance_perp'")
        self.conn.commit()
        df = build_picture(self.conn)
        self.assertTrue(df["combo_4h"].isna().all())


class TestStatistics(unittest.TestCase):
    def test_bootstrap_mean_covers_true_mean(self):
        rng = np.random.default_rng(0)
        v = rng.normal(0.5, 1, 5000)
        m, lo, hi = block_bootstrap_mean(v, 10, rng)
        self.assertLess(lo, 0.5)
        self.assertGreater(hi, 0.5)
        self.assertLess(hi - lo, 0.2)

    def test_ic_detects_signal_and_not_noise(self):
        rng = np.random.default_rng(1)
        x = rng.normal(size=5000)
        ic, lo, hi, _ = block_bootstrap_ic(x, x + rng.normal(scale=3, size=5000), 4, rng)
        self.assertGreater(lo, 0)
        ic0, lo0, hi0, _ = block_bootstrap_ic(x, rng.normal(size=5000), 4, rng)
        self.assertLess(lo0, 0)
        self.assertGreater(hi0, 0)

    def test_walk_forward_uses_only_the_past(self):
        # the feature predicts the 1h return perfectly, but the sign flips at a month boundary: the first month after
        # the flip must still be traded with the OLD sign (it could not have been known), so it loses
        hours = 24 * 400
        idx = pd.Index([START + k * HOUR_MS for k in range(hours)])
        rng = np.random.default_rng(2)
        y = pd.Series(rng.normal(0, 0.01, hours), index=idx)
        t = pd.to_datetime(np.asarray(idx), unit="ms", utc=True)
        flip_month = t[24 * 300].to_period("M")
        flip_ms = int(flip_month.to_timestamp().tz_localize("UTC").value // 1_000_000)
        x = y.copy()
        x[idx >= flip_ms] = -y[idx >= flip_ms]
        pos = walk_forward_quintiles(x, y, 1)
        first_month = (pd.Series(t.to_period("M"), index=idx) == flip_month).to_numpy()
        pnl_after = (pos[first_month] * y[first_month]).sum()
        before = (idx < flip_ms) & pos.notna().to_numpy()
        pnl_before = (pos[before] * y[before]).sum()
        self.assertGreater(pnl_before, 0)
        self.assertLess(pnl_after, 0)
        self.assertTrue(pos[: 24 * 170].isna().all())  # no positions before the minimum training period

    def test_us_session_mask_follows_riga_time(self):
        # 2026-07-01 14:00 UTC = 17:00 Riga (summer, UTC+3); 2026-01-15 14:00 UTC = 16:00 Riga (winter, UTC+2)
        summer = int(pd.Timestamp("2026-07-01 14:00", tz="UTC").value // 1_000_000)
        winter = int(pd.Timestamp("2026-01-15 14:00", tz="UTC").value // 1_000_000)
        self.assertEqual(list(us_session_mask(pd.Index([summer, winter]))), [True, False])


class TestEndToEnd(TempDb):
    """Two years of synthetic data: the acceptance rule must reject noise AND find a planted effect."""

    def test_pure_noise_is_rejected(self):
        self.fill(n=24 * 730, seed=5)
        report = run_research(add_targets(build_picture(self.conn)), seed=1)
        self.assertGreater(report["tests"]["features"], 0)
        self.assertGreater(report["tests"]["states"], 0)
        accepted_f = [(r["feature"], r["horizon_h"], r["subset"]) for r in report["features"] if r["accepted"]]
        accepted_s = [(r["state"], r["state_column"], r["horizon_h"]) for r in report["states"] if r["accepted"]]
        # a random walk has no edge: an accepted result here is a false positive of the method itself
        self.assertLessEqual(len(accepted_f), 1, accepted_f)
        self.assertLessEqual(len(accepted_s), 1, accepted_s)
        self.assertTrue(set(FEATURE_COLUMNS) >= {r["feature"] for r in report["features"]})

    def test_planted_spot_flow_effect_is_found(self):
        n = 24 * 730
        rng = np.random.default_rng(11)
        # persistent spot taker share; the next hours drift with the last day's spot buying
        share = np.empty(n)
        share[0] = 0.5
        for i in range(1, n):
            share[i] = 0.5 + 0.97 * (share[i - 1] - 0.5) + rng.normal(0, 0.01)
        share = np.clip(share, 0.05, 0.95)
        past_day = pd.Series(share).rolling(24).mean().shift(1).fillna(0.5).to_numpy()
        returns = 0.004 * (past_day - 0.5) / 0.05 * 0.25 + rng.normal(0, 0.004, n)
        closes = 30000 * np.exp(np.cumsum(returns))
        perp_share = np.clip(0.5 + rng.normal(0, 0.03, n), 0.05, 0.95)
        oi = 80000 * np.exp(np.cumsum(rng.normal(0, 0.003, n)))
        db.upsert_bars(self.conn, _bars("binance_spot", "BTCUSDT", closes, share))
        db.upsert_bars(self.conn, _bars("binance_perp", "BTCUSDT", closes, perp_share))
        db.upsert_series(self.conn, _series("binance.oi", oi))
        db.upsert_series(self.conn, _series("bybit.oi", oi * 0.6))
        report = run_research(add_targets(build_picture(self.conn)), seed=1)
        found = {(r["feature"], r["horizon_h"]) for r in report["features"] if r["accepted"] and r["subset"] == "all_hours"}
        self.assertTrue(any(f.startswith("spot_delta_24h") for f, _ in found), found)


if __name__ == "__main__":
    unittest.main()

```


## Итоговый отчёт первого прогона (`research\report_2026-10-21.md`)

```markdown
# Research report
Period 2020-09-01 01:00:00+00:00 - 2026-10-21 07:00:00+00:00, 53771 hourly rows, round-trip cost 0.12%.
Tested: 520 feature x horizon x subset, 480 state x horizon x subset.

## States accepted: 1
| state | window | horizon | subset | n | excess vs base | 99% CI | up-rate / base | quarters same sign |
|---|---|---|---|---|---|---|---|---|
| drop_perp_led | driver_24h | 24h | all_hours | 1676 | +0.43% | +0.08%..+0.81% | 63.0% / 52.0% | 77% |

## Features accepted (walk-forward, after costs): 0
| feature | horizon | subset | IC [CI] | IC quarters same sign | active | hit | mean after cost [CI] |
|---|---|---|---|---|---|---|---|

## Strongest rejected features (by walk-forward mean after cost)
| feature | horizon | subset | IC [CI] | quarters | hit | mean after cost [CI] |
|---|---|---|---|---|---|---|
| ls_ratio | 48h | us_session | -0.057 [-0.124, +0.016] | 54% | 51.6% | +0.42% [-0.02%, +0.82%] |
| ls_ratio | 48h | all_hours | -0.057 [-0.122, +0.011] | 50% | 51.9% | +0.39% [-0.03%, +0.83%] |
| cb_premium_z | 48h | us_session | +0.059 [-0.008, +0.129] | 60% | 51.5% | +0.36% [+0.00%, +0.81%] |
| cb_premium_z | 48h | all_hours | +0.055 [-0.007, +0.120] | 58% | 51.8% | +0.32% [-0.10%, +0.69%] |
| perp_delta_24h | 48h | us_session | +0.024 [-0.027, +0.075] | 58% | 49.9% | +0.21% [-0.13%, +0.57%] |
| perp_delta_24h | 48h | all_hours | +0.021 [-0.034, +0.074] | 62% | 49.8% | +0.19% [-0.17%, +0.54%] |
| cb_premium_z | 24h | us_session | +0.048 [+0.003, +0.091] | 60% | 51.0% | +0.18% [-0.04%, +0.37%] |
| ls_ratio | 24h | us_session | -0.043 [-0.093, +0.007] | 54% | 50.9% | +0.18% [-0.05%, +0.41%] |
| spot_delta_24h | 48h | all_hours | +0.029 [-0.022, +0.083] | 54% | 51.5% | +0.17% [-0.14%, +0.44%] |
| ls_ratio | 24h | all_hours | -0.038 [-0.087, +0.006] | 54% | 50.2% | +0.16% [-0.06%, +0.39%] |
| spot_delta_24h | 48h | us_session | +0.026 [-0.026, +0.079] | 54% | 50.4% | +0.14% [-0.16%, +0.46%] |
| cb_premium_z | 24h | all_hours | +0.040 [-0.007, +0.080] | 58% | 50.6% | +0.13% [-0.05%, +0.34%] |
| perp_delta_4h | 48h | us_session | +0.043 [-0.001, +0.085] | 69% | 50.1% | +0.12% [-0.14%, +0.36%] |
| ls_ratio | 12h | us_session | -0.038 [-0.079, +0.009] | 58% | 50.8% | +0.09% [-0.06%, +0.25%] |
| spot_delta_24h_z | 48h | all_hours | +0.026 [-0.018, +0.077] | 58% | 50.4% | +0.09% [-0.23%, +0.41%] |
```


## Дополнительно: состояния, у которых 99% интервал не включает 0 (13 из 480), и «рост на плечах»

```
drop_perp_led   driver_24h 24h all  n=1676 excess +0.43% [+0.08,+0.81] up 63%/52% q 77% halves +0.50/+0.38 ACCEPTED
drop_perp_led   driver_24h 12h all  n=1682 excess +0.30% [+0.03,+0.57] up 61%/51% q 68% halves +0.41/+0.18
long_buildup    oi_state_4h 12h all n=7604 excess +0.15% [+0.01,+0.29] up 51%/51% q 65%
rise_on_spot    combo_4h  4h all    n=4142 excess -0.06% [-0.12,-0.01] up 44%/51% q 72%
rise_on_leverage combo_4h 24h all   n=2306 excess +0.16% [-0.11,+0.46] up 52%/53% q 52%
rise_on_leverage combo_24h 24h all  n=3209 excess +0.03% [-0.39,+0.40] up 48%/52% q 42%
drop_on_leverage combo_24h 24h all  n=602  excess +0.36% [-0.30,+1.02] up 68%/52% q 83%
drop_on_leverage combo_24h 48h all  n=595  excess +0.56% [-0.34,+1.55] up 63%/52% q 73%
```
Период 2020-09-01 … 2026-10-21, 53 771 часовая точка, 520 тестов признаков и 480 тестов состояний.
