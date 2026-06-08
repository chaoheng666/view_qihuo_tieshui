from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from src import web_app


SAMPLE_SNAPSHOT = {
    "generated_at": "2026-04-23 15:00:00",
    "symbols": {
        "IF": {
            "symbol": "IF",
            "symbol_name": "沪深300",
            "index": {
                "latest_price": 4800.0,
                "change": 12.0,
                "change_pct": 0.25,
                "quote_time": "2026-04-23 15:00:00",
                "source_index": "sina_index",
            },
            "main_contract": {
                "contract_code": "IF2606",
                "contract_name": "IF2606",
                "position": "下月",
                "expiry_date": "2026-06-19",
                "days_to_expiry": 57,
                "futures_price": 4744.8,
                "index_price": 4800.0,
                "premium_points": -55.2,
                "premium_rate": -1.15,
                "annualized_rate": -7.36,
                "volume": 51772,
                "open_interest": 141181,
                "quote_time": "2026-04-23 15:00:00",
                "source_futures": "akshare_realtime",
                "source_index": "sina_index",
                "data_quality": "ok",
                "quality_reason": "",
                "freshness_seconds": 0,
                "index_change": 12.0,
                "index_change_pct": 0.25,
            },
            "contracts": [
                {
                    "contract_code": "IF2606",
                    "contract_name": "IF2606",
                    "position": "下月",
                    "expiry_date": "2026-06-19",
                    "days_to_expiry": 57,
                    "futures_price": 4744.8,
                    "index_price": 4800.0,
                    "premium_points": -55.2,
                    "premium_rate": -1.15,
                    "annualized_rate": -7.36,
                    "volume": 51772,
                    "open_interest": 141181,
                    "quote_time": "2026-04-23 15:00:00",
                    "source_futures": "akshare_realtime",
                    "source_index": "sina_index",
                    "data_quality": "ok",
                    "quality_reason": "",
                    "freshness_seconds": 0,
                    "index_change": 12.0,
                    "index_change_pct": 0.25,
                    "change": 14.0,
                    "change_pct": 0.3,
                    "symbol": "IF",
                    "symbol_name": "沪深300",
                    "is_continuous": False,
                }
            ],
            "alerts": [],
            "quality_summary": {"main_quality": "ok", "main_reason": "", "freshness_seconds": 0, "counts": {"ok": 1}},
            "stats_30d": {"mean_30d": -0.8, "percentile_30d": 32.0, "z_score_30d": -0.7},
        },
        "IC": {
            "symbol": "IC",
            "symbol_name": "中证500",
            "index": {"latest_price": 8380.0, "change": 8.0, "change_pct": 0.1, "quote_time": "2026-04-23 15:00:00", "source_index": "sina_index"},
            "main_contract": {
                "contract_code": "IC2606",
                "contract_name": "IC2606",
                "position": "下月",
                "expiry_date": "2026-06-19",
                "days_to_expiry": 57,
                "futures_price": 8260.0,
                "index_price": 8380.0,
                "premium_points": -120.0,
                "premium_rate": -1.43,
                "annualized_rate": -9.16,
                "volume": 62000,
                "open_interest": 150000,
                "quote_time": "2026-04-23 15:00:00",
                "source_futures": "akshare_realtime",
                "source_index": "sina_index",
                "data_quality": "ok",
                "quality_reason": "",
                "freshness_seconds": 0,
                "index_change": 8.0,
                "index_change_pct": 0.1,
            },
            "contracts": [],
            "alerts": [],
            "quality_summary": {"main_quality": "ok", "main_reason": "", "freshness_seconds": 0, "counts": {}},
            "stats_30d": {"mean_30d": -1.2, "percentile_30d": 40.0, "z_score_30d": -0.2},
        },
        "IH": {
            "symbol": "IH",
            "symbol_name": "上证50",
            "index": {"latest_price": 2930.0, "change": 3.0, "change_pct": 0.1, "quote_time": "2026-04-23 15:00:00", "source_index": "sina_index"},
            "main_contract": {"contract_code": "IH2606", "premium_rate": -0.6, "annualized_rate": -3.8, "premium_points": -18.0, "futures_price": 2912.0, "index_price": 2930.0, "data_quality": "ok", "quality_reason": "", "freshness_seconds": 0, "source_futures": "akshare_realtime", "source_index": "sina_index", "quote_time": "2026-04-23 15:00:00", "volume": 20000, "open_interest": 50000, "days_to_expiry": 57, "index_change": 3.0, "index_change_pct": 0.1},
            "contracts": [],
            "alerts": [],
            "quality_summary": {"main_quality": "ok", "main_reason": "", "freshness_seconds": 0, "counts": {}},
            "stats_30d": {"mean_30d": -0.5, "percentile_30d": 52.0, "z_score_30d": -0.1},
        },
        "IM": {
            "symbol": "IM",
            "symbol_name": "中证1000",
            "index": {"latest_price": 8480.0, "change": 16.0, "change_pct": 0.2, "quote_time": "2026-04-23 15:00:00", "source_index": "sina_index"},
            "main_contract": {"contract_code": "IM2606", "premium_rate": -3.0, "annualized_rate": -19.2, "premium_points": -260.0, "futures_price": 8220.0, "index_price": 8480.0, "data_quality": "ok", "quality_reason": "", "freshness_seconds": 0, "source_futures": "sina_futures", "source_index": "sina_index", "quote_time": "2026-04-23 15:00:00", "volume": 30000, "open_interest": 80000, "days_to_expiry": 57, "index_change": 16.0, "index_change_pct": 0.2},
            "contracts": [],
            "alerts": [],
            "quality_summary": {"main_quality": "ok", "main_reason": "", "freshness_seconds": 0, "counts": {}},
            "stats_30d": {"mean_30d": -2.5, "percentile_30d": 68.0, "z_score_30d": -0.4},
        },
    },
}


class DashboardApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = web_app.app.test_client()

    @patch.object(web_app.service, "get_dashboard_overview")
    def test_dashboard_overview_endpoint(self, mocked) -> None:
        mocked.return_value = {
            "success": True,
            "generated_at": "2026-04-23 15:00:00",
            "selected_symbol": "IF",
            "thresholds": {"warning": 2.0, "alert": 3.0, "trigger": 2.0, "popup_enabled": True},
            "cards": [{"symbol": "IF"}],
            "selected": {"contracts": [], "alerts": [], "quality_summary": {}},
        }
        response = self.client.get("/api/dashboard/overview?symbol=IF")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["selected_symbol"], "IF")
        self.assertEqual(payload["thresholds"]["trigger"], 2.0)

    @patch.object(web_app.service, "get_symbol_details")
    @patch.object(web_app.service, "get_timeseries")
    def test_timeseries_and_details_endpoints(self, mocked_timeseries, mocked_details) -> None:
        mocked_details.return_value = {"success": True, "symbol": "IF", "metrics": {}, "validation": {}, "sources": {}, "stats_30d": {}}
        mocked_timeseries.return_value = {"success": True, "symbol": "IF", "range": "intraday", "points": []}
        details_response = self.client.get("/api/dashboard/details?symbol=IF")
        intraday_response = self.client.get("/api/dashboard/timeseries?symbol=IF&range=intraday")
        self.assertEqual(details_response.status_code, 200)
        self.assertEqual(intraday_response.status_code, 200)
        self.assertTrue(details_response.get_json()["success"])
        self.assertTrue(intraday_response.get_json()["success"])

    @patch.object(web_app.service, "get_market_snapshot", return_value=SAMPLE_SNAPSHOT)
    def test_legacy_realtime_endpoint(self, _mocked_snapshot) -> None:
        response = self.client.get("/api/premium/realtime")
        payload = response.get_json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["success"])
        self.assertIn("contracts", payload)
        self.assertIn("all_summaries", payload)
        self.assertEqual(payload["summary"]["main_contract"]["contract_code"], "IF2606")

    @patch.object(web_app.service.storage, "get_premium_history")
    @patch.object(web_app.service.storage, "get_premium_statistics")
    def test_legacy_history_and_statistics_endpoints(self, mocked_stats, mocked_history) -> None:
        mocked_history.return_value = pd.DataFrame(
            [{"日期": "2026-04-23", "时间戳": "2026-04-23 15:00:00", "合约代码": "IF2606"}]
        )
        mocked_stats.return_value = {"avg_premium_rate": -1.2}
        history_response = self.client.get("/api/premium/history?contract=IF&limit=5")
        statistics_response = self.client.get("/api/premium/statistics?contract=IF")
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(statistics_response.status_code, 200)
        self.assertTrue(history_response.get_json()["success"])
        self.assertTrue(statistics_response.get_json()["success"])


if __name__ == "__main__":
    unittest.main()
