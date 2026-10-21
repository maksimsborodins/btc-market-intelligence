import unittest
from unittest import mock

import requests

from btcmi import http


class FakeResp:
    def __init__(self, status=200, payload=None, content=b"", headers=None, text=""):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.headers = headers or {}
        self.text = text or str(payload)

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class HttpTests(unittest.TestCase):
    def setUp(self):
        p = mock.patch("btcmi.http.time.sleep")
        self.sleep = p.start()
        self.addCleanup(p.stop)
        p2 = mock.patch.object(http._session, "get")
        self.get = p2.start()
        self.addCleanup(p2.stop)

    def test_ok(self):
        self.get.return_value = FakeResp(200, [1, 2])
        self.assertEqual(http.get_json("https://x.test/a", {"p": 1}), [1, 2])
        self.assertEqual(self.get.call_args.kwargs["params"], {"p": 1})

    def test_user_agent_is_browser_like(self):
        self.assertIn("Mozilla/5.0", http._session.headers["User-Agent"])

    def test_retries_on_5xx_and_429_with_backoff(self):
        self.get.side_effect = [FakeResp(500), FakeResp(429), FakeResp(502), FakeResp(200, {"ok": 1})]
        self.assertEqual(http.get_json("https://x.test/a"), {"ok": 1})
        self.assertEqual(self.get.call_count, 4)
        waits = [c.args[0] for c in self.sleep.call_args_list if c.args[0] >= 1]
        self.assertEqual(waits, [1.0, 2.0, 4.0])             # exponential

    def test_retry_after_header_is_honoured(self):
        self.get.side_effect = [FakeResp(429, headers={"Retry-After": "7"}), FakeResp(200, [])]
        http.get_json("https://x.test/a")
        self.assertIn(mock.call(7.0), self.sleep.call_args_list)

    def test_retries_network_errors_then_gives_up(self):
        self.get.side_effect = requests.ConnectionError("down")
        with self.assertRaises(http.HttpError) as cm:
            http.get_json("https://x.test/a", retries=2)
        self.assertEqual(self.get.call_count, 3)
        self.assertIn("giving up", str(cm.exception))

    def test_4xx_is_not_retried(self):
        self.get.return_value = FakeResp(400, text="bad limit")
        with self.assertRaises(http.HttpError) as cm:
            http.get_json("https://x.test/a")
        self.assertEqual(cm.exception.status, 400)
        self.assertEqual(self.get.call_count, 1)

    def test_binance_error_body_with_http_200(self):
        self.get.return_value = FakeResp(200, {"code": -1130, "msg": "Invalid data sent for parameter 'limit'."})
        with self.assertRaises(http.BinanceError):
            http.get_json("https://x.test/a")
        self.get.return_value = FakeResp(200, {"code": -1121, "errorData": None})
        with self.assertRaises(http.BinanceError):
            http.get_json("https://x.test/a")

    def test_dict_without_error_markers_is_fine(self):
        self.get.return_value = FakeResp(200, {"retCode": 0, "result": {"list": []}})
        self.assertEqual(http.get_json("https://x.test/a")["retCode"], 0)

    def test_invalid_json(self):
        self.get.return_value = FakeResp(200, None, text="<html>")
        with self.assertRaises(http.HttpError):
            http.get_json("https://x.test/a")

    def test_get_bytes_and_404(self):
        self.get.return_value = FakeResp(200, content=b"PK")
        self.assertEqual(http.get_bytes("https://x.test/a.zip"), b"PK")
        self.get.return_value = FakeResp(404, text="nope")
        with self.assertRaises(http.HttpError) as cm:
            http.get_bytes("https://x.test/a.zip")
        self.assertEqual(cm.exception.status, 404)

    def test_per_host_pacing(self):
        http._last_call["paced.test"] = http.time.monotonic()
        http._pace("paced.test")
        waited = [c.args[0] for c in self.sleep.call_args_list]
        self.assertEqual(len(waited), 1)
        self.assertTrue(0 < waited[0] <= http.MIN_INTERVAL)
        self.sleep.reset_mock()
        http._pace("other-host.test")                       # a different host is not delayed
        self.sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
