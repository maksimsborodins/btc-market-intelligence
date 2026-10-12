"""
Empirical Verification Suite for Challenger 2:
1. Verification of Farside ETF HTML Parser behavior on rows with '-' and '0.0'.
2. Verification of Bybit duplicate orderbook call at lines 1278 vs 1322.
3. Verification of Calibration Tracker Lookbehind Bias & Event-Driven Touch.
"""

import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import btc_market_intelligence as bmi


class TestFarsideParserEmpirical(unittest.TestCase):
    """Empirically test Farside parser behavior on '-', '0.0', and in-session rows."""

    def test_parse_money_cell_primitives(self):
        """Verify primitive parsing of individual cells."""
        # Dashes and empty cells -> None
        self.assertIsNone(bmi._parse_money_cell("-"))
        self.assertIsNone(bmi._parse_money_cell("—"))
        self.assertIsNone(bmi._parse_money_cell("–"))
        self.assertIsNone(bmi._parse_money_cell(""))
        self.assertIsNone(bmi._parse_money_cell("n/a"))
        self.assertIsNone(bmi._parse_money_cell("N/A"))
        self.assertIsNone(bmi._parse_money_cell(None))

        # Numbers -> float
        self.assertEqual(bmi._parse_money_cell("0.0"), 0.0)
        self.assertEqual(bmi._parse_money_cell("0"), 0.0)
        self.assertEqual(bmi._parse_money_cell("(0.0)"), 0.0)
        self.assertEqual(bmi._parse_money_cell("12.5"), 12.5)
        self.assertEqual(bmi._parse_money_cell("(12.5)"), -12.5)
        self.assertEqual(bmi._parse_money_cell("$1,234.5"), 1234.5)

    def test_farside_in_session_pending_total_zero_behavior(self):
        """
        Verify parser behavior when Farside has an active trading day row
        where individual funds are '-' (pending) but Total is '0.0'.
        """
        html_content = """
        <html>
        <body>
        <table>
            <tr>
                <th>Date</th><th>IBIT</th><th>FBTC</th><th>BITB</th><th>ARKB</th><th>Total</th>
            </tr>
            <tr>
                <td>08 Oct 2026</td><td>50.0</td><td>25.0</td><td>10.0</td><td>15.0</td><td>100.0</td>
            </tr>
            <tr>
                <td>09 Oct 2026</td><td>40.0</td><td>30.0</td><td>10.0</td><td>20.0</td><td>100.0</td>
            </tr>
            <tr>
                <td>10 Oct 2026</td><td>60.0</td><td>40.0</td><td>10.0</td><td>10.0</td><td>120.0</td>
            </tr>
            <!-- Active/Pending session where funds are not yet reported ('-') but Total column has '0.0' -->
            <tr>
                <td>11 Oct 2026</td><td>-</td><td>-</td><td>-</td><td>-</td><td>0.0</td>
            </tr>
        </table>
        </body>
        </html>
        """
        with patch.object(bmi, "safe_get_text", return_value=html_content):
            result = bmi.fetch_btc_etf_flows()

        self.assertEqual(result["status"], "OK")
        latest = result["latest"]
        
        # Post-Fix Verification:
        # The parser correctly ignores pending in-session rows where all funds are '-' and total is 0.0,
        # preventing displacement of valid completed sessions!
        self.assertEqual(latest["date"], "2026-10-10")
        self.assertEqual(latest["total_net_flow_usd_millions"], 120.0)
        self.assertEqual(result["trading_sessions_available"], 3)
        self.assertEqual(result["latest_3_sessions_sum_usd_millions"], 320.0)

    def test_farside_all_dash_row_behavior(self):
        """
        Verify parser behavior when an in-session row has '-' in the Total column as well.
        """
        html_content = """
        <html>
        <body>
        <table>
            <tr>
                <th>Date</th><th>IBIT</th><th>FBTC</th><th>Total</th>
            </tr>
            <tr>
                <td>08 Oct 2026</td><td>50.0</td><td>25.0</td><td>75.0</td>
            </tr>
            <!-- Row where even Total is '-' -->
            <tr>
                <td>09 Oct 2026</td><td>-</td><td>-</td><td>-</td>
            </tr>
        </table>
        </body>
        </html>
        """
        with patch.object(bmi, "safe_get_text", return_value=html_content):
            result = bmi.fetch_btc_etf_flows()

        self.assertEqual(result["status"], "OK")
        latest = result["latest"]
        # When Total is '-', vals[-1] is None, so total is None -> row IS skipped!
        self.assertEqual(latest["date"], "2026-10-08")
        self.assertEqual(result["trading_sessions_available"], 1)


class TestBybitDuplicateOrderbookCallEmpirical(unittest.TestCase):
    """Empirically test whether fetch_bybit_telemetry eliminates duplicate orderbook calls."""

    @patch("btc_market_intelligence.bybit_get")
    def test_duplicate_orderbook_call_parallel(self, mock_bybit_get):
        """Verify duplicate orderbook call is eliminated in parallel=True mode."""
        # Setup mock return values
        def side_effect(endpoint, params=None):
            if endpoint == "/v5/market/tickers":
                return {"list": [{"lastPrice": "83000.0", "markPrice": "83000.0", "price24hPcnt": "0.01"}]}
            elif endpoint == "/v5/market/open-interest":
                return {"list": [{"timestamp": "1700000000000", "openInterest": "50000.0"}]}
            elif endpoint == "/v5/market/funding/history":
                return {"list": [{"fundingRate": "0.0001", "fundingRateTimestamp": "1700000000000"}]}
            elif endpoint == "/v5/market/account-ratio":
                return {"list": [{"timestamp": "1700000000000", "buyRatio": "0.5", "sellRatio": "0.5"}]}
            elif endpoint == "/v5/market/orderbook":
                return {"ts": 1700000000000, "b": [["82990.0", "1.0"]], "a": [["83010.0", "1.0"]]}
            return {}

        mock_bybit_get.side_effect = side_effect

        out = bmi.fetch_bybit_telemetry(parallel=True)
        self.assertEqual(out["status"], "OK")

        # Count calls to /v5/market/orderbook
        orderbook_calls = [
            call for call in mock_bybit_get.call_args_list
            if call[0][0] == "/v5/market/orderbook"
        ]
        
        # Post-Fix Verification:
        # Redundant duplicate sequential call is eliminated; exactly 1 call is made.
        self.assertEqual(
            len(orderbook_calls), 1,
            f"Expected exactly 1 orderbook call (redundant call eliminated), got {len(orderbook_calls)}"
        )

    @patch("btc_market_intelligence.bybit_get")
    def test_duplicate_orderbook_call_sequential(self, mock_bybit_get):
        """Verify duplicate orderbook call is eliminated in parallel=False mode."""
        def side_effect(endpoint, params=None):
            if endpoint == "/v5/market/tickers":
                return {"list": [{"lastPrice": "83000.0"}]}
            elif endpoint == "/v5/market/orderbook":
                return {"ts": 1700000000000, "b": [["82990.0", "1.0"]], "a": [["83010.0", "1.0"]]}
            return {}

        mock_bybit_get.side_effect = side_effect

        out = bmi.fetch_bybit_telemetry(parallel=False)

        orderbook_calls = [
            call for call in mock_bybit_get.call_args_list
            if call[0][0] == "/v5/market/orderbook"
        ]
        self.assertEqual(
            len(orderbook_calls), 1,
            f"Expected exactly 1 orderbook call in sequential mode, got {len(orderbook_calls)}"
        )


if __name__ == "__main__":
    unittest.main()
