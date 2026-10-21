"""The user's manual strategies as mechanical rules, simulated on Binance BTCUSDT perp bars.

Every trade risks RISK_USD: size = RISK_USD / |entry - stop|. Costs follow BingX perps: stop and market orders pay the
taker fee plus slippage, take-profit limits pay the maker fee, funding is charged for the time held. Trades are walked
on 15-minute bars; inside one bar the stop is assumed to come first (conservative), and a take-profit is never
credited on the bar the position was opened in.

Oligator (1h): Bill Williams Alligator and fractals. A fractal beyond the jaw arms a trigger; price taking it opens a
position in that direction; the stop goes behind the latest fractal on the other side of the jaw.
RSI30m (30m): RSI(14) at 30/70, then a reversal candle (engulfing or pin bar); stop behind the pattern or at the
-0.27 Fibonacci extension; take-profits at retracements of the impulse.
Discretionary parts (levels, liquidity, volume profile, "the market looks dead") cannot be reproduced; they are
approximated where noted or left out, and the report says so.
"""

from __future__ import annotations

import math
import zoneinfo
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from btcmi.db import read_bars, read_series

RISK_USD = 10.0
TAKER = 0.0005
MAKER = 0.0002
SLIPPAGE = 0.0002          # on stop and market fills
FUNDING_8H = 0.0001        # average funding paid per 8 h held (conservative: always paid)
STOP_BUFFER = 0.0005       # stop placed 0.05% beyond the fractal / pattern extreme
MIN_STOP = 0.0015          # a stop closer than 0.15% is not a real trade (fees > 50% of risk)
M15 = 900_000
HOUR_MS = 3_600_000
RIGA = zoneinfo.ZoneInfo("Europe/Riga")


# --- data ---

def load_15m(conn, start_ms=None, end_ms=None) -> pd.DataFrame:
    """Perp 15m bars on a gapless grid, index = bar open (ms)."""
    b = read_bars(conn, "binance_perp", "BTCUSDT", "15m", start_ms, end_ms).set_index("ts")
    grid = np.arange(b.index.min(), b.index.max() + M15, M15, dtype="int64")
    return b.reindex(grid)[["open", "high", "low", "close", "volume"]]


def resample(b15: pd.DataFrame, minutes: int) -> pd.DataFrame:
    """Aggregate 15m bars into `minutes` bars, index = bar open (ms). Incomplete bars are dropped."""
    step = minutes * 60_000
    key = (b15.index // step) * step
    g = b15.groupby(key)
    out = pd.DataFrame({"open": g["open"].first(), "high": g["high"].max(), "low": g["low"].min(),
                        "close": g["close"].last(), "volume": g["volume"].sum(), "n": g["close"].count()})
    return out[out["n"] == minutes // 15].drop(columns="n")


# --- trade simulation ---

@dataclass
class Trade:
    strategy: str
    side: int                 # +1 long, -1 short
    entry_ts: int
    entry: float
    stop: float
    exit_ts: int = 0
    exit_reason: str = ""
    r_net: float = 0.0
    r_gross: float = 0.0
    fee_r: float = 0.0
    tags: dict = field(default_factory=dict)

    @property
    def stop_pct(self) -> float:
        return abs(self.entry - self.stop) / self.entry


FUNDING: tuple[np.ndarray, np.ndarray] | None = None   # (funding times ms, rates), set by set_funding()


def set_funding(conn) -> None:
    """Use Binance's real funding history (longs pay a positive rate, shorts receive it) instead of FUNDING_8H."""
    global FUNDING
    s = read_series(conn, "binance.funding")
    FUNDING = (s["ts"].to_numpy(dtype="int64"), s["value"].to_numpy(dtype="float64"))


def _funding_paid(side: int, notional: float, start_ms: int, end_ms: int) -> float:
    if FUNDING is None:
        return notional * FUNDING_8H * (end_ms - start_ms) / HOUR_MS / 8
    t, rate = FUNDING
    a, b = np.searchsorted(t, start_ms, side="right"), np.searchsorted(t, end_ms, side="right")
    return side * notional * float(rate[a:b].sum())


def simulate(b15: pd.DataFrame, trade: Trade, entry_taker: bool, targets: list[tuple[float, float]],
             be_after_first: bool, trail: list[tuple[int, float]] | None, max_hold_h: int) -> Trade:
    """Walk 15m bars from the entry bar. targets: (price, fraction of the position); the rest exits at the stop,
    on a trail update or at max hold. trail: (time known, new stop) sorted by time; a stop only moves in favour.
    Funding is charged on the full position for the whole hold (slightly conservative after partial exits)."""
    side, entry = trade.side, trade.entry
    size = RISK_USD / abs(entry - trade.stop)
    notional = size * entry
    fees = notional * (TAKER + SLIPPAGE if entry_taker else MAKER)
    ts = b15.index.to_numpy()
    o, h, l, c = (b15[k].to_numpy() for k in ("open", "high", "low", "close"))
    j = int(np.searchsorted(ts, trade.entry_ts, side="right")) - 1   # bar that contains the entry
    stop, left, gross, ti, k = trade.stop, 1.0, 0.0, 0, 0
    pending = sorted(targets, key=lambda t: side * t[0])
    end_ts = trade.entry_ts + max_hold_h * HOUR_MS
    reason, last_ts = "end_of_data", trade.entry_ts
    first_bar = True
    while j < len(ts) and left > 1e-9:
        if np.isnan(o[j]):
            j += 1
            continue
        while trail and ti < len(trail) and trail[ti][0] <= ts[j]:
            new = trail[ti][1]
            if side * (new - stop) > 0:
                stop = new
            ti += 1
        last_ts = ts[j]
        adverse = l[j] if side > 0 else h[j]
        if not first_bar and side * (o[j] - stop) <= 0:            # gapped through the stop
            px, reason = o[j], "stop"
        elif side * (adverse - stop) <= 0:
            px, reason = stop, "stop"
        else:
            px = None
        if px is not None:
            gross += left * size * side * (px - entry)
            fees += left * size * px * (TAKER + SLIPPAGE)
            left = 0.0
            break
        if not first_bar:
            favourable = h[j] if side > 0 else l[j]
            while k < len(pending) and side * (favourable - pending[k][0]) >= 0:
                px, frac = pending[k]
                frac = min(frac, left)
                gross += frac * size * side * (px - entry)
                fees += frac * size * px * MAKER
                left -= frac
                k += 1
                if be_after_first and side * (entry - stop) > 0:
                    stop = entry
            if left <= 1e-9:
                reason = "targets"
                break
        if ts[j] + M15 >= end_ts:
            gross += left * size * side * (c[j] - entry)
            fees += left * size * c[j] * (TAKER + SLIPPAGE)
            left, reason = 0.0, "time"
            break
        first_bar = False
        j += 1
    if left > 1e-9:   # data ended: mark to the last close
        gross += left * size * side * (c[j - 1] - entry)
    fees += _funding_paid(side, notional, trade.entry_ts, int(last_ts + M15))
    trade.exit_ts, trade.exit_reason = int(last_ts + M15), reason
    trade.r_gross, trade.fee_r, trade.r_net = gross / RISK_USD, fees / RISK_USD, (gross - fees) / RISK_USD
    return trade


# --- indicators ---

def alligator(b: pd.DataFrame) -> pd.DataFrame:
    """Bill Williams Alligator on the median price; the forward shift means the value at t uses data up to t - shift."""
    med = (b["high"] + b["low"]) / 2

    def smma(n):
        return med.ewm(alpha=1 / n, adjust=False).mean()
    return pd.DataFrame({"jaw": smma(13).shift(8), "teeth": smma(8).shift(5), "lips": smma(5).shift(3)}, index=b.index)


def fractals(b: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """5-bar fractals: bar i is an up (down) fractal when its high (low) is above (below) the two bars on each side.
    Known only at the close of bar i + 2."""
    h, l = b["high"].to_numpy(), b["low"].to_numpy()
    up = np.zeros(len(h), bool)
    dn = np.zeros(len(h), bool)
    up[2:-2] = (h[2:-2] > h[1:-3]) & (h[2:-2] > h[:-4]) & (h[2:-2] > h[3:-1]) & (h[2:-2] > h[4:])
    dn[2:-2] = (l[2:-2] < l[1:-3]) & (l[2:-2] < l[:-4]) & (l[2:-2] < l[3:-1]) & (l[2:-2] < l[4:])
    return up, dn


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    down = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + up / down.replace(0, np.nan))


def riga_session(ts_ms: int) -> str:
    t = pd.Timestamp(ts_ms, unit="ms", tz="UTC").tz_convert(RIGA)
    hr = t.hour + t.minute / 60
    if 16.5 <= hr < 23:
        return "us 16:30-23"
    if 10 <= hr < 16.5:
        return "europe 10-16:30"
    if 2 <= hr < 10:
        return "asia 02-10"
    return "night 23-02"


# --- Oligator ---

OLIGATOR_EXITS = {
    # name: (targets as % moves with fractions, move stop to breakeven after the first target, trail behind fractals)
    "trail": ([], False, True),
    "tp_1pct": ([(0.01, 1.0)], False, False),
    "ladder": ([(0.01, 1 / 3), (0.02, 1 / 3)], True, True),
}


COST_STOP = 0.0095   # stop at which a full round trip (~0.14%) is 15% of the risk: the "fees eat the trade" filter


def oligator(b15: pd.DataFrame, exit_rule: str = "ladder", widening_only: bool = False, min_stop: float = MIN_STOP,
             max_hold_h: int = 14 * 24) -> list[Trade]:
    """widening_only: enter only when the mouth is open in the trade's direction and opening further (the user's
    "no trading in a range" rule). min_stop: skip trades whose stop is closer than this."""
    b = resample(b15, 60).dropna()
    al = alligator(b)
    up, dn = fractals(b)
    ts = b.index.to_numpy()
    h, l = b["high"].to_numpy(), b["low"].to_numpy()
    jaw, teeth, lips = (al[k].to_numpy() for k in ("jaw", "teeth", "lips"))
    known = ts + 3 * HOUR_MS                       # fractal at i is confirmed at the close of i + 2
    # fractals beyond the jaw, in order of confirmation: (known, level, bar index)
    up_beyond = [(known[i], h[i], i) for i in np.flatnonzero(up) if h[i] > jaw[i]]
    dn_beyond = [(known[i], l[i], i) for i in np.flatnonzero(dn) if l[i] < jaw[i]]
    all_up = [(known[i], h[i]) for i in np.flatnonzero(up)]
    all_dn = [(known[i], l[i]) for i in np.flatnonzero(dn)]
    up_known = np.array([u[0] for u in up_beyond])
    dn_known = np.array([d[0] for d in dn_beyond])
    targets_def, be, use_trail = OLIGATOR_EXITS[exit_rule]

    trades: list[Trade] = []
    t15 = b15.index.to_numpy()
    h15, l15, o15 = b15["high"].to_numpy(), b15["low"].to_numpy(), b15["open"].to_numpy()
    free_at = 0
    taken_up, taken_dn = set(), set()
    for bi in range(len(ts) - 1):
        now = ts[bi] + HOUR_MS                     # close of bar bi: decisions for the next hour
        if now < free_at or np.isnan(jaw[bi]):
            continue
        iu = int(np.searchsorted(up_known, now, side="right")) - 1
        idn = int(np.searchsorted(dn_known, now, side="right")) - 1
        trig_long = up_beyond[iu] if iu >= 0 and iu not in taken_up else None
        trig_short = dn_beyond[idn] if idn >= 0 and idn not in taken_dn else None
        if trig_long is None and trig_short is None:
            continue
        # walk the next hour on 15m bars: first trigger taken wins
        j0 = int(np.searchsorted(t15, now))
        hit, long_hit, short_hit = None, False, False
        for j in range(j0, min(j0 + 4, len(t15))):
            if np.isnan(h15[j]):
                continue
            long_hit = trig_long is not None and h15[j] >= trig_long[1]
            short_hit = trig_short is not None and l15[j] <= trig_short[1]
            if long_hit and short_hit:
                hit = "both"
            elif long_hit:
                hit = ("long", j)
            elif short_hit:
                hit = ("short", j)
            if hit:
                break
        if hit is None:
            continue
        if long_hit:
            taken_up.add(iu)
        if short_hit:
            taken_dn.add(idn)
        if hit == "both":
            continue
        side_name, j = hit
        side = 1 if side_name == "long" else -1
        level = trig_long[1] if side > 0 else trig_short[1]
        entry = max(level, o15[j]) if side > 0 else min(level, o15[j])
        # stop: latest confirmed fractal on the other side of the jaw
        other = dn_beyond if side > 0 else up_beyond
        other_known = dn_known if side > 0 else up_known
        io = int(np.searchsorted(other_known, now, side="right")) - 1
        if io < 0:
            continue
        stop = other[io][1] * (1 - side * STOP_BUFFER)
        if side * (entry - stop) <= 0 or abs(entry - stop) / entry < min_stop:
            continue
        mouth = side * (lips[bi] - teeth[bi]) > 0 and side * (teeth[bi] - jaw[bi]) > 0
        spread = side * (lips[bi] - jaw[bi])
        widening = mouth and bi >= 3 and spread > side * (lips[bi - 3] - jaw[bi - 3])
        if widening_only and not widening:
            continue
        # previous trend: side of the mouth 24 h ago; a signal against it is a "first signal after a trend"
        prev = np.sign(lips[bi - 24] - jaw[bi - 24]) if bi >= 24 else 0
        t = Trade("oligator_" + exit_rule, side, int(t15[j]), float(entry), float(stop),
                  tags={"mouth_open": bool(mouth), "widening": bool(widening),
                        "against_prev_trend": bool(prev != 0 and prev != side),
                        "session": riga_session(int(t15[j]))})
        trail = None
        if use_trail:   # any new opposite fractal, beyond the jaw or not
            trail = [(k_, lv * (1 - side * STOP_BUFFER)) for k_, lv in (all_dn if side > 0 else all_up) if k_ > now]
        targets = [(entry * (1 + side * pct), frac) for pct, frac in targets_def]
        trades.append(simulate(b15, t, True, targets, be, trail, max_hold_h))
        free_at = trades[-1].exit_ts
    return trades


# --- RSI30m ---

def rsi30m(b15: pd.DataFrame, stop_rule: str = "pattern", trend_only: bool = False, min_stop: float = MIN_STOP,
           max_hold_h: int = 48) -> list[Trade]:
    b = resample(b15, 30).dropna()
    r = rsi(b["close"]).to_numpy()
    ts = b.index.to_numpy()
    o, h, l, c = (b[k].to_numpy() for k in ("open", "high", "low", "close"))
    # main trend: last completed 4h close against the 4h EMA50 (about 8 days)
    b4 = resample(b15, 240).dropna()
    trend4 = np.sign(b4["close"] - b4["close"].ewm(span=50, adjust=False).mean())
    trend4.index = trend4.index + 4 * HOUR_MS                  # known at the 4h bar's close
    trend = trend4.reindex(ts + 1_800_000, method="ffill").to_numpy()
    h1 = resample(b15, 60).dropna()
    up1, dn1 = fractals(h1)
    t1 = h1.index.to_numpy()
    fr_hi = pd.Series(np.where(up1, h1["high"], np.nan), index=t1 + 3 * HOUR_MS).dropna()
    fr_lo = pd.Series(np.where(dn1, h1["low"], np.nan), index=t1 + 3 * HOUR_MS).dropna()
    trades: list[Trade] = []
    free_at = 0
    for k in range(200, len(ts) - 1):
        close_ts = ts[k] + 1_800_000
        if close_ts < free_at:
            continue
        body = abs(c[k] - o[k])
        rng_ = h[k] - l[k]
        if rng_ <= 0:
            continue
        lower = min(o[k], c[k]) - l[k]
        upper = h[k] - max(o[k], c[k])
        for side in (1, -1):
            zone = np.nanmin(r[k - 3:k + 1]) <= 30 if side > 0 else np.nanmax(r[k - 3:k + 1]) >= 70
            if not zone:
                continue
            if side > 0:
                engulf = c[k] > o[k] and c[k - 1] < o[k - 1] and c[k] >= o[k - 1] and o[k] <= c[k - 1]
                pin = lower >= 2 * body and upper <= max(body, 0.25 * rng_) and c[k] >= l[k] + 0.6 * rng_
            else:
                engulf = c[k] < o[k] and c[k - 1] > o[k - 1] and c[k] <= o[k - 1] and o[k] >= c[k - 1]
                pin = upper >= 2 * body and lower <= max(body, 0.25 * rng_) and c[k] <= h[k] - 0.6 * rng_
            if not (engulf or pin):
                continue
            # impulse: from the extreme of the last 12 h to the extreme of the last 3 h
            if side > 0:
                imp_start, imp_end = np.nanmax(h[k - 24:k + 1]), np.nanmin(l[k - 6:k + 1])
                pattern_ext = np.nanmin(l[k - 1:k + 1])
            else:
                imp_start, imp_end = np.nanmin(l[k - 24:k + 1]), np.nanmax(h[k - 6:k + 1])
                pattern_ext = np.nanmax(h[k - 1:k + 1])
            size_ = imp_start - imp_end
            entry = o[k + 1]
            if stop_rule == "pattern":
                stop = pattern_ext * (1 - side * STOP_BUFFER)
            else:   # fib -0.27 extension beyond the impulse end
                stop = imp_end - 0.27 * size_
            tp1, tp2 = imp_end + 0.382 * size_, imp_end + 0.618 * size_
            if side * (entry - stop) <= 0 or abs(entry - stop) / entry < min_stop or side * (tp1 - entry) <= 0:
                continue
            if trend_only and trend[k] != side:
                continue
            fr = fr_lo if side > 0 else fr_hi
            near = fr[(fr.index <= close_ts - 6 * HOUR_MS) & (fr.index > close_ts - 7 * 24 * HOUR_MS)]
            level = bool(len(near) and np.min(np.abs(near.to_numpy() / pattern_ext - 1)) <= 0.003)
            t = Trade("rsi30m_" + stop_rule, side, int(ts[k + 1]), float(entry), float(stop),
                      tags={"with_trend": bool(trend[k] == side), "near_level": level,
                            "pattern": "engulfing" if engulf else "pin", "session": riga_session(int(ts[k + 1]))})
            trades.append(simulate(b15, t, True, [(tp1, 0.5), (tp2, 0.5)], True, None, max_hold_h))
            free_at = trades[-1].exit_ts
            break
    return trades


def to_frame(trades: list[Trade]) -> pd.DataFrame:
    rows = []
    for t in trades:
        rows.append({"strategy": t.strategy, "side": t.side, "entry_ts": t.entry_ts, "exit_ts": t.exit_ts,
                     "entry": t.entry, "stop": t.stop, "stop_pct": t.stop_pct, "r_net": t.r_net,
                     "r_gross": t.r_gross, "fee_r": t.fee_r, "exit_reason": t.exit_reason, **t.tags})
    return pd.DataFrame(rows)
