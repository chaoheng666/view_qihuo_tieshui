from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional, Tuple

import akshare as ak
import pandas as pd
import requests

from .alerting import AlertNotificationManager
from .storage import CSVStorage, DAILY_COLUMNS

try:
    from .config import ALERT_THRESHOLD, WARNING_THRESHOLD
except Exception:
    WARNING_THRESHOLD = 2.0
    ALERT_THRESHOLD = 3.0


LOGGER = logging.getLogger(__name__)

DAILY_HISTORY_START = date(2021, 1, 1)

SYMBOL_CONFIG: Dict[str, Dict[str, str]] = {
    "IF": {
        "name": "沪深300",
        "sina_index_code": "sh000300",
        "index_code": "000300",
        "ak_realtime_symbol": "\u6caa\u6df1300\u6307\u6570\u671f\u8d27",
        "ak_history_symbol": "sh000300",
    },
    "IC": {
        "name": "中证500",
        "sina_index_code": "sh000905",
        "index_code": "000905",
        "ak_realtime_symbol": "\u4e2d\u8bc1500\u6307\u6570\u671f\u8d27",
        "ak_history_symbol": "sh000905",
    },
    "IH": {
        "name": "上证50",
        "sina_index_code": "sh000016",
        "index_code": "000016",
        "ak_realtime_symbol": "\u4e0a\u8bc150\u6307\u6570\u671f\u8d27",
        "ak_history_symbol": "sh000016",
    },
    "IM": {
        "name": "中证1000",
        "sina_index_code": "sh000852",
        "index_code": "000852",
        "ak_realtime_symbol": "\u4e2d\u8bc11000\u6307\u6570\u671f\u8d27",
        "ak_history_symbol": "sh000852",
    },
}

QUALITY_RANK = {
    "ok": 0,
    "fallback": 1,
    "stale": 2,
    "needs_review": 3,
    "missing": 4,
}


def _now() -> datetime:
    return datetime.now()


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in ("", None) or pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if value in ("", None) or pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_pct_gap(left: Optional[float], right: Optional[float]) -> float:
    if not left or not right:
        return 0.0
    return abs(left - right) / abs(right) * 100


def _quality_max(*values: str) -> str:
    best = "ok"
    for value in values:
        if QUALITY_RANK.get(value, 0) > QUALITY_RANK.get(best, 0):
            best = value
    return best


def _format_basis_rate_text(value: float) -> str:
    if value == 0:
        return "平水 0.000%"
    return f"{'贴水' if value < 0 else '升水'} {abs(value):.3f}%"


def _parse_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _format_datetime(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _add_months(anchor: date, months: int) -> date:
    month_index = anchor.month - 1 + months
    year = anchor.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _third_friday(year: int, month: int) -> date:
    first_day = date(year, month, 1)
    offset = (4 - first_day.weekday()) % 7
    return first_day + timedelta(days=offset + 14)


def _front_delivery_month(reference: date) -> date:
    current = date(reference.year, reference.month, 1)
    if reference > _third_friday(reference.year, reference.month):
        current = _add_months(current, 1)
    return current


def build_candidate_contract_codes(symbol: str, reference: Optional[date] = None) -> List[str]:
    today = reference or date.today()
    front = _front_delivery_month(today)
    next_month = _add_months(front, 1)
    quarter_months: List[date] = []
    cursor = next_month
    while len(quarter_months) < 2:
        cursor = _add_months(cursor, 1)
        if cursor.month in {3, 6, 9, 12}:
            quarter_months.append(cursor)

    codes = [f"{symbol}0", f"{symbol}{front:%y%m}", f"{symbol}{next_month:%y%m}"]
    codes.extend(f"{symbol}{month:%y%m}" for month in quarter_months)

    deduped: List[str] = []
    for code in codes:
        if code not in deduped:
            deduped.append(code)
    return deduped


def contract_expiry_date(contract_code: str) -> Optional[date]:
    if not contract_code or contract_code.endswith("0"):
        return None
    match = re.search(r"(\d{2})(\d{2})$", contract_code)
    if not match:
        return None
    year = 2000 + int(match.group(1))
    month = int(match.group(2))
    return _third_friday(year, month)


def contract_position(symbol: str, contract_code: str, reference: Optional[date] = None) -> str:
    if contract_code.endswith("0"):
        return "连续"
    codes = build_candidate_contract_codes(symbol, reference)
    mapping = {
        1: "当月",
        2: "下月",
        3: "下季月",
        4: "隔季月",
    }
    for index, code in enumerate(codes):
        if code == contract_code:
            return mapping.get(index, "远月")
    return "远月"


def days_to_expiry(contract_code: str, reference: Optional[date] = None) -> int:
    expiry = contract_expiry_date(contract_code)
    if not expiry:
        return 0
    target = reference or date.today()
    delta = (expiry - target).days
    return max(delta, 0)


def compute_premium(
    futures_price: float,
    index_price: float,
    days_remaining: int,
) -> Dict[str, float]:
    if futures_price <= 0 or index_price <= 0:
        return {
            "premium_points": 0.0,
            "premium_rate": 0.0,
            "annualized_rate": 0.0,
            "annualized_basis_rate": 0.0,
        }
    premium_points = futures_price - index_price
    premium_rate = premium_points / index_price * 100
    annualized_rate = (
        (index_price - futures_price) / futures_price * 100 * 365 / days_remaining
        if days_remaining > 0
        else 0.0
    )
    annualized_basis_rate = annualized_rate
    return {
        "premium_points": round(premium_points, 4),
        "premium_rate": round(premium_rate, 4),
        "annualized_rate": round(annualized_rate, 4),
        "annualized_basis_rate": round(annualized_basis_rate, 4),
    }


def infer_freshness_seconds(quote_time: str, now: Optional[datetime] = None) -> int:
    current = now or _now()
    parsed = _parse_datetime(quote_time)
    if parsed is None:
        return 0
    return max(int((current - parsed).total_seconds()), 0)


def validate_price_band(symbol: str, futures_price: float, index_price: float) -> bool:
    band = {
        "IF": (2000, 8000),
        "IC": (3000, 12000),
        "IH": (1500, 6000),
        "IM": (3000, 15000),
    }.get(symbol, (500, 20000))
    return band[0] <= futures_price <= band[1] and band[0] <= index_price <= band[1]


def select_main_contract(contracts: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    contract_list = list(contracts)
    if not contract_list:
        return None

    dated = [item for item in contract_list if not item.get("is_continuous")]
    candidates = dated or contract_list
    ordered = sorted(
        candidates,
        key=lambda item: (
            -_to_int(item.get("volume")),
            -_to_int(item.get("open_interest")),
            _to_int(item.get("days_to_expiry"), 9999),
        ),
    )
    return ordered[0] if ordered else None


class MarketDataService:
    def __init__(
        self,
        storage: Optional[CSVStorage] = None,
        cache_ttl_seconds: int = 20,
        snapshot_write_interval_seconds: int = 60,
        freshness_warning_seconds: int = 60,
        freshness_stale_seconds: int = 180,
        divergence_threshold_pct: float = 0.15,
    ) -> None:
        self.storage = storage or CSVStorage()
        self.cache_ttl_seconds = cache_ttl_seconds
        self.snapshot_write_interval_seconds = snapshot_write_interval_seconds
        self.freshness_warning_seconds = freshness_warning_seconds
        self.freshness_stale_seconds = freshness_stale_seconds
        self.divergence_threshold_pct = divergence_threshold_pct
        self.warning_threshold = WARNING_THRESHOLD
        self.alert_threshold = ALERT_THRESHOLD
        self.alert_manager = AlertNotificationManager()

        self._lock = Lock()
        self._cached_snapshot: Optional[Dict[str, Any]] = None
        self._cached_at: Optional[datetime] = None
        self._last_snapshot_write_at: Optional[datetime] = None
        self._daily_backfill_at: Optional[datetime] = None
        self._fallback_state = self.storage.get_latest_symbol_state()

    def clear_cache(self) -> None:
        with self._lock:
            self._cached_snapshot = None
            self._cached_at = None

    def get_cache_stats(self) -> Dict[str, Any]:
        cached_age = None
        if self._cached_at:
            cached_age = int((_now() - self._cached_at).total_seconds())
        return {
            "cache_ttl_seconds": self.cache_ttl_seconds,
            "cache_age_seconds": cached_age,
            "has_snapshot": self._cached_snapshot is not None,
            "last_snapshot_write_at": _format_datetime(self._last_snapshot_write_at),
            "last_daily_backfill_at": _format_datetime(self._daily_backfill_at),
        }

    def refresh(self) -> Dict[str, Any]:
        return self.get_market_snapshot(force_refresh=True)

    def get_market_snapshot(self, force_refresh: bool = False) -> Dict[str, Any]:
        snapshot: Optional[Dict[str, Any]] = None
        snapshot_origin = "cache"
        with self._lock:
            if (
                not force_refresh
                and self._cached_snapshot is not None
                and self._cached_at is not None
                and (_now() - self._cached_at).total_seconds() < self.cache_ttl_seconds
            ):
                snapshot = self._cached_snapshot

        if snapshot is None:
            snapshot_origin = "live"
            snapshot = self._fetch_market_snapshot()
            self._persist_snapshots(snapshot)
            with self._lock:
                self._cached_snapshot = snapshot
                self._cached_at = _now()

        LOGGER.info(
            "market snapshot ready origin=%s generated_at=%s force_refresh=%s",
            snapshot_origin,
            snapshot.get("generated_at"),
            force_refresh,
        )

        try:
            alert_results = self.alert_manager.handle_snapshot(snapshot)
            LOGGER.info(
                "market snapshot alert processing generated_at=%s dispatched=%s",
                snapshot.get("generated_at"),
                len(alert_results),
            )
        except Exception as exc:
            LOGGER.warning("threshold notification handling failed: %s", exc)
        return snapshot

    def get_alert_config(self) -> Dict[str, Any]:
        return {
            "success": True,
            "config": self.alert_manager.get_config(),
        }

    def update_alert_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "success": True,
            "config": self.alert_manager.update_config(updates),
        }

    def send_test_alert_notification(self) -> Dict[str, Any]:
        return self.alert_manager.send_test_notification()

    def get_dashboard_overview(self, selected_symbol: str = "IF", force_refresh: bool = False) -> Dict[str, Any]:
        snapshot = self.get_market_snapshot(force_refresh=force_refresh)
        alert_config = self.alert_manager.get_config()
        symbols = snapshot["symbols"]
        selected_key = selected_symbol.upper() if selected_symbol.upper() in symbols else "IF"
        selected = symbols.get(selected_key) or next(iter(symbols.values()))

        cards = []
        for symbol in ["IF", "IC", "IH", "IM"]:
            data = symbols.get(symbol)
            if not data:
                continue
            cards.append(
                {
                    "symbol": symbol,
                    "symbol_name": data["symbol_name"],
                    "contract_code": data["main_contract"].get("contract_code"),
                    "futures_price": data["main_contract"].get("futures_price"),
                    "index_price": data["main_contract"].get("index_price"),
                    "premium_points": data["main_contract"].get("premium_points"),
                    "premium_rate": data["main_contract"].get("premium_rate"),
                    "annualized_rate": data["main_contract"].get("annualized_rate"),
                    "annualized_basis_rate": data["main_contract"].get("annualized_basis_rate"),
                    "data_quality": data["main_contract"].get("data_quality"),
                    "quality_reason": data["main_contract"].get("quality_reason"),
                    "freshness_seconds": data["main_contract"].get("freshness_seconds"),
                    "percentile_30d": data["stats_30d"].get("percentile_30d"),
                    "basis_percentile_30d": data["stats_30d"].get("basis_percentile_30d"),
                    "z_score_30d": data["stats_30d"].get("z_score_30d"),
                    "ma5": data["stats_30d"].get("ma5"),
                    "ma20": data["stats_30d"].get("ma20"),
                    "quote_time": data["main_contract"].get("quote_time"),
                }
            )

        return {
            "success": True,
            "generated_at": snapshot["generated_at"],
            "selected_symbol": selected_key,
            "thresholds": {
                "warning": self.warning_threshold,
                "alert": self.alert_threshold,
                "trigger": alert_config.get("trigger_threshold"),
                "popup_enabled": bool(alert_config.get("popup_enabled")),
            },
            "cards": cards,
            "selected": {
                "symbol": selected["symbol"],
                "symbol_name": selected["symbol_name"],
                "main_contract": selected["main_contract"],
                "contracts": selected["contracts"],
                "alerts": selected["alerts"],
                "quality_summary": selected["quality_summary"],
                "stats_30d": selected["stats_30d"],
                "index": selected["index"],
            },
        }

    def get_symbol_details(self, symbol: str, force_refresh: bool = False) -> Dict[str, Any]:
        snapshot = self.get_market_snapshot(force_refresh=force_refresh)
        selected = snapshot["symbols"].get(symbol.upper())
        if not selected:
            return {
                "success": False,
                "error": f"unsupported symbol: {symbol}",
            }

        main = selected["main_contract"]
        stats = selected["stats_30d"]
        return {
            "success": True,
            "generated_at": snapshot["generated_at"],
            "symbol": selected["symbol"],
            "symbol_name": selected["symbol_name"],
            "metrics": {
                "contract_code": main.get("contract_code"),
                "futures_price": main.get("futures_price"),
                "index_price": main.get("index_price"),
                "premium_points": main.get("premium_points"),
                "premium_rate": main.get("premium_rate"),
                "annualized_rate": main.get("annualized_rate"),
                "annualized_basis_rate": main.get("annualized_basis_rate"),
                "volume": main.get("volume"),
                "open_interest": main.get("open_interest"),
                "days_to_expiry": main.get("days_to_expiry"),
                "index_change": main.get("index_change"),
                "index_change_pct": main.get("index_change_pct"),
                "percentile_30d": stats.get("percentile_30d"),
                "basis_percentile_30d": stats.get("basis_percentile_30d"),
                "z_score_30d": stats.get("z_score_30d"),
                "mean_30d": stats.get("mean_30d"),
                "std_30d": stats.get("std_30d"),
                "ma5": stats.get("ma5"),
                "ma20": stats.get("ma20"),
                "quote_time": main.get("quote_time"),
            },
            "basis_curve": [
                {
                    "contract_code": item["contract_code"],
                    "position": item["position"],
                    "premium_points": item["premium_points"],
                    "premium_rate": item["premium_rate"],
                    "annualized_rate": item["annualized_rate"],
                    "annualized_basis_rate": item.get("annualized_basis_rate"),
                    "days_to_expiry": item["days_to_expiry"],
                    "volume": item["volume"],
                    "open_interest": item["open_interest"],
                    "data_quality": item["data_quality"],
                }
                for item in selected["contracts"]
            ],
            "sources": {
                "futures": main.get("source_futures"),
                "index": main.get("source_index"),
            },
            "validation": {
                "data_quality": main.get("data_quality"),
                "quality_reason": main.get("quality_reason"),
                "freshness_seconds": main.get("freshness_seconds"),
                "primary_backup_gap_pct": main.get("primary_backup_gap_pct", 0.0),
            },
            "stats_30d": stats,
            "alerts": selected["alerts"],
        }

    def get_timeseries(self, symbol: str, range_name: str = "intraday") -> Dict[str, Any]:
        target = symbol.upper()
        if range_name == "intraday":
            frame = self.storage.load_intraday_snapshots(target)
            contract_code = ""
            if not frame.empty and "contract_code" in frame.columns:
                contract_code = str(frame["contract_code"].dropna().iloc[-1]).upper()
            if not contract_code:
                live = self.get_market_snapshot()["symbols"].get(target)
                if live:
                    contract_code = str(live["main_contract"].get("contract_code") or "").upper()
            backfill_points = self._fetch_intraday_minute_backfill(target, contract_code)
            points = [
                {
                    "timestamp": row["quote_time"],
                    "premium_rate": _to_float(row["premium_rate"]),
                    "premium_points": _to_float(row["premium_points"]),
                    "futures_price": _to_float(row["futures_price"]),
                    "index_price": _to_float(row["index_price"]),
                    "volume": _to_float(row.get("volume")),
                    "contract_code": row["contract_code"],
                    "data_quality": row["data_quality"],
                }
                for _, row in frame.iterrows()
            ]
            if backfill_points:
                by_minute = {str(item.get("timestamp", ""))[:16]: item for item in backfill_points}
                for item in points:
                    by_minute[str(item.get("timestamp", ""))[:16]] = item
                points = [by_minute[key] for key in sorted(by_minute)]
            if not points:
                live = self.get_market_snapshot()["symbols"].get(target)
                if live:
                    main = live["main_contract"]
                    points = [
                        {
                            "timestamp": main.get("quote_time"),
                            "premium_rate": main.get("premium_rate"),
                            "premium_points": main.get("premium_points"),
                            "futures_price": main.get("futures_price"),
                            "index_price": main.get("index_price"),
                            "volume": main.get("volume"),
                            "contract_code": main.get("contract_code"),
                            "data_quality": main.get("data_quality"),
                        }
                    ]
            return {
                "success": True,
                "symbol": target,
                "range": "intraday",
                "generated_at": _format_datetime(_now()),
                "points": points,
            }

        daily = self.storage.load_daily_history(target, limit=0)
        if daily.empty:
            return {
                "success": True,
                "symbol": target,
                "range": "30d",
                "generated_at": _format_datetime(_now()),
                "status": "backfilling",
                "raw": [],
                "smoothed": [],
            }

        raw_points = [
            {
                "timestamp": row["trade_date"],
                "premium_rate": _to_float(row["premium_rate"]),
                "premium_points": _to_float(row["premium_points"]),
                "futures_price": _to_float(row["futures_close"]),
                "index_price": _to_float(row["index_close"]),
                "contract_code": row["contract_code"],
            }
            for _, row in daily.iterrows()
        ]
        smooth = (
            pd.Series(daily["premium_rate"].astype(float))
            .ewm(span=5, adjust=False)
            .mean()
            .round(4)
            .tolist()
        )
        smoothed_points = [
            {
                "timestamp": raw_points[index]["timestamp"],
                "premium_rate": _to_float(value),
            }
            for index, value in enumerate(smooth)
        ]
        return {
            "success": True,
            "symbol": target,
            "range": "30d",
            "generated_at": _format_datetime(_now()),
            "status": "ready",
            "raw": raw_points,
            "smoothed": smoothed_points,
        }

    def _fetch_intraday_minute_backfill(self, symbol: str, contract_code: str) -> List[Dict[str, Any]]:
        if not contract_code or symbol not in SYMBOL_CONFIG:
            return []
        try:
            futures = ak.futures_zh_minute_sina(symbol=contract_code, period="1")
            index = ak.stock_zh_a_minute(symbol=SYMBOL_CONFIG[symbol]["sina_index_code"], period="1", adjust="")
        except Exception as exc:
            LOGGER.debug("intraday minute backfill failed for %s %s: %s", symbol, contract_code, exc)
            return []
        if futures is None or index is None or futures.empty or index.empty:
            return []
        if "datetime" not in futures.columns or "day" not in index.columns:
            return []

        today = _now().date()
        futures = futures.copy()
        index = index.copy()
        futures["minute"] = pd.to_datetime(futures["datetime"], errors="coerce")
        index["minute"] = pd.to_datetime(index["day"], errors="coerce")
        futures = futures.dropna(subset=["minute"])
        index = index.dropna(subset=["minute"])
        futures = futures[futures["minute"].dt.date == today]
        index = index[index["minute"].dt.date == today]
        if futures.empty or index.empty:
            return []

        futures = futures[["minute", "close", "volume", "hold"]].rename(
            columns={"close": "futures_price", "hold": "open_interest"}
        )
        index = index[["minute", "close"]].rename(columns={"close": "index_price"})
        merged = pd.merge(futures, index, on="minute", how="inner").sort_values("minute")
        rows: List[Dict[str, Any]] = []
        for _, row in merged.iterrows():
            futures_price = _to_float(row.get("futures_price"))
            index_price = _to_float(row.get("index_price"))
            if futures_price <= 0 or index_price <= 0:
                continue
            premium = compute_premium(futures_price, index_price, 0)
            rows.append(
                {
                    "timestamp": row["minute"].strftime("%Y-%m-%d %H:%M:%S"),
                    "premium_rate": premium["premium_rate"],
                    "premium_points": premium["premium_points"],
                    "futures_price": futures_price,
                    "index_price": index_price,
                    "volume": _to_float(row.get("volume")),
                    "open_interest": _to_float(row.get("open_interest")),
                    "contract_code": contract_code,
                    "data_quality": "ok",
                    "source_futures": "sina_minute",
                    "source_index": "sina_minute",
                }
            )
        return rows

    def ensure_daily_history_backfill(self, force: bool = False) -> None:
        now = _now()
        if not force and self._daily_backfill_at and (now - self._daily_backfill_at) < timedelta(hours=6):
            return

        end = date.today()
        start = self._get_daily_backfill_start(end)
        if start > end:
            self._daily_backfill_at = now
            return

        try:
            rows = self._build_daily_backfill_rows(start, end)
            if rows:
                self.storage.upsert_daily_main_history(rows)
        except Exception as exc:
            LOGGER.exception("daily backfill failed: %s", exc)
        finally:
            self._daily_backfill_at = now

    def _get_daily_backfill_start(self, end: date) -> date:
        latest_dates: List[date] = []
        for symbol in SYMBOL_CONFIG:
            existing = self.storage.load_daily_history(symbol, limit=0)
            if existing.empty:
                return DAILY_HISTORY_START
            latest = pd.to_datetime(existing["trade_date"], errors="coerce").max()
            if pd.isna(latest):
                return DAILY_HISTORY_START
            latest_dates.append(latest.date())

        if not latest_dates:
            return DAILY_HISTORY_START
        return min(min(latest_dates) + timedelta(days=1), end + timedelta(days=1))

    def _build_daily_backfill_rows(self, start: date, end: date) -> List[Dict[str, Any]]:
        index_history = self._fetch_index_daily_history(start, end)
        existing_daily = self.storage._read_csv(self.storage.daily_main_file, DAILY_COLUMNS)
        existing_keys = set()
        if not existing_daily.empty and "trade_date" in existing_daily.columns and "symbol" in existing_daily.columns:
            existing_keys = {
                (str(row.trade_date), str(row.symbol).upper())
                for row in existing_daily.itertuples(index=False)
            }

        rows: List[Dict[str, Any]] = []
        cursor = start
        while cursor <= end:
            day_key = cursor.strftime("%Y-%m-%d")
            if all((day_key, symbol) in existing_keys for symbol in SYMBOL_CONFIG):
                cursor += timedelta(days=1)
                continue
            try:
                futures_daily = self._fetch_cffex_daily(cursor)
            except Exception:
                futures_daily = pd.DataFrame()

            if futures_daily.empty:
                cursor += timedelta(days=1)
                continue

            futures_daily["symbol_root"] = futures_daily["symbol"].astype(str).str.extract(r"^([A-Z]+)")[0]
            futures_daily = futures_daily[futures_daily["symbol_root"].isin(SYMBOL_CONFIG)]
            if futures_daily.empty:
                cursor += timedelta(days=1)
                continue

            for symbol in ["IF", "IC", "IH", "IM"]:
                if (day_key, symbol) in existing_keys:
                    continue
                symbol_frame = futures_daily[futures_daily["symbol_root"] == symbol].copy()
                if symbol_frame.empty:
                    continue
                symbol_frame = symbol_frame[~symbol_frame["symbol"].astype(str).str.endswith("0")]
                if symbol_frame.empty:
                    continue
                symbol_frame = symbol_frame.sort_values(
                    ["volume", "open_interest"], ascending=[False, False]
                )
                contract = symbol_frame.iloc[0]
                index_row = index_history.get(symbol, {}).get(day_key)
                if not index_row:
                    continue
                futures_close = _to_float(contract.get("close"))
                index_close = _to_float(index_row.get("close"))
                expiry = contract_expiry_date(str(contract.get("symbol", "")))
                remaining = max((expiry - cursor).days, 0) if expiry else 0
                premium = compute_premium(futures_close, index_close, remaining)
                rows.append(
                    {
                        "trade_date": day_key,
                        "symbol": symbol,
                        "symbol_name": SYMBOL_CONFIG[symbol]["name"],
                        "contract_code": str(contract.get("symbol", "")).upper(),
                        "contract_name": str(contract.get("symbol", "")).upper(),
                        "expiry_date": expiry.strftime("%Y-%m-%d") if expiry else "",
                        "days_to_expiry": remaining,
                        "futures_close": futures_close,
                        "index_close": index_close,
                        "premium_points": premium["premium_points"],
                        "premium_rate": premium["premium_rate"],
                        "annualized_rate": premium["annualized_rate"],
                        "volume": _to_int(contract.get("volume")),
                        "open_interest": _to_int(contract.get("open_interest")),
                    }
                )

            cursor += timedelta(days=1)
        return rows

    def _fetch_cffex_daily(self, target: date) -> pd.DataFrame:
        date_string = target.strftime("%Y%m%d")
        try:
            frame = ak.get_futures_daily(
                start_date=date_string,
                end_date=date_string,
                market="CFFEX",
            )
            if frame is not None and not frame.empty:
                return frame
        except Exception:
            LOGGER.debug("get_futures_daily failed for %s", date_string, exc_info=True)
        try:
            frame = ak.futures_hist_daily_cffex(date=date_string)
            if frame is not None and not frame.empty:
                return frame
        except Exception:
            LOGGER.debug("futures_hist_daily_cffex failed for %s", date_string, exc_info=True)
        return pd.DataFrame()

    def _fetch_index_daily_history(self, start: date, end: date) -> Dict[str, Dict[str, Dict[str, Any]]]:
        history: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for symbol, config in SYMBOL_CONFIG.items():
            frame = pd.DataFrame()
            try:
                frame = ak.stock_zh_index_daily_em(
                    symbol=config["ak_history_symbol"],
                    start_date=start.strftime("%Y%m%d"),
                    end_date=end.strftime("%Y%m%d"),
                )
            except Exception:
                LOGGER.debug("stock_zh_index_daily_em failed for %s", symbol, exc_info=True)

            if frame is None or frame.empty:
                try:
                    frame = ak.stock_zh_index_daily(symbol=config["ak_history_symbol"])
                except Exception:
                    LOGGER.debug("stock_zh_index_daily failed for %s", symbol, exc_info=True)
                    frame = pd.DataFrame()

            if frame is None or frame.empty:
                history[symbol] = {}
                continue

            normalized = frame.copy()
            date_column = "date" if "date" in normalized.columns else normalized.columns[0]
            close_column = "close" if "close" in normalized.columns else "收盘"
            open_column = "open" if "open" in normalized.columns else "开盘"
            high_column = "high" if "high" in normalized.columns else "最高"
            low_column = "low" if "low" in normalized.columns else "最低"

            normalized[date_column] = pd.to_datetime(normalized[date_column], errors="coerce")
            normalized = normalized.dropna(subset=[date_column])
            normalized = normalized[
                (normalized[date_column].dt.date >= start)
                & (normalized[date_column].dt.date <= end)
            ]

            history[symbol] = {
                row[date_column].strftime("%Y-%m-%d"): {
                    "close": _to_float(row[close_column]),
                    "open": _to_float(row[open_column]),
                    "high": _to_float(row[high_column]),
                    "low": _to_float(row[low_column]),
                }
                for _, row in normalized.iterrows()
            }
        return history

    def _fetch_market_snapshot(self) -> Dict[str, Any]:
        fetched_at = _now()
        index_primary: Dict[str, Dict[str, Any]] = {}
        index_backup: Dict[str, Dict[str, Any]] = {}
        futures_primary: Dict[str, Dict[str, Dict[str, Any]]] = {}
        futures_backup: Dict[str, Dict[str, Dict[str, Any]]] = {}

        # Sina is primary for both indexes and futures (stable, no crash).
        # AkShare live calls (eastmoney) crash Python process on Windows;
        # they are only used for historical data backfill.
        sina_tasks = {
            "index_primary": self._fetch_sina_indexes,
            "IF_primary": lambda: self._fetch_sina_futures("IF"),
            "IC_primary": lambda: self._fetch_sina_futures("IC"),
            "IH_primary": lambda: self._fetch_sina_futures("IH"),
            "IM_primary": lambda: self._fetch_sina_futures("IM"),
        }

        for name, func in sina_tasks.items():
            try:
                result = func()
            except Exception as exc:
                LOGGER.warning("sina task %s failed: %s", name, exc)
                result = {}

            if name == "index_primary":
                index_primary = result
            elif name.endswith("_primary"):
                futures_primary[name.split("_")[0]] = result

        symbols: Dict[str, Dict[str, Any]] = {}
        for symbol in ["IF", "IC", "IH", "IM"]:
            symbol_snapshot = self._build_symbol_snapshot(
                symbol=symbol,
                fetched_at=fetched_at,
                primary_index=index_primary.get(symbol),
                backup_index=index_backup.get(symbol),
                primary_futures=futures_primary.get(symbol, {}),
                backup_futures=futures_backup.get(symbol, {}),
            )
            symbols[symbol] = symbol_snapshot

        return {
            "generated_at": fetched_at.strftime("%Y-%m-%d %H:%M:%S"),
            "symbols": symbols,
        }

    def _build_symbol_snapshot(
        self,
        symbol: str,
        fetched_at: datetime,
        primary_index: Optional[Dict[str, Any]],
        backup_index: Optional[Dict[str, Any]],
        primary_futures: Dict[str, Dict[str, Any]],
        backup_futures: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        fallback_state = self._fallback_state.get(symbol)
        index_data, index_gap = self._select_index(symbol, primary_index, backup_index, fallback_state)
        contracts = self._merge_contracts(
            symbol=symbol,
            fetched_at=fetched_at,
            index_data=index_data,
            primary_futures=primary_futures,
            backup_futures=backup_futures,
            fallback_state=fallback_state,
        )
        main_contract = select_main_contract(contracts) or {
            "symbol": symbol,
            "symbol_name": SYMBOL_CONFIG[symbol]["name"],
            "contract_code": "",
            "contract_name": "",
            "position": "",
            "expiry_date": "",
            "days_to_expiry": 0,
            "futures_price": 0.0,
            "index_price": _to_float(index_data.get("latest_price")),
            "premium_points": 0.0,
            "premium_rate": 0.0,
            "annualized_rate": 0.0,
            "annualized_basis_rate": 0.0,
            "volume": 0,
            "open_interest": 0,
            "quote_time": index_data.get("quote_time", fetched_at.strftime("%Y-%m-%d %H:%M:%S")),
            "source_futures": "missing",
            "source_index": index_data.get("source_index", "missing"),
            "data_quality": "missing",
            "quality_reason": "missing contracts",
            "freshness_seconds": infer_freshness_seconds(index_data.get("quote_time", ""), fetched_at),
            "is_continuous": False,
            "is_main": True,
            "index_change": _to_float(index_data.get("change")),
            "index_change_pct": _to_float(index_data.get("change_pct")),
        }

        for contract in contracts:
            contract["is_main"] = contract["contract_code"] == main_contract.get("contract_code")

        if main_contract.get("contract_code"):
            self._fallback_state[symbol] = self._build_fallback_state(symbol, contracts, main_contract)

        if index_gap > self.divergence_threshold_pct:
            main_contract["data_quality"] = _quality_max(main_contract["data_quality"], "needs_review")
            reason = main_contract.get("quality_reason", "")
            extra = f"index primary/backup gap {index_gap:.3f}%"
            main_contract["quality_reason"] = ", ".join(filter(None, [reason, extra]))

        stats_30d = self._build_symbol_stats(symbol, main_contract)
        alerts = self._build_alerts(symbol, main_contract, stats_30d)
        quality_summary = self._build_quality_summary(contracts, main_contract)
        return {
            "symbol": symbol,
            "symbol_name": SYMBOL_CONFIG[symbol]["name"],
            "index": index_data,
            "contracts": contracts,
            "main_contract": main_contract,
            "stats_30d": stats_30d,
            "alerts": alerts,
            "quality_summary": quality_summary,
        }

    def _build_fallback_state(
        self,
        symbol: str,
        contracts: List[Dict[str, Any]],
        main_contract: Dict[str, Any],
    ) -> Any:
        from .storage import SymbolSnapshotState

        return SymbolSnapshotState(
            quote_time=main_contract.get("quote_time", ""),
            contracts=[dict(item) for item in contracts],
            main_contract=dict(main_contract),
        )

    def _select_index(
        self,
        symbol: str,
        primary: Optional[Dict[str, Any]],
        backup: Optional[Dict[str, Any]],
        fallback_state: Optional[Any],
    ) -> Tuple[Dict[str, Any], float]:
        selected = dict(primary or {})
        gap = 0.0

        if primary and backup:
            gap = _safe_pct_gap(_to_float(primary.get("latest_price")), _to_float(backup.get("latest_price")))
        elif not primary and backup:
            selected = dict(backup)
        elif not primary and not backup and fallback_state and fallback_state.main_contract:
            selected = {
                "symbol": symbol,
                "name": SYMBOL_CONFIG[symbol]["name"],
                "latest_price": _to_float(fallback_state.main_contract.get("index_price")),
                "change": _to_float(fallback_state.main_contract.get("index_change")),
                "change_pct": _to_float(fallback_state.main_contract.get("index_change_pct")),
                "open": 0.0,
                "high": 0.0,
                "low": 0.0,
                "quote_time": fallback_state.quote_time,
                "source_index": "last_valid_snapshot",
            }

        if not selected:
            selected = {
                "symbol": symbol,
                "name": SYMBOL_CONFIG[symbol]["name"],
                "latest_price": 0.0,
                "change": 0.0,
                "change_pct": 0.0,
                "open": 0.0,
                "high": 0.0,
                "low": 0.0,
                "quote_time": _format_datetime(_now()),
                "source_index": "missing",
            }
        selected.setdefault("source_index", "sina_index")
        return selected, gap

    def _merge_contracts(
        self,
        symbol: str,
        fetched_at: datetime,
        index_data: Dict[str, Any],
        primary_futures: Dict[str, Dict[str, Any]],
        backup_futures: Dict[str, Dict[str, Any]],
        fallback_state: Optional[Any],
    ) -> List[Dict[str, Any]]:
        all_codes = set(primary_futures) | set(backup_futures)
        if not all_codes and fallback_state:
            all_codes = {row.get("contract_code", "") for row in fallback_state.contracts}

        contracts: List[Dict[str, Any]] = []
        for code in sorted(filter(None, all_codes)):
            primary = primary_futures.get(code)
            backup = backup_futures.get(code)
            selected = dict(primary or backup or {})
            if not selected and fallback_state:
                selected = next(
                    (dict(row) for row in fallback_state.contracts if row.get("contract_code") == code),
                    {},
                )
                if selected:
                    selected["source_futures"] = "last_valid_snapshot"

            futures_price = _to_float(selected.get("latest_price") or selected.get("futures_price"))
            index_price = _to_float(index_data.get("latest_price"))
            if futures_price <= 0 or index_price <= 0:
                continue

            quote_time = selected.get("quote_time") or _format_datetime(fetched_at)
            expiry = contract_expiry_date(code)
            remaining = days_to_expiry(code, fetched_at.date())
            premium = compute_premium(futures_price, index_price, remaining)
            gap = 0.0
            if primary and backup:
                gap = _safe_pct_gap(
                    _to_float(primary.get("latest_price")),
                    _to_float(backup.get("latest_price")),
                )

            quality = "ok"
            reasons: List[str] = []
            source_futures = selected.get("source_futures")
            if not source_futures:
                source_futures = "sina_futures"

            freshness = infer_freshness_seconds(quote_time, fetched_at)
            if source_futures == "last_valid_snapshot":
                quality = _quality_max(quality, "stale")
                reasons.append("fallback to last valid snapshot")
            elif not primary and backup:
                quality = _quality_max(quality, "fallback")
                reasons.append("primary futures source unavailable")

            if freshness > self.freshness_stale_seconds:
                quality = _quality_max(quality, "stale")
                reasons.append(f"freshness {freshness}s exceeds stale threshold")
            elif freshness > self.freshness_warning_seconds:
                quality = _quality_max(quality, "fallback")
                reasons.append(f"freshness {freshness}s exceeds warning threshold")

            if gap > self.divergence_threshold_pct:
                quality = _quality_max(quality, "needs_review")
                reasons.append(f"primary/backup gap {gap:.3f}%")

            if not validate_price_band(symbol, futures_price, index_price):
                quality = _quality_max(quality, "needs_review")
                reasons.append("price outside expected range")

            if abs(premium["premium_rate"]) > 20:
                quality = _quality_max(quality, "needs_review")
                reasons.append("premium rate outlier")

            contract = {
                "symbol": symbol,
                "symbol_name": SYMBOL_CONFIG[symbol]["name"],
                "contract_code": code,
                "contract_name": selected.get("name", code),
                "position": contract_position(symbol, code, fetched_at.date()),
                "expiry_date": expiry.strftime("%Y-%m-%d") if expiry else "",
                "days_to_expiry": remaining,
                "quote_time": quote_time,
                "futures_price": round(futures_price, 4),
                "index_price": round(index_price, 4),
                "premium_points": premium["premium_points"],
                "premium_rate": premium["premium_rate"],
                "annualized_rate": premium["annualized_rate"],
                "annualized_basis_rate": premium["annualized_basis_rate"],
                "volume": _to_int(selected.get("volume")),
                "open_interest": _to_int(selected.get("open_interest")),
                "index_change": round(_to_float(index_data.get("change")), 4),
                "index_change_pct": round(_to_float(index_data.get("change_pct")), 4),
                "change": round(_to_float(selected.get("change")), 4),
                "change_pct": round(_to_float(selected.get("change_pct")), 4),
                "source_futures": source_futures,
                "source_index": index_data.get("source_index", "missing"),
                "data_quality": quality,
                "quality_reason": "; ".join(reasons),
                "freshness_seconds": freshness,
                "primary_backup_gap_pct": round(gap, 4),
                "is_continuous": code.endswith("0"),
                "is_main": False,
            }
            contracts.append(contract)

        display_contracts = [item for item in contracts if not item.get("is_continuous")] or contracts
        display_contracts.sort(
            key=lambda item: (
                _to_int(item.get("days_to_expiry"), 9999),
                -_to_int(item.get("volume")),
                -_to_int(item.get("open_interest")),
            )
        )
        return display_contracts

    def _build_symbol_stats(self, symbol: str, main_contract: Dict[str, Any]) -> Dict[str, Any]:
        daily = self.storage.load_daily_history(symbol, limit=30)
        if daily.empty:
            return {
                "count": 0,
                "mean_30d": None,
                "std_30d": None,
                "min_30d": None,
                "max_30d": None,
                "percentile_30d": None,
                "basis_percentile_30d": None,
                "z_score_30d": None,
                "ma5": None,
                "ma20": None,
            }

        rates = pd.to_numeric(daily["premium_rate"], errors="coerce").dropna()
        if rates.empty:
            return {
                "count": 0,
                "mean_30d": None,
                "std_30d": None,
                "min_30d": None,
                "max_30d": None,
                "percentile_30d": None,
                "basis_percentile_30d": None,
                "z_score_30d": None,
                "ma5": None,
                "ma20": None,
            }

        current_rate = _to_float(main_contract.get("premium_rate"))
        std = float(rates.std(ddof=0)) if len(rates) > 1 else 0.0
        mean = float(rates.mean())
        percentile = float((rates < current_rate).mean() * 100)
        basis_percentile = float((rates.abs() < abs(current_rate)).mean() * 100)
        z_score = float((current_rate - mean) / std) if std else 0.0
        ma5 = float(rates.tail(5).mean()) if len(rates) >= 5 else float(rates.mean())
        ma20 = float(rates.tail(20).mean()) if len(rates) >= 20 else float(rates.mean())
        return {
            "count": int(len(rates)),
            "mean_30d": round(mean, 4),
            "std_30d": round(std, 4),
            "min_30d": round(float(rates.min()), 4),
            "max_30d": round(float(rates.max()), 4),
            "percentile_30d": round(percentile, 2),
            "basis_percentile_30d": round(basis_percentile, 2),
            "z_score_30d": round(z_score, 4),
            "ma5": round(ma5, 4),
            "ma20": round(ma20, 4),
        }

    def _build_alerts(
        self,
        symbol: str,
        main_contract: Dict[str, Any],
        stats: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        premium_rate = _to_float(main_contract.get("premium_rate"))
        quality = main_contract.get("data_quality", "ok")
        timestamp = main_contract.get("quote_time", _format_datetime(_now()))
        contract_code = main_contract.get("contract_code") or "--"

        if QUALITY_RANK.get(quality, 0) >= QUALITY_RANK["stale"]:
            alerts.append(
                {
                    "level": "warning",
                    "message": f"{symbol} {contract_code} 数据状态为 {quality}",
                    "timestamp": timestamp,
                }
            )
        if abs(premium_rate) >= self.alert_threshold:
            alerts.append(
                {
                    "level": "alert",
                    "message": f"{symbol} {contract_code} {_format_basis_rate_text(premium_rate)}",
                    "timestamp": timestamp,
                }
            )
        elif abs(premium_rate) >= self.warning_threshold:
            alerts.append(
                {
                    "level": "warning",
                    "message": f"{symbol} {contract_code} {_format_basis_rate_text(premium_rate)}",
                    "timestamp": timestamp,
                }
            )
        z_score = stats.get("z_score_30d")
        if z_score is not None and abs(z_score) >= 2:
            alerts.append(
                {
                    "level": "warning",
                    "message": f"{symbol} 30日 z-score {z_score:+.2f}",
                    "timestamp": timestamp,
                }
            )
        return alerts

    def _build_quality_summary(
        self,
        contracts: List[Dict[str, Any]],
        main_contract: Dict[str, Any],
    ) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        for contract in contracts:
            quality = contract.get("data_quality", "ok")
            counts[quality] = counts.get(quality, 0) + 1
        return {
            "main_quality": main_contract.get("data_quality", "ok"),
            "main_reason": main_contract.get("quality_reason", ""),
            "freshness_seconds": main_contract.get("freshness_seconds", 0),
            "counts": counts,
        }

    def _persist_snapshots(self, snapshot: Dict[str, Any]) -> None:
        now = _now()
        if (
            self._last_snapshot_write_at
            and (now - self._last_snapshot_write_at).total_seconds() < self.snapshot_write_interval_seconds
        ):
            return

        rows: List[Dict[str, Any]] = []
        for symbol_data in snapshot["symbols"].values():
            main_code = symbol_data["main_contract"].get("contract_code")
            for contract in symbol_data["contracts"]:
                row = {
                    "trade_date": contract["quote_time"][:10],
                    "quote_time": contract["quote_time"],
                    "quote_minute": contract["quote_time"][:16],
                    "symbol": contract["symbol"],
                    "symbol_name": contract["symbol_name"],
                    "contract_code": contract["contract_code"],
                    "contract_name": contract["contract_name"],
                    "position": contract["position"],
                    "expiry_date": contract["expiry_date"],
                    "days_to_expiry": contract["days_to_expiry"],
                    "futures_price": contract["futures_price"],
                    "index_price": contract["index_price"],
                    "premium_points": contract["premium_points"],
                    "premium_rate": contract["premium_rate"],
                    "annualized_rate": contract["annualized_rate"],
                    "volume": contract["volume"],
                    "open_interest": contract["open_interest"],
                    "index_change": contract["index_change"],
                    "index_change_pct": contract["index_change_pct"],
                    "source_futures": contract["source_futures"],
                    "source_index": contract["source_index"],
                    "data_quality": contract["data_quality"],
                    "quality_reason": contract["quality_reason"],
                    "freshness_seconds": contract["freshness_seconds"],
                    "is_continuous": contract["is_continuous"],
                    "is_main": contract["contract_code"] == main_code,
                }
                rows.append(row)

        if rows:
            self.storage.append_realtime_snapshots(rows)
            self._last_snapshot_write_at = now

    def _fetch_sina_indexes(self) -> Dict[str, Dict[str, Any]]:
        code_map = {config["sina_index_code"]: symbol for symbol, config in SYMBOL_CONFIG.items()}
        url = "http://hq.sinajs.cn/list=" + ",".join(code_map)
        headers = {
            "Referer": "http://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = "gbk"

        results: Dict[str, Dict[str, Any]] = {}
        for line in response.text.strip().splitlines():
            match = re.match(r'var hq_str_([^=]+)="(.*)"', line)
            if not match:
                continue
            code = match.group(1)
            payload = match.group(2)
            values = payload.split(",")
            symbol = code_map.get(code)
            if not symbol or len(values) < 10:
                continue
            latest = _to_float(values[3])
            if latest <= 0:
                continue
            quote_date = values[30] if len(values) > 30 else _now().strftime("%Y-%m-%d")
            quote_clock = values[31] if len(values) > 31 else _now().strftime("%H:%M:%S")
            prev_close = _to_float(values[2])
            change = latest - prev_close
            results[symbol] = {
                "symbol": symbol,
                "name": SYMBOL_CONFIG[symbol]["name"],
                "latest_price": latest,
                "prev_close": prev_close,
                "open": _to_float(values[1]),
                "high": _to_float(values[4]),
                "low": _to_float(values[5]),
                "change": change,
                "change_pct": (change / prev_close * 100) if prev_close else 0.0,
                "volume": _to_float(values[8]),
                "amount": _to_float(values[9]),
                "quote_time": f"{quote_date} {quote_clock}",
                "source_index": "sina_index",
            }
        return results

    def _fetch_em_indexes(self) -> Dict[str, Dict[str, Any]]:
        try:
            frame = ak.stock_zh_index_spot_em()
        except Exception:
            LOGGER.debug("stock_zh_index_spot_em failed", exc_info=True)
            return {}
        if frame is None or frame.empty or "代码" not in frame.columns:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        for symbol, config in SYMBOL_CONFIG.items():
            row = frame[frame["代码"].astype(str) == config["index_code"]]
            if row.empty:
                continue
            item = row.iloc[0]
            latest = _to_float(item.get("最新价"))
            if latest <= 0:
                continue
            prev_close = _to_float(item.get("昨收"))
            change_pct = _to_float(item.get("涨跌幅"))
            results[symbol] = {
                "symbol": symbol,
                "name": config["name"],
                "latest_price": latest,
                "prev_close": prev_close,
                "open": _to_float(item.get("开盘")),
                "high": _to_float(item.get("最高")),
                "low": _to_float(item.get("最低")),
                "change": _to_float(item.get("涨跌额")),
                "change_pct": change_pct,
                "volume": _to_float(item.get("成交量")),
                "amount": _to_float(item.get("成交额")),
                "quote_time": _format_datetime(_now()),
                "source_index": "eastmoney_index",
            }
        return results

    def _fetch_ak_futures(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        config = SYMBOL_CONFIG[symbol]
        try:
            frame = ak.futures_zh_realtime(symbol=config["ak_realtime_symbol"])
        except Exception:
            LOGGER.debug("futures_zh_realtime failed for %s", symbol, exc_info=True)
            return {}

        if frame is None or frame.empty:
            return {}

        results: Dict[str, Dict[str, Any]] = {}
        for _, row in frame.iterrows():
            contract_code = str(row.get("symbol", "")).upper().strip()
            if not contract_code.startswith(symbol):
                continue
            latest = _to_float(row.get("trade"))
            if latest <= 0:
                continue
            results[contract_code] = {
                "symbol": symbol,
                "contract_code": contract_code,
                "name": str(row.get("name", contract_code)),
                "latest_price": latest,
                "change": _to_float(row.get("change")),
                "change_pct": _to_float(row.get("changepercent")),
                "volume": _to_int(row.get("volume")),
                "open_interest": _to_int(row.get("position")),
                "quote_time": _format_datetime(_now()),
                "source_futures": "akshare_realtime",
            }
        return results

    def _fetch_sina_futures(self, symbol: str) -> Dict[str, Dict[str, Any]]:
        codes = build_candidate_contract_codes(symbol)
        url = "http://hq.sinajs.cn/list=" + ",".join(f"nf_{code}" for code in codes)
        headers = {
            "Referer": "http://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
        except Exception:
            LOGGER.debug("sina futures failed for %s", symbol, exc_info=True)
            return {}

        response.encoding = "gbk"
        results: Dict[str, Dict[str, Any]] = {}
        for line in response.text.strip().splitlines():
            match = re.match(r'var hq_str_nf_([^=]+)="(.*)"', line)
            if not match:
                continue
            contract_code = match.group(1).upper()
            values = match.group(2).split(",")
            if len(values) < 7:
                continue
            latest = _to_float(values[3])
            if latest <= 0:
                continue
            results[contract_code] = {
                "symbol": symbol,
                "contract_code": contract_code,
                "name": values[-1] if values and values[-1] else contract_code,
                "latest_price": latest,
                "change": latest - _to_float(values[1]),
                "change_pct": (
                    (latest - _to_float(values[1])) / _to_float(values[1]) * 100
                    if _to_float(values[1]) > 0
                    else 0.0
                ),
                "volume": _to_int(values[4]),
                "open_interest": _to_int(values[6]),
                "quote_time": _format_datetime(_now()),
                "source_futures": "sina_futures",
            }
        return results
