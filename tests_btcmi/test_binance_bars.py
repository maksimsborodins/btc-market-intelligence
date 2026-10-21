from unittest import mock

from btcmi import db, http
from btcmi.collectors import binance_funding, binance_perp_bars, binance_premium, binance_spot_bars
from tests_btcmi.helpers import HOUR, M15, NOW, T0, BinanceKlineServer, CollectorCase, kline, make_klines


def two_interval_server(n_1h=10, n_15m=10, max_limit=1000):
    return BinanceKlineServer({"1h": make_klines(T0, n_1h, HOUR), "15m": make_klines(T0, n_15m, M15)},
                              max_limit=max_limit)


class SpotBarsTests(CollectorCase):
    def test_parses_bars_for_both_intervals(self):
        self.get_json.side_effect = two_interval_server(3, 2)
        self.assertEqual(binance_spot_bars.run(self.conn, T0), 5)
        row = self.conn.execute(
            "SELECT venue,symbol,interval,ts,open,high,low,close,volume,quote_volume,taker_buy_volume,trades "
            "FROM bars WHERE interval='1h' AND ts=?", (T0,)).fetchone()
        self.assertEqual(row, ("binance_spot", "BTCUSDT", "1h", T0, 29000.0, 29050.0, 28950.0, 29010.0,
                               100.0, 100 * 29000.0, 40.0, 1000))
        self.assertEqual(self.count("bars", "interval='15m'"), 2)
        self.assertEqual(self.get_json.call_args_list[0].args[0],
                         "https://api.binance.com/api/v3/klines")

    def test_pages_forward_until_exhausted(self):
        server = two_interval_server(10, 4)
        self.get_json.side_effect = server
        with mock.patch.object(binance_spot_bars, "LIMIT", 3):
            self.assertEqual(binance_spot_bars.run(self.conn, T0), 14)
        self.assertEqual(self.count("bars", "interval='1h'"), 10)
        starts = [p["startTime"] for _, p in server.calls if p["interval"] == "1h"]
        self.assertEqual(starts, [T0 + k * 3 * HOUR for k in range(4)])      # 3+3+3+1, short page ends it
        self.assertEqual(db.gaps(self.conn, venue="binance_spot", symbol="BTCUSDT", interval="1h"), [])

    def test_resume_second_run_writes_nothing(self):
        server = two_interval_server(10, 10)
        self.get_json.side_effect = server
        self.assertEqual(binance_spot_bars.run(self.conn, T0), 20)
        server.calls.clear()
        self.assertEqual(binance_spot_bars.run(self.conn, T0), 0)
        first = [p for _, p in server.calls if p["interval"] == "1h"][0]
        self.assertEqual(first["startTime"], T0 + 10 * HOUR)                 # last stored + one step

    def test_unfinished_bar_is_not_stored(self):
        self.get_json.side_effect = two_interval_server(10, 0)
        self.now = T0 + 5 * HOUR + 1800_000                                  # bar #5 is still open
        binance_spot_bars.run(self.conn, T0)
        self.assertEqual(db.last_ts(self.conn, venue="binance_spot", symbol="BTCUSDT", interval="1h"),
                         T0 + 4 * HOUR)
        self.now = NOW                                                       # later it is picked up
        self.assertEqual(binance_spot_bars.run(self.conn, T0), 5)

    def test_falls_back_to_data_api_host(self):
        server = two_interval_server(2, 2)

        def flaky(url, params=None, **kw):
            if url.startswith("https://api.binance.com"):
                raise http.HttpError("HTTP 451", 451, url)
            return server(url, params)

        self.get_json.side_effect = flaky
        self.assertEqual(binance_spot_bars.run(self.conn, T0), 4)
        urls = {c.args[0] for c in self.get_json.call_args_list}
        self.assertIn("https://data-api.binance.vision/api/v3/klines", urls)

    def test_end_ms_limits_range(self):
        self.get_json.side_effect = two_interval_server(10, 0)
        binance_spot_bars.run(self.conn, T0, end_ms=T0 + 3 * HOUR)
        self.assertEqual(db.last_ts(self.conn, venue="binance_spot", symbol="BTCUSDT", interval="1h"),
                         T0 + 3 * HOUR)


class PerpBarsTests(CollectorCase):
    def test_parses_and_uses_perp_endpoint_with_1500_limit(self):
        server = two_interval_server(3, 3, max_limit=1500)       # a limit of 1501 would be HTTP 400
        self.get_json.side_effect = server
        self.assertEqual(binance_perp_bars.run(self.conn, T0), 6)
        self.assertEqual(server.calls[0][0], "https://fapi.binance.com/fapi/v1/klines")
        self.assertEqual(server.calls[0][1]["limit"], 1500)
        row = self.conn.execute("SELECT venue, taker_buy_volume, trades FROM bars WHERE ts=? AND interval='1h'",
                                (T0,)).fetchone()
        self.assertEqual(row, ("binance_perp", 40.0, 1000))

    def test_pages_forward(self):
        server = two_interval_server(7, 0, max_limit=1500)
        self.get_json.side_effect = server
        with mock.patch.object(binance_perp_bars, "LIMIT", 3):
            self.assertEqual(binance_perp_bars.run(self.conn, T0), 7)
        self.assertEqual(len([c for c in server.calls if c[1]["interval"] == "1h"]), 3)

    def test_placeholder_bars_before_2019_09_09_are_dropped(self):
        placeholder = [binance_perp_bars.MIN_TS - 2 * HOUR, "10000", "10000", "10000", "10000", "0",
                       binance_perp_bars.MIN_TS - HOUR - 1, "0", 0, "0", "0", "0"]
        placeholder2 = list(placeholder)
        placeholder2[0] = binance_perp_bars.MIN_TS - HOUR
        real = kline(binance_perp_bars.MIN_TS)

        def server(url, params=None, **kw):
            if params["interval"] != "1h":
                return []
            return [placeholder, placeholder2, real]          # returned even if startTime is later

        self.get_json.side_effect = server
        self.now = binance_perp_bars.MIN_TS + DAY_MS
        self.assertEqual(binance_perp_bars.run(self.conn, 0), 1)
        self.assertEqual(db.first_ts(self.conn, venue="binance_perp", symbol="BTCUSDT", interval="1h"),
                         binance_perp_bars.MIN_TS)
        # and the request never asks for the placeholder period
        starts = [c.args[1]["startTime"] for c in self.get_json.call_args_list]
        self.assertTrue(all(s >= binance_perp_bars.MIN_TS for s in starts))

    def test_resume(self):
        server = two_interval_server(5, 5, max_limit=1500)
        self.get_json.side_effect = server
        self.assertEqual(binance_perp_bars.run(self.conn, T0), 10)
        self.assertEqual(binance_perp_bars.run(self.conn, T0), 0)


DAY_MS = 86_400_000


class PremiumTests(CollectorCase):
    def test_close_stored_as_premium_with_available_at_plus_1h(self):
        bars = [[T0 + k * HOUR, "0.0001", "0.0002", "-0.0001", f"0.000{k + 1}", "0", T0 + (k + 1) * HOUR - 1,
                 "0", 0, "0", "0", "0"] for k in range(3)]
        server = BinanceKlineServer({"1h": bars}, max_limit=1500)
        self.get_json.side_effect = server
        self.assertEqual(binance_premium.run(self.conn, T0), 3)
        self.assertEqual(server.calls[0][0], "https://fapi.binance.com/fapi/v1/premiumIndexKlines")
        rows = self.conn.execute("SELECT ts, value, available_at FROM series WHERE metric='binance.premium' "
                                 "ORDER BY ts").fetchall()
        self.assertEqual(rows, [(T0 + k * HOUR, float(f"0.000{k + 1}"), T0 + (k + 1) * HOUR) for k in range(3)])

    def test_pages_resume_and_open_bar(self):
        server = BinanceKlineServer({"1h": make_klines(T0, 8, HOUR)}, max_limit=1500)
        self.get_json.side_effect = server
        self.now = T0 + 6 * HOUR + 10                                     # bar #6 and #7 not closed
        with mock.patch.object(binance_premium, "LIMIT", 3):
            self.assertEqual(binance_premium.run(self.conn, T0), 6)
        self.assertEqual(binance_premium.run(self.conn, T0), 0)
        self.now = NOW
        self.assertEqual(binance_premium.run(self.conn, T0), 2)           # open bars arrive once closed


class FundingTests(CollectorCase):
    def rows(self, n, first=T0 + 8 * HOUR + 5):
        return [{"symbol": "BTCUSDT", "fundingTime": first + k * 8 * HOUR, "fundingRate": f"0.0001{k}",
                 "markPrice": "29000.0"} for k in range(n)]

    def server(self, data):
        calls = []

        def f(url, params=None, **kw):
            calls.append(dict(params))
            assert params["limit"] <= 1000
            if params["startTime"] == 0:                                  # real API ignores 0 -> newest rows
                return data[-params["limit"]:]
            return [r for r in data if r["fundingTime"] >= params["startTime"]][:params["limit"]]

        f.calls = calls
        return f

    def test_parse_ts_equals_available_at_equals_funding_time(self):
        self.get_json.side_effect = self.server(self.rows(2))
        self.assertEqual(binance_funding.run(self.conn, T0), 2)
        rows = self.conn.execute("SELECT metric, ts, value, available_at FROM series ORDER BY ts").fetchall()
        self.assertEqual(rows[0], ("binance.funding", T0 + 8 * HOUR + 5, 0.00010, T0 + 8 * HOUR + 5))
        self.assertEqual(rows[1][2], 0.00011)

    def test_never_sends_start_time_zero(self):
        server = self.server(self.rows(2))
        self.get_json.side_effect = server
        binance_funding.run(self.conn, 0)
        self.assertTrue(all(c["startTime"] >= binance_funding.EARLIEST for c in server.calls))

    def test_pages_forward_and_resumes(self):
        server = self.server(self.rows(7))
        self.get_json.side_effect = server
        with mock.patch.object(binance_funding, "LIMIT", 3):
            self.assertEqual(binance_funding.run(self.conn, T0), 7)
        self.assertEqual(len(server.calls), 3)
        server.calls.clear()
        self.assertEqual(binance_funding.run(self.conn, T0), 0)
        self.assertEqual(server.calls[0]["startTime"], T0 + 8 * HOUR + 5 + 6 * 8 * HOUR + 1)

    def test_error_body_with_http_200_propagates(self):
        self.get_json.side_effect = http.BinanceError("limit", 200)
        with self.assertRaises(http.BinanceError):
            binance_funding.run(self.conn, T0)


if __name__ == "__main__":
    import unittest
    unittest.main()
