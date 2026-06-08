from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = str(PROJECT_ROOT / "data")
LOG_FILE = str(PROJECT_ROOT / "premium_monitor.log")

WARNING_THRESHOLD = 2.0
ALERT_THRESHOLD = 3.0
ALERT_NOTIFICATION_CONFIG = {
    "trigger_threshold": 8.0,
    "cooldown_minutes": 5,
    "popup_enabled": True,
    "email": {
        "enabled": True,
        "smtp_host": "smtp.163.com",
        "smtp_port": 465,
        "username": "szjj_report_bot@163.com",
        "password": "UZRYRLH7Pq9Ggn3e",
        "sender": "szjj_report_bot@163.com",
        "recipients": "1952778042@qq.com",
        "security": "ssl",
        "subject_prefix": "[升贴水提醒]",
    },
    "feishu": {
        "enabled": False,
        "webhook_url": "",
        "secret": "",
    },
    "wecom": {
        "enabled": False,
        "webhook_url": "",
    },
}

PREMIUM_SNAPSHOT_CSV = "realtime_snapshots.csv"
DAILY_MAIN_CSV = "daily_main_premium.csv"
LEGACY_DATA_FILES = [
    "futures_premium_daily.csv",
    "if_futures_daily.csv",
    "index_daily.csv",
]

COLLECTION_TIMES = ["09:30", "11:30", "15:00"]
LOG_LEVEL = "INFO"
SWITCH_WARNING_DAYS = 3
