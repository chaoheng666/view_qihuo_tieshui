from __future__ import annotations

import tempfile
import unittest
from datetime import date, datetime
from unittest.mock import patch

import pandas as pd

from src.market_data_service import (
    MarketDataService,
    build_candidate_contract_codes,
    compute_premium,
    select_main_contract,
)
from src.storage import CSVStorage


class DashboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.storage = CSVStorage(self.tempdir.name)
        with patch.object(MarketDataService, "ensure_daily_history_backfill", return_value=None):
            self.service = MarketDataService(storage=self.storage)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_candidate_contract_codes_roll_after_expiry(self) -> None:
        codes = build_candidate_contract_codes("IF", date(2026, 4, 23))
        self.assertEqual(codes, ["IF0", "IF2605", "IF2606", "IF2609", "IF2612"])

    def test_select_main_contract_ignores_continuous_contract(self) -> None:
        main = select_main_contract(
            [
                {"contract_code": "IF0", "volume": 90000, "open_interest": 100000, "is_continuous": True},
                {"contract_code": "IF2606", "volume": 60000, "open_interest": 120000, "is_continuous": False},
                {"contract_code": "IF2609", "volume": 20000, "open_interest": 70000, "is_continuous": False},
            ]
        )
        self.assertIsNotNone(main)
        self.assertEqual(main["contract_code"], "IF2606")

    def test_compute_premium_keeps_signed_basis_and_adds_convergence_annualized(self) -> None:
        result = compute_premium(4865.2, 4940.9454, 23)

        self.assertAlmostEqual(result["premium_points"], -75.7454, places=4)
        self.assertAlmostEqual(result["premium_rate"], -1.533, places=3)
        self.assertAlmostEqual(
            result["annualized_rate"],
            (4940.9454 - 4865.2) / 4865.2 * 100 * 365 / 23,
            places=4,
        )
        self.assertAlmostEqual(
            result["annualized_basis_rate"],
            (4940.9454 - 4865.2) / 4865.2 * 100 * 365 / 23,
            places=4,
        )

    def test_merge_contracts_marks_needs_review_on_primary_backup_gap(self) -> None:
        contracts = self.service._merge_contracts(
            symbol="IF",
            fetched_at=datetime(2026, 4, 23, 14, 30, 0),
            index_data={
                "latest_price": 4800.0,
                "change": 10.0,
                "change_pct": 0.2,
                "source_index": "sina_index",
            },
            primary_futures={
                "IF2606": {
                    "latest_price": 4700.0,
                    "volume": 60000,
                    "open_interest": 120000,
                    "quote_time": "2026-04-23 14:30:00",
                    "source_futures": "akshare_realtime",
                }
            },
            backup_futures={
                "IF2606": {
                    "latest_price": 4600.0,
                    "volume": 58000,
                    "open_interest": 110000,
                    "quote_time": "2026-04-23 14:30:00",
                    "source_futures": "sina_futures",
                }
            },
            fallback_state=None,
        )
        self.assertEqual(len(contracts), 1)
        self.assertEqual(contracts[0]["data_quality"], "needs_review")

    def test_alert_message_uses_basis_direction_text(self) -> None:
        alerts = self.service._build_alerts(
            "IF",
            {
                "contract_code": "IF2606",
                "premium_rate": -3.1,
                "data_quality": "ok",
                "quote_time": "2026-04-23 15:00:00",
            },
            {},
        )

        self.assertIn("贴水 3.100%", alerts[0]["message"])
        self.assertNotIn("-3.100%", alerts[0]["message"])

    def test_build_daily_backfill_rows_uses_highest_volume_contract(self) -> None:
        futures_daily = pd.DataFrame(
            [
                {
                    "symbol": "IF2605",
                    "date": "20260422",
                    "close": 4760.0,
                    "volume": 20000,
                    "open_interest": 50000,
                },
                {
                    "symbol": "IF2606",
                    "date": "20260422",
                    "close": 4744.8,
                    "volume": 51772,
                    "open_interest": 141181,
                },
            ]
        )
        with patch.object(
            self.service,
            "_fetch_index_daily_history",
            return_value={"IF": {"2026-04-22": {"close": 4799.627}}},
        ), patch.object(self.service, "_fetch_cffex_daily", return_value=futures_daily):
            rows = self.service._build_daily_backfill_rows(date(2026, 4, 22), date(2026, 4, 22))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["contract_code"], "IF2606")
        self.assertAlmostEqual(rows[0]["premium_rate"], (4744.8 - 4799.627) / 4799.627 * 100, places=4)

    def test_latest_symbol_state_handles_string_false_is_main(self) -> None:
        rows = []
        for code, is_main in [("IF2606", "False"), ("IF2609", "True")]:
            row = {column: "" for column in self.storage._read_csv(self.storage.realtime_snapshot_file).columns}
            row.update(
                {
                    "trade_date": "2026-04-23",
                    "quote_time": "2026-04-23 15:00:00",
                    "quote_minute": "2026-04-23 15:00",
                    "symbol": "IF",
                    "contract_code": code,
                    "is_main": is_main,
                }
            )
            rows.append(row)
        pd.DataFrame(rows).to_csv(self.storage.realtime_snapshot_file, index=False, encoding="utf-8-sig")

        state = self.storage.get_latest_symbol_state()

        self.assertEqual(state["IF"].main_contract["contract_code"], "IF2609")


if __name__ == "__main__":
    unittest.main()
