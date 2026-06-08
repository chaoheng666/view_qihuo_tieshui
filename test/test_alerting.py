from __future__ import annotations

import unittest
from unittest.mock import patch

from src.alerting import AlertNotificationManager


def build_snapshot(rate: float, quote_time: str = "2026-04-24 10:00:00") -> dict:
    return {
        "generated_at": quote_time,
        "symbols": {
            "IF": {
                "symbol": "IF",
                "symbol_name": "沪深300",
                "main_contract": {
                    "contract_code": "IF2606",
                    "quote_time": quote_time,
                    "premium_rate": rate,
                    "premium_points": rate * 10,
                    "data_quality": "ok",
                    "quality_reason": "",
                },
            }
        },
    }


class AlertNotificationManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manager = AlertNotificationManager()

    def test_config_override_is_loaded(self) -> None:
        manager = AlertNotificationManager(
            config_override={
                "trigger_threshold": 1.6,
                "cooldown_minutes": 3,
                "popup_enabled": False,
                "email": {
                    "enabled": True,
                    "smtp_host": "smtp.example.com",
                    "sender": "monitor@example.com",
                    "recipients": "a@example.com,b@example.com",
                },
            }
        )
        config = manager.get_config()

        self.assertEqual(config["trigger_threshold"], 1.6)
        self.assertEqual(config["cooldown_minutes"], 3)
        self.assertFalse(config["popup_enabled"])
        self.assertTrue(config["email"]["enabled"])
        self.assertEqual(config["email"]["smtp_host"], "smtp.example.com")

    def test_handle_snapshot_deduplicates_until_recovery(self) -> None:
        self.manager.update_config({"trigger_threshold": 2.0, "cooldown_minutes": 10})

        with patch.object(self.manager, "_dispatch_event", return_value=[{"channel": "email", "status": "sent"}]) as mocked:
            first = self.manager.handle_snapshot(build_snapshot(-2.5, "2026-04-24 10:00:00"))
            second = self.manager.handle_snapshot(build_snapshot(-2.7, "2026-04-24 10:01:00"))
            recovery = self.manager.handle_snapshot(build_snapshot(-1.2, "2026-04-24 10:02:00"))
            third = self.manager.handle_snapshot(build_snapshot(-2.6, "2026-04-24 10:03:00"))

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 0)
        self.assertEqual(len(recovery), 0)
        self.assertEqual(len(third), 1)
        self.assertEqual(mocked.call_count, 2)

    def test_handle_snapshot_retries_after_failed_delivery(self) -> None:
        self.manager.update_config({"trigger_threshold": 2.0, "cooldown_minutes": 10})

        with patch.object(
            self.manager,
            "_dispatch_event",
            side_effect=[
                [{"channel": "email", "status": "error"}],
                [{"channel": "email", "status": "sent"}],
            ],
        ) as mocked:
            first = self.manager.handle_snapshot(build_snapshot(-2.5, "2026-04-24 10:00:00"))
            second = self.manager.handle_snapshot(build_snapshot(-2.6, "2026-04-24 10:01:00"))

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)
        self.assertEqual(mocked.call_count, 2)


if __name__ == "__main__":
    unittest.main()
