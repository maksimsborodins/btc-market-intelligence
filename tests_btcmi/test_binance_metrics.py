import io
import zipfile
from unittest import mock

from btcmi import db, http
from btcmi.collectors import binance_metrics, binance_metrics_recent
from btcmi.collectors import _common as C
from tests_btcmi.helpers import DAY, M5, NOW, CollectorCase

HEADER = ("create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,"
          "sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio")


def stamp(ms):
    import datetime
    return datetime.datetime.fromtimestamp(ms / 1000, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def make_zip(day_ms, n=3, dup_first=False, first_offset=0):
    """Daily metrics zip with n 5-minute rows starting at day_ms + first_offset."""
    lines = [HEADER]
    for k in range(n):
        ts = day_ms + first_offset + k * M5
        lines.append(f"{stamp(ts)},BTCUSDT,{1000 + k}.5,{2_000_000 + k}.25,1.1,1.2,1.3,0.{k + 5}")
        if dup_first and k == 0:
            lines.append(lines[-1])                      # exact duplicate row, as in the real files
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("BTCUSDT-metrics-x.csv", "\n".join(lines) + "\n")
    return buf.getvalue()


def zip_server(days: dict, missing=()):
    """get_bytes fake: days maps 'YYYY-MM-DD' -> bytes; `missing` days answer 404."""
    calls = []

    def f(url, *a, **kw):
        calls.append(url)
        day = url.rsplit("-metrics-", 1)[1][:-4]
        if day in missing or day not in days:
            raise http.HttpError("HTTP 404", 404, url)
        return days[day]

    f.calls = calls
    return f


D1 = C.utc_ms(2021, 1, 5)


class BulkMetricsTests(CollectorCase):
    def test_parse_zip_maps_columns_and_dedupes_create_time(self):
        rows = binance_metrics.parse_zip(make_zip(D1, n=3, dup_first=True))
        self.assertEqual(len(rows), 3 * 5)                              # 5 metrics x 3 distinct timestamps
        by = {(r["metric"], r["ts"]): r for r in rows}
        r = by[("binance.oi", D1)]
        self.assertEqual((r["value"], r["available_at"]), (1000.5, D1))
        self.assertEqual(by[("binance.oi_usd", D1 + M5)]["value"], 2_000_001.25)
        self.assertEqual(by[("binance.top_ls_ratio", D1)]["value"], 1.2)
        self.assertEqual(by[("binance.ls_ratio", D1)]["value"], 1.3)
        self.assertEqual(by[("binance.taker_ls_vol_ratio", D1 + 2 * M5)]["value"], 0.7)
        self.assertEqual({r["metric"] for r in rows}, {"binance.oi", "binance.oi_usd", "binance.top_ls_ratio",
                                                       "binance.ls_ratio", "binance.taker_ls_vol_ratio"})

    def test_downloads_each_day_until_yesterday_never_today(self):
        # NOW = 2021-01-10 00:00 -> today is 2021-01-10, yesterday 2021-01-09
        days = {f"2021-01-0{d}": make_zip(C.utc_ms(2021, 1, d)) for d in range(7, 10)}
        days["2021-01-10"] = make_zip(C.utc_ms(2021, 1, 10))
        server = zip_server(days)
        self.get_bytes.side_effect = server
        self.now = NOW + 3600_000
        self.assertEqual(binance_metrics.run(self.conn, C.utc_ms(2021, 1, 7)), 3 * 3 * 5)
        self.assertEqual([u.rsplit("-", 3)[-3:] for u in server.calls],
                         [["2021", "01", "07.zip"], ["2021", "01", "08.zip"], ["2021", "01", "09.zip"]])
        self.assertTrue(server.calls[0].startswith(
            "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-"))

    def test_resume_skips_stored_days(self):
        days = {f"2021-01-0{d}": make_zip(C.utc_ms(2021, 1, d), n=288) for d in range(7, 10)}
        server = zip_server(days)
        self.get_bytes.side_effect = server
        self.assertEqual(binance_metrics.run(self.conn, C.utc_ms(2021, 1, 7)), 3 * 288 * 5)
        server.calls.clear()
        self.assertEqual(binance_metrics.run(self.conn, C.utc_ms(2021, 1, 7)), 0)
        self.assertEqual(server.calls, [])                              # nothing downloaded again

    def test_resume_redownloads_a_partially_stored_day(self):
        day = C.utc_ms(2021, 1, 8)
        db.upsert_series(self.conn, [{"metric": "binance.oi", "ts": day + 10 * M5, "value": 1.0,
                                      "available_at": day + 10 * M5}])
        server = zip_server({"2021-01-08": make_zip(day, n=288), "2021-01-09": make_zip(day + DAY, n=288)})
        self.get_bytes.side_effect = server
        binance_metrics.run(self.conn, C.utc_ms(2021, 1, 1))
        self.assertEqual([u[-14:] for u in server.calls], ["2021-01-08.zip", "2021-01-09.zip"])

    def test_missing_day_404_is_skipped_and_run_continues(self):
        days = {"2021-01-07": make_zip(C.utc_ms(2021, 1, 7)), "2021-01-09": make_zip(C.utc_ms(2021, 1, 9))}
        server = zip_server(days)                                        # 2021-01-08 -> 404
        self.get_bytes.side_effect = server
        self.assertEqual(binance_metrics.run(self.conn, C.utc_ms(2021, 1, 7)), 2 * 3 * 5)
        self.assertEqual(len(server.calls), 3)

    def test_other_http_errors_propagate(self):
        self.get_bytes.side_effect = http.HttpError("HTTP 500", 500)
        with self.assertRaises(http.HttpError):
            binance_metrics.run(self.conn, C.utc_ms(2021, 1, 7))

    def test_never_before_first_published_day(self):
        server = zip_server({})
        self.get_bytes.side_effect = server
        self.now = C.utc_ms(2020, 9, 4)
        binance_metrics.run(self.conn, 0)
        self.assertTrue(server.calls[0].endswith("BTCUSDT-metrics-2020-09-01.zip"))
        self.assertEqual(len(server.calls), 3)                          # 09-01, 09-02, 09-03 (yesterday)


class FakeFuturesData:
    """Fake of futures/data endpoints: needs endTime; ascending; honours startTime/endTime/limit."""

    FIELDS = {"openInterestHist": {"sumOpenInterest": "{v}", "sumOpenInterestValue": "{v}00"},
              "topLongShortPositionRatio": {"longShortRatio": "1.{v}"},
              "globalLongShortAccountRatio": {"longShortRatio": "2.{v}"},
              "takerlongshortRatio": {"buySellRatio": "0.{v}"}}

    def __init__(self, first_ts, n):
        self.points = [first_ts + k * M5 for k in range(n)]
        self.calls = []

    def __call__(self, url, params=None, **kw):
        self.calls.append((url.rsplit("/", 1)[1], dict(params)))
        if "endTime" not in params:
            return [{"timestamp": self.points[-1]}]                     # real API: startTime ignored w/o endTime
        assert params["period"] == "5m" and params["limit"] <= 500
        name = url.rsplit("/", 1)[1]
        out = []
        for i, ts in enumerate(self.points):
            if params["startTime"] <= ts <= params["endTime"]:
                rec = {"symbol": "BTCUSDT", "timestamp": ts}
                for field, fmt in self.FIELDS[name].items():
                    rec[field] = fmt.format(v=i)
                out.append(rec)
        return out[:params["limit"]]


class RecentMetricsTests(CollectorCase):
    def test_parse_all_four_endpoints(self):
        first = NOW - 5 * M5
        fake = FakeFuturesData(first, 6)
        self.get_json.side_effect = fake
        written = binance_metrics_recent.run(self.conn, first)
        self.assertEqual(written, 6 * 5)                                 # oi, oi_usd, top, ls, taker
        self.assertEqual({n for n, _ in fake.calls},
                         {"openInterestHist", "topLongShortPositionRatio", "globalLongShortAccountRatio",
                          "takerlongshortRatio"})
        rows = dict(((m, t), (v, a)) for m, t, v, a in self.conn.execute(
            "SELECT metric, ts, value, available_at FROM series"))
        self.assertEqual(rows[("binance.oi", first)], (0.0, first))
        self.assertEqual(rows[("binance.oi_usd", first + M5)], (100.0, first + M5))
        self.assertEqual(rows[("binance.top_ls_ratio", first + 2 * M5)], (1.2, first + 2 * M5))
        self.assertEqual(rows[("binance.ls_ratio", first)][0], 2.0)
        self.assertEqual(rows[("binance.taker_ls_vol_ratio", first + 5 * M5)], (0.5, first + 5 * M5))

    def test_windows_always_carry_endtime_and_cover_the_range(self):
        first = NOW - 9 * M5
        fake = FakeFuturesData(first, 10)
        self.get_json.side_effect = fake
        with mock.patch.object(binance_metrics_recent, "LIMIT", 4):
            self.assertEqual(binance_metrics_recent.run(self.conn, first), 10 * 5)
        self.assertTrue(all("endTime" in p for _, p in fake.calls))
        oi_calls = [p for n, p in fake.calls if n == "openInterestHist"]
        self.assertEqual(len(oi_calls), 3)                               # 4 + 4 + 2 points
        self.assertEqual(self.count("series", "metric='binance.oi'"), 10)

    def test_resume_writes_nothing_second_time(self):
        first = NOW - 9 * M5
        fake = FakeFuturesData(first, 10)
        self.get_json.side_effect = fake
        binance_metrics_recent.run(self.conn, first)
        fake.calls.clear()
        self.assertEqual(binance_metrics_recent.run(self.conn, first), 0)
        self.assertEqual(fake.calls, [])                                 # nothing newer than the last point

    def test_new_points_after_the_last_stored_are_fetched(self):
        first = NOW - 9 * M5
        fake = FakeFuturesData(first, 10)
        self.get_json.side_effect = fake
        self.now = first + 5 * M5
        binance_metrics_recent.run(self.conn, first)
        self.assertEqual(db.last_ts(self.conn, metric="binance.oi"), first + 5 * M5)
        self.now = NOW
        self.assertEqual(binance_metrics_recent.run(self.conn, first), 4 * 5)

    def test_start_is_clamped_to_30_day_limit(self):
        fake = FakeFuturesData(NOW - 2 * M5, 3)
        self.get_json.side_effect = fake
        binance_metrics_recent.run(self.conn, 0)
        first_oi = [p for n, p in fake.calls if n == "openInterestHist"][0]
        self.assertGreaterEqual(first_oi["startTime"], NOW - 30 * DAY)
        self.assertGreaterEqual(first_oi["startTime"], NOW - binance_metrics_recent.RECENT_DAYS * DAY)

    def test_does_not_store_points_in_the_future(self):
        fake = FakeFuturesData(NOW - 2 * M5, 3)                          # last point == NOW
        self.get_json.side_effect = fake
        self.now = NOW - M5
        binance_metrics_recent.run(self.conn, NOW - 2 * M5)
        self.assertEqual(db.last_ts(self.conn, metric="binance.oi"), NOW - M5)


if __name__ == "__main__":
    import unittest
    unittest.main()
