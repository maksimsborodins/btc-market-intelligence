from unittest import mock

from btcmi import db, http
from btcmi.collectors import bybit_bars, bybit_funding, bybit_ls_ratio, bybit_oi
from tests_btcmi.helpers import HOUR, NOW, T0, BybitServer, CollectorCase


def bar_item(k):
    ts = T0 + k * HOUR
    return [str(ts), f"{29000 + k}", f"{29050 + k}", f"{28950 + k}", f"{29010 + k}", f"{100 + k}.5", f"{3_000_000 + k}.25"]


def oi_item(k):
    return {"openInterest": f"{60000 + k}.5", "timestamp": str(T0 + k * HOUR)}


def funding_item(k):
    return {"symbol": "BTCUSDT", "fundingRate": f"0.0001{k}", "fundingRateTimestamp": str(T0 + k * 8 * HOUR)}


def ratio_item(k):
    return {"symbol": "BTCUSDT", "buyRatio": f"0.6{k}", "sellRatio": f"0.3{k}", "timestamp": str(T0 + k * HOUR)}


class BybitBarsTests(CollectorCase):
    def server(self, n=10, **kw):
        return BybitServer([bar_item(k) for k in range(n)], lambda i: int(i[0]), max_limit=1000, **kw)

    def test_parse(self):
        server = self.server(3)
        self.get_json.side_effect = server
        self.assertEqual(bybit_bars.run(self.conn, T0), 3)
        row = self.conn.execute("SELECT venue,symbol,interval,ts,open,high,low,close,volume,quote_volume,"
                                "taker_buy_volume,trades FROM bars WHERE ts=?", (T0 + HOUR,)).fetchone()
        self.assertEqual(row, ("bybit_perp", "BTCUSDT", "1h", T0 + HOUR, 29001.0, 29051.0, 28951.0, 29011.0,
                               101.5, 3_000_001.25, None, None))
        p = server.calls[0]
        self.assertEqual((p["category"], p["symbol"], p["interval"]), ("linear", "BTCUSDT", "60"))

    def test_pages_backwards_through_silent_cap(self):
        server = self.server(10, cap=4)                      # server returns at most 4 although 1000 asked
        self.get_json.side_effect = server
        self.assertEqual(bybit_bars.run(self.conn, T0), 10)
        self.assertEqual(len(server.calls), 3)
        ends = [c["end"] for c in server.calls]
        self.assertEqual(ends[1], T0 + 6 * HOUR - 1)         # page 1 held #9..#6 -> next end = oldest - 1
        self.assertEqual(db.gaps(self.conn, venue="bybit_perp", symbol="BTCUSDT", interval="1h"), [])

    def test_resume(self):
        self.get_json.side_effect = self.server(10)
        self.assertEqual(bybit_bars.run(self.conn, T0), 10)
        self.assertEqual(bybit_bars.run(self.conn, T0), 0)
        self.assertEqual(self.get_json.call_args.args[1]["start"], T0 + 10 * HOUR)

    def test_open_bar_not_stored(self):
        self.get_json.side_effect = self.server(10)
        self.now = T0 + 6 * HOUR + 10
        self.assertEqual(bybit_bars.run(self.conn, T0), 6)
        self.assertEqual(db.last_ts(self.conn, venue="bybit_perp", symbol="BTCUSDT", interval="1h"), T0 + 5 * HOUR)

    def test_error_envelope_raises(self):
        self.get_json.return_value = {"retCode": 10001, "retMsg": "params error", "result": {}}
        with self.assertRaises(http.HttpError):
            bybit_bars.run(self.conn, T0)


class BybitOiTests(CollectorCase):
    def server(self, n=10, **kw):
        return BybitServer([oi_item(k) for k in range(n)], lambda i: int(i["timestamp"]), max_limit=200, **kw)

    def test_parse_ts_equals_available_at(self):
        server = self.server(3)
        self.get_json.side_effect = server
        self.assertEqual(bybit_oi.run(self.conn, T0), 3)
        rows = self.conn.execute("SELECT metric,ts,value,available_at FROM series ORDER BY ts").fetchall()
        self.assertEqual(rows[1], ("bybit.oi", T0 + HOUR, 60001.5, T0 + HOUR))
        p = server.calls[0]
        self.assertEqual((p["intervalTime"], p["limit"]), ("1h", 200))

    def test_pages_backwards_with_cap_200(self):
        server = self.server(10, cap=3)
        self.get_json.side_effect = server
        with mock.patch.object(bybit_oi, "LIMIT", 5):
            self.assertEqual(bybit_oi.run(self.conn, T0), 10)
        self.assertEqual(self.count("series"), 10)

    def test_resume(self):
        self.get_json.side_effect = self.server(10)
        bybit_oi.run(self.conn, T0)
        self.assertEqual(bybit_oi.run(self.conn, T0), 0)

    def test_snapshot_at_open_hour_is_kept(self):
        # OI is a point-in-time snapshot: available_at = ts, so the newest point is valid immediately
        self.get_json.side_effect = self.server(10)
        self.now = T0 + 9 * HOUR + 5
        self.assertEqual(bybit_oi.run(self.conn, T0), 10)


class BybitFundingTests(CollectorCase):
    def server(self, n=12, **kw):
        return BybitServer([funding_item(k) for k in range(n)], lambda i: int(i["fundingRateTimestamp"]),
                           max_limit=200, **kw)

    def test_parse(self):
        self.get_json.side_effect = self.server(3, now=NOW)
        self.assertEqual(bybit_funding.run(self.conn, T0), 3)
        rows = self.conn.execute("SELECT metric,ts,value,available_at FROM series ORDER BY ts").fetchall()
        self.assertEqual(rows[2], ("bybit.funding", T0 + 16 * HOUR, 0.00012, T0 + 16 * HOUR))

    def test_end_time_is_capped_at_now(self):
        server = self.server(12, now=NOW)                    # future endTime would return an empty list
        self.get_json.side_effect = server
        self.assertEqual(bybit_funding.run(self.conn, T0, end_ms=NOW + 10 * HOUR), 12)
        self.assertTrue(all(c["endTime"] <= NOW for c in server.calls))
        self.assertEqual(server.calls[0]["endTime"], NOW)

    def test_pages_backwards_and_resumes(self):
        server = self.server(12, cap=5, now=NOW)
        self.get_json.side_effect = server
        with mock.patch.object(bybit_funding, "LIMIT", 5):
            self.assertEqual(bybit_funding.run(self.conn, T0), 12)
        self.assertEqual(len(server.calls), 3)
        self.assertEqual(bybit_funding.run(self.conn, T0), 0)
        self.assertEqual(server.calls[-1]["startTime"], T0 + 11 * 8 * HOUR + 1)


class BybitLsRatioTests(CollectorCase):
    def server(self, n=10, **kw):
        return BybitServer([ratio_item(k) for k in range(n)], lambda i: int(i["timestamp"]), max_limit=500, **kw)

    def test_parse_available_at_is_ts_plus_1h(self):
        server = self.server(3)
        self.get_json.side_effect = server
        self.assertEqual(bybit_ls_ratio.run(self.conn, T0), 3)
        rows = self.conn.execute("SELECT metric,ts,value,available_at FROM series ORDER BY ts").fetchall()
        self.assertEqual(rows[1], ("bybit.ls_buy_ratio", T0 + HOUR, 0.61, T0 + 2 * HOUR))
        self.assertEqual((server.calls[0]["period"], server.calls[0]["limit"]), ("1h", 500))

    def test_non_empty_cursor_does_not_loop_and_paging_is_by_end_time(self):
        server = self.server(10, cap=4)                      # nextPageCursor == "abc" in every response
        self.get_json.side_effect = server
        with mock.patch.object(bybit_ls_ratio, "LIMIT", 5):
            self.assertEqual(bybit_ls_ratio.run(self.conn, T0), 10)
        self.assertEqual(len(server.calls), 3)
        self.assertTrue(all("cursor" not in c for c in server.calls))

    def test_resume_and_open_hour(self):
        self.get_json.side_effect = self.server(10)
        self.now = T0 + 5 * HOUR + 10                        # available_at of #5 would be in the future
        self.assertEqual(bybit_ls_ratio.run(self.conn, T0), 5)
        self.now = NOW
        self.assertEqual(bybit_ls_ratio.run(self.conn, T0), 5)
        self.assertEqual(bybit_ls_ratio.run(self.conn, T0), 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
