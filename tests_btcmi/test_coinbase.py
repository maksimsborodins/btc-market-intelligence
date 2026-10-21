from unittest import mock
from datetime import datetime, timezone

from btcmi import db, http
from btcmi.collectors import coinbase_bars
from tests_btcmi.helpers import HOUR, NOW, T0, CollectorCase


def candle(k):
    """Coinbase wire shape: [time SECONDS, low, high, open, close, volume] (note the column order)."""
    t = (T0 + k * HOUR) // 1000
    return [t, 28950.0 + k, 29050.0 + k, 29000.0 + k, 29010.0 + k, 12.5 + k]


def parse_iso(s):
    return int(datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() * 1000)


class CoinbaseServer:
    """Newest first, `end` inclusive, more than 300 intervals -> HTTP 400 (here: more than `max_candles`)."""

    def __init__(self, candles, max_candles=300):
        self.candles = candles
        self.max_candles = max_candles
        self.calls = []

    def __call__(self, url, params=None, **kw):
        self.calls.append(dict(params))
        s, e = parse_iso(params["start"]), parse_iso(params["end"])
        assert params["granularity"] == 3600
        if (e - s) // HOUR + 1 > self.max_candles:
            raise http.HttpError("HTTP 400", 400, url)
        out = [c for c in self.candles if s <= c[0] * 1000 <= e]
        return sorted(out, key=lambda c: -c[0])


class CoinbaseTests(CollectorCase):
    def test_parse_seconds_and_column_order(self):
        self.get_json.side_effect = CoinbaseServer([candle(0), candle(1)])
        self.assertEqual(coinbase_bars.run(self.conn, T0), 2)
        row = self.conn.execute("SELECT venue,symbol,interval,ts,open,high,low,close,volume,quote_volume,"
                                "taker_buy_volume,trades FROM bars WHERE ts=?", (T0 + HOUR,)).fetchone()
        self.assertEqual(row, ("coinbase_spot", "BTC-USD", "1h", T0 + HOUR, 29001.0, 29051.0, 28951.0, 29011.0,
                               13.5, None, None, None))

    def test_windows_never_exceed_300_candles_and_cover_the_range(self):
        candles = [candle(k) for k in range(700)]
        server = CoinbaseServer(candles, max_candles=300)                # a 301-interval request raises
        self.get_json.side_effect = server
        self.now = T0 + 800 * HOUR
        self.assertEqual(coinbase_bars.run(self.conn, T0), 700)
        self.assertEqual(db.gaps(self.conn, venue="coinbase_spot", symbol="BTC-USD", interval="1h"), [])
        spans = [(parse_iso(c["end"]) - parse_iso(c["start"])) // HOUR + 1 for c in server.calls]
        self.assertTrue(all(s <= 300 for s in spans))
        self.assertEqual(parse_iso(server.calls[1]["start"]), T0 + 300 * HOUR)       # windows are contiguous

    def test_small_window_with_patched_limit(self):
        server = CoinbaseServer([candle(k) for k in range(8)], max_candles=3)
        self.get_json.side_effect = server
        with mock.patch.object(coinbase_bars, "LIMIT", 3):
            self.assertEqual(coinbase_bars.run(self.conn, T0), 8)

    def test_empty_window_does_not_stop_the_run(self):
        # hours without trades are missing in early history: a whole window can be empty
        candles = [candle(k) for k in (0, 1, 2, 9, 10)]
        self.get_json.side_effect = CoinbaseServer(candles, max_candles=3)
        with mock.patch.object(coinbase_bars, "LIMIT", 3):
            self.assertEqual(coinbase_bars.run(self.conn, T0), 5)
        self.assertEqual(db.gaps(self.conn, venue="coinbase_spot", symbol="BTC-USD", interval="1h"),
                         [(T0 + 3 * HOUR, T0 + 8 * HOUR)])

    def test_resume_second_run_writes_nothing(self):
        server = CoinbaseServer([candle(k) for k in range(5)])
        self.get_json.side_effect = server
        self.assertEqual(coinbase_bars.run(self.conn, T0), 5)
        server.calls.clear()
        self.assertEqual(coinbase_bars.run(self.conn, T0), 0)
        self.assertEqual(parse_iso(server.calls[0]["start"]), T0 + 5 * HOUR)

    def test_open_hour_not_stored(self):
        self.get_json.side_effect = CoinbaseServer([candle(k) for k in range(5)])
        self.now = T0 + 3 * HOUR + 10
        self.assertEqual(coinbase_bars.run(self.conn, T0), 3)

    def test_error_message_dict_raises(self):
        self.get_json.return_value = {"message": "NotFound"}
        with self.assertRaises(http.HttpError):
            coinbase_bars.run(self.conn, T0)

    def test_not_before_first_candle_date(self):
        server = CoinbaseServer([])
        self.get_json.side_effect = server
        self.now = coinbase_bars.EARLIEST + 3 * HOUR
        coinbase_bars.run(self.conn, 0)
        self.assertEqual(parse_iso(server.calls[0]["start"]), coinbase_bars.EARLIEST)


if __name__ == "__main__":
    import unittest
    unittest.main()
