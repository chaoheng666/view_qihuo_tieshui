from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Iterable, List, Optional

import pandas as pd


REALTIME_COLUMNS = [
    "trade_date",
    "quote_time",
    "quote_minute",
    "symbol",
    "symbol_name",
    "contract_code",
    "contract_name",
    "position",
    "expiry_date",
    "days_to_expiry",
    "futures_price",
    "index_price",
    "premium_points",
    "premium_rate",
    "annualized_rate",
    "volume",
    "open_interest",
    "index_change",
    "index_change_pct",
    "source_futures",
    "source_index",
    "data_quality",
    "quality_reason",
    "freshness_seconds",
    "is_continuous",
    "is_main",
]

DAILY_COLUMNS = [
    "trade_date",
    "symbol",
    "symbol_name",
    "contract_code",
    "contract_name",
    "expiry_date",
    "days_to_expiry",
    "futures_close",
    "index_close",
    "premium_points",
    "premium_rate",
    "annualized_rate",
    "volume",
    "open_interest",
]

MINUTE_HISTORY_START_DATE = "2023-01-01"

LEGACY_HISTORY_COLUMN_MAP = {
    "trade_date": "日期",
    "quote_time": "时间戳",
    "contract_code": "合约代码",
    "contract_name": "合约名称",
    "position": "合约位置",
    "expiry_date": "到期日",
    "days_to_expiry": "距到期天数",
    "futures_price": "期货价格",
    "index_price": "指数价格",
    "premium_points": "升贴水点数",
    "premium_rate": "升贴水率",
    "data_quality": "数据质量",
    "volume": "成交量",
    "open_interest": "持仓量",
    "quality_reason": "质量说明",
}


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _empty_frame(columns: List[str]) -> pd.DataFrame:
    return pd.DataFrame(columns=columns)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int = 0) -> int:
    try:
        if pd.isna(value):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in ("", None) or pd.isna(value):
        return False
    return str(value).strip().lower() in {"true", "1", "1.0", "yes", "y"}


def _normalize_date(value: Any) -> str:
    if value in ("", None) or pd.isna(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d")


def _normalize_datetime(value: Any) -> str:
    if value in ("", None) or pd.isna(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def _normalize_minute(value: Any) -> str:
    if value in ("", None) or pd.isna(value):
        return ""
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M")


def _ensure_columns(frame: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
    if frame.empty:
        return _empty_frame(columns)
    for column in columns:
        if column not in frame.columns:
            frame[column] = ""
    return frame[columns].copy()


@dataclass
class SymbolSnapshotState:
    quote_time: str
    contracts: List[Dict[str, Any]]
    main_contract: Optional[Dict[str, Any]]


class CSVStorage:
    """Unified storage for realtime snapshots and daily main-contract history."""

    def __init__(self, data_dir: Optional[str] = None) -> None:
        root_dir = _project_root()
        self.data_dir = Path(data_dir) if data_dir else root_dir / "data"
        self.src_data_dir = root_dir / "src" / "data"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.realtime_snapshot_file = self.data_dir / "realtime_snapshots.csv"
        self.daily_main_file = self.data_dir / "daily_main_premium.csv"
        self.legacy_premium_file = self.data_dir / "futures_premium_daily.csv"
        self.legacy_futures_file = self.data_dir / "if_futures_daily.csv"
        self.legacy_index_file = self.data_dir / "index_daily.csv"
        self.legacy_archive_dir = self.data_dir / "_legacy_archive"
        self.migration_marker = self.data_dir / ".dashboard_storage_v2_migrated"
        self._lock = Lock()

        self._init_files()
        self.migrate_legacy_data()
        self.archive_legacy_artifacts()

    def _init_files(self) -> None:
        if not self.realtime_snapshot_file.exists():
            _empty_frame(REALTIME_COLUMNS).to_csv(
                self.realtime_snapshot_file, index=False, encoding="utf-8-sig"
            )
        if not self.daily_main_file.exists():
            _empty_frame(DAILY_COLUMNS).to_csv(
                self.daily_main_file, index=False, encoding="utf-8-sig"
            )

    def _read_csv(self, path: Path, columns: Optional[List[str]] = None) -> pd.DataFrame:
        if not path.exists() or path.stat().st_size == 0:
            return _empty_frame(columns or [])
        frame = pd.read_csv(path, encoding="utf-8-sig")
        if columns is None:
            return frame
        return _ensure_columns(frame, columns)

    def migrate_legacy_data(self) -> None:
        if self.migration_marker.exists():
            return

        legacy_sources = [self.legacy_premium_file, self.src_data_dir / "futures_premium_daily.csv"]
        frames: List[pd.DataFrame] = []

        for source in legacy_sources:
            if not source.exists() or source == self.realtime_snapshot_file:
                continue
            legacy_frame = self._convert_legacy_snapshot_frame(source)
            if not legacy_frame.empty:
                frames.append(legacy_frame)

        if frames:
            current = self._read_csv(self.realtime_snapshot_file, REALTIME_COLUMNS)
            combined = pd.concat(frames, ignore_index=True) if current.empty else pd.concat([current, *frames], ignore_index=True)
            combined = self._dedupe_realtime_frame(combined)
            combined.to_csv(self.realtime_snapshot_file, index=False, encoding="utf-8-sig")

        self.migration_marker.write_text(datetime.now().isoformat(), encoding="utf-8")

    def _archive_file(self, source: Path, bucket: str) -> None:
        if not source.exists():
            return
        bucket_dir = self.legacy_archive_dir / bucket
        bucket_dir.mkdir(parents=True, exist_ok=True)
        target = bucket_dir / source.name
        if target.exists():
            same_size = target.stat().st_size == source.stat().st_size
            if same_size:
                source.unlink()
                return
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
            target = bucket_dir / f"{source.stem}_{timestamp}{source.suffix}"
        source.replace(target)

    def archive_legacy_artifacts(self) -> None:
        candidates = [
            (self.legacy_premium_file, "data_root"),
            (self.legacy_futures_file, "data_root"),
            (self.legacy_index_file, "data_root"),
            (self.src_data_dir / "futures_premium_daily.csv", "src_data"),
            (self.src_data_dir / "if_futures_daily.csv", "src_data"),
            (self.src_data_dir / "index_daily.csv", "src_data"),
        ]
        for source, bucket in candidates:
            self._archive_file(source, bucket)

        if self.src_data_dir.exists():
            try:
                if not any(self.src_data_dir.iterdir()):
                    self.src_data_dir.rmdir()
            except OSError:
                pass

    def _convert_legacy_snapshot_frame(self, path: Path) -> pd.DataFrame:
        try:
            legacy = pd.read_csv(path, encoding="utf-8-sig")
        except FileNotFoundError:
            return _empty_frame(REALTIME_COLUMNS)
        except Exception:
            return _empty_frame(REALTIME_COLUMNS)

        if legacy.empty or "时间戳" not in legacy.columns or "合约代码" not in legacy.columns:
            return _empty_frame(REALTIME_COLUMNS)

        contract_codes = legacy["合约代码"].astype(str).str.upper().str.strip()
        symbols = contract_codes.str.extract(r"^([A-Z]+)")[0].fillna("")
        quote_times = legacy["时间戳"].apply(_normalize_datetime)
        frame = pd.DataFrame(
            {
                "trade_date": legacy.get("日期", quote_times.str[:10]).apply(_normalize_date),
                "quote_time": quote_times,
                "quote_minute": quote_times.apply(_normalize_minute),
                "symbol": symbols,
                "symbol_name": symbols,
                "contract_code": contract_codes,
                "contract_name": legacy.get("合约名称", "").fillna(""),
                "position": legacy.get("合约位置", "").fillna(""),
                "expiry_date": legacy.get("到期日", "").fillna("").apply(_normalize_date),
                "days_to_expiry": legacy.get("距到期天数", 0).apply(_to_int),
                "futures_price": legacy.get("期货价格", 0).apply(_to_float),
                "index_price": legacy.get("指数价格", 0).apply(_to_float),
                "premium_points": legacy.get("升贴水点数", 0).apply(_to_float),
                "premium_rate": legacy.get("升贴水率", 0).apply(_to_float),
                "annualized_rate": 0.0,
                "volume": legacy.get("成交量", 0).apply(_to_int),
                "open_interest": legacy.get("持仓量", 0).apply(_to_int),
                "index_change": 0.0,
                "index_change_pct": 0.0,
                "source_futures": "legacy_csv",
                "source_index": "legacy_csv",
                "data_quality": "migrated",
                "quality_reason": f"migrated:{path.name}",
                "freshness_seconds": 0,
                "is_continuous": contract_codes.str.endswith("0"),
                "is_main": False,
            }
        )

        days = frame["days_to_expiry"].replace(0, pd.NA)
        futures_price = pd.to_numeric(frame["futures_price"], errors="coerce").replace(0, pd.NA)
        index_price = pd.to_numeric(frame["index_price"], errors="coerce")
        frame["annualized_rate"] = (
            (index_price - futures_price) / futures_price * 100 * 365 / days
        ).fillna(0.0)

        if frame.empty:
            return _empty_frame(REALTIME_COLUMNS)

        frame = frame.sort_values(
            ["quote_time", "symbol", "is_continuous", "volume", "open_interest"],
            ascending=[True, True, True, False, False],
        )
        for (_, symbol), group in frame.groupby(["quote_time", "symbol"], dropna=False):
            candidates = group[~group["is_continuous"]]
            if candidates.empty:
                candidates = group
            frame.loc[candidates.index[:1], "is_main"] = True

        return _ensure_columns(frame, REALTIME_COLUMNS)

    def _dedupe_realtime_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = _ensure_columns(frame, REALTIME_COLUMNS)
        frame["quote_time"] = frame["quote_time"].apply(_normalize_datetime)
        frame["quote_minute"] = frame["quote_time"].apply(_normalize_minute)
        frame["trade_date"] = frame["trade_date"].apply(_normalize_date)
        frame = frame.drop_duplicates(
            subset=["quote_time", "symbol", "contract_code"], keep="last"
        )
        frame = frame.sort_values(["quote_time", "symbol", "contract_code"])
        return frame.reset_index(drop=True)

    def _dedupe_daily_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = _ensure_columns(frame, DAILY_COLUMNS)
        frame["trade_date"] = frame["trade_date"].apply(_normalize_date)
        frame = frame.drop_duplicates(subset=["trade_date", "symbol"], keep="last")
        frame = frame.sort_values(["trade_date", "symbol"])
        return frame.reset_index(drop=True)

    def append_realtime_snapshots(self, rows: Iterable[Dict[str, Any]]) -> None:
        frame = pd.DataFrame(list(rows))
        if frame.empty:
            return
        frame = _ensure_columns(frame, REALTIME_COLUMNS)
        with self._lock:
            # Append-only mode: write new rows directly without reading entire file
            write_header = not self.realtime_snapshot_file.exists() or self.realtime_snapshot_file.stat().st_size == 0
            frame.to_csv(
                self.realtime_snapshot_file,
                mode="a",
                header=write_header,
                index=False,
                encoding="utf-8-sig",
            )

    def _trim_old_realtime(self, frame: pd.DataFrame, days: int = 3) -> pd.DataFrame:
        cutoff = MINUTE_HISTORY_START_DATE
        if "trade_date" in frame.columns:
            before = len(frame)
            frame = frame[frame["trade_date"].astype(str) >= cutoff]
            removed = before - len(frame)
            if removed:
                import logging
                logging.getLogger(__name__).debug("trimmed %d old realtime rows (start %s)", removed, cutoff)
        return frame

    def upsert_daily_main_history(self, rows: Iterable[Dict[str, Any]]) -> None:
        frame = pd.DataFrame(list(rows))
        if frame.empty:
            return
        frame = _ensure_columns(frame, DAILY_COLUMNS)
        with self._lock:
            current = self._read_csv(self.daily_main_file, DAILY_COLUMNS)
            combined = frame if current.empty else pd.concat([current, frame], ignore_index=True)
            combined = self._dedupe_daily_frame(combined)
            combined.to_csv(self.daily_main_file, index=False, encoding="utf-8-sig")

    def load_intraday_snapshots(self, symbol: str, trade_date: Optional[str] = None) -> pd.DataFrame:
        frame = self._read_csv(self.realtime_snapshot_file, REALTIME_COLUMNS)
        if frame.empty:
            return frame
        filtered = frame[
            (frame["symbol"].astype(str).str.upper() == symbol.upper())
            & (frame["is_main"].astype(str).isin(["True", "true", "1", "1.0", "True"]))
        ].copy()
        if trade_date:
            filtered = filtered[filtered["trade_date"].astype(str) == trade_date]
        else:
            latest_trade_date = filtered["trade_date"].astype(str).max()
            filtered = filtered[filtered["trade_date"].astype(str) == latest_trade_date]
        # Periodic cleanup: if CSV > 10MB, keep minute history from 2023.
        file_size_mb = self.realtime_snapshot_file.stat().st_size / (1024 * 1024)
        if file_size_mb > 10:
            self._auto_cleanup_realtime()
        if filtered.empty:
            return filtered
        filtered["quote_time"] = pd.to_datetime(filtered["quote_time"], errors="coerce")
        filtered = filtered.sort_values("quote_time")
        filtered = filtered.drop_duplicates(subset=["quote_minute"], keep="last")
        filtered["quote_time"] = filtered["quote_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        return filtered.reset_index(drop=True)

    def _auto_cleanup_realtime(self) -> None:
        import logging
        _log = logging.getLogger(__name__)
        try:
            frame = pd.read_csv(self.realtime_snapshot_file, encoding="utf-8-sig", low_memory=False)
            before = len(frame)
            if "trade_date" in frame.columns:
                frame = frame[frame["trade_date"].astype(str) >= MINUTE_HISTORY_START_DATE]
            frame.to_csv(self.realtime_snapshot_file, index=False, encoding="utf-8-sig")
            _log.info("auto-cleanup realtime CSV: %d → %d rows", before, len(frame))
        except Exception as exc:
            _log.warning("auto-cleanup failed: %s", exc)

    def load_daily_history(self, symbol: str, limit: int = 30) -> pd.DataFrame:
        frame = self._read_csv(self.daily_main_file, DAILY_COLUMNS)
        if frame.empty:
            return frame
        filtered = frame[frame["symbol"].astype(str).str.upper() == symbol.upper()].copy()
        if filtered.empty:
            return filtered
        filtered["trade_date"] = pd.to_datetime(filtered["trade_date"], errors="coerce")
        filtered = filtered.sort_values("trade_date")
        if limit:
            filtered = filtered.tail(limit)
        filtered["trade_date"] = filtered["trade_date"].dt.strftime("%Y-%m-%d")
        return filtered.reset_index(drop=True)

    def get_latest_symbol_state(self) -> Dict[str, SymbolSnapshotState]:
        frame = self._read_csv(self.realtime_snapshot_file, REALTIME_COLUMNS)
        if frame.empty:
            return {}

        frame["quote_time"] = pd.to_datetime(frame["quote_time"], errors="coerce")
        frame = frame.dropna(subset=["quote_time"])
        frame = frame.sort_values("quote_time")

        state: Dict[str, SymbolSnapshotState] = {}
        for symbol in frame["symbol"].dropna().astype(str).str.upper().unique():
            symbol_frame = frame[frame["symbol"].astype(str).str.upper() == symbol]
            if symbol_frame.empty:
                continue
            latest_time = symbol_frame["quote_time"].max()
            latest_rows = symbol_frame[symbol_frame["quote_time"] == latest_time].copy()
            latest_rows["quote_time"] = latest_rows["quote_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
            rows = latest_rows.to_dict("records")
            main = next((row for row in rows if _to_bool(row.get("is_main"))), None)
            state[symbol] = SymbolSnapshotState(
                quote_time=latest_time.strftime("%Y-%m-%d %H:%M:%S"),
                contracts=rows,
                main_contract=main,
            )
        return state

    def save_premium_data(self, premium_data_list: Iterable[Dict[str, Any]]) -> None:
        now = datetime.now()
        rows: List[Dict[str, Any]] = []
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for item in premium_data_list:
            symbol = str(item.get("symbol") or item.get("contract_code", "")[:2]).upper()
            grouped.setdefault(symbol, []).append(item)

        main_by_symbol: Dict[str, str] = {}
        for symbol, items in grouped.items():
            sorted_items = sorted(
                items,
                key=lambda value: (
                    str(value.get("contract_code", "")).endswith("0"),
                    -_to_int(value.get("volume")),
                    -_to_int(value.get("open_interest")),
                ),
            )
            if sorted_items:
                main_by_symbol[symbol] = str(sorted_items[0].get("contract_code", ""))

        for item in premium_data_list:
            contract_code = str(item.get("contract_code", "")).upper()
            symbol = str(item.get("symbol") or contract_code[:2]).upper()
            rows.append(
                {
                    "trade_date": now.strftime("%Y-%m-%d"),
                    "quote_time": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "quote_minute": now.strftime("%Y-%m-%d %H:%M"),
                    "symbol": symbol,
                    "symbol_name": symbol,
                    "contract_code": contract_code,
                    "contract_name": item.get("contract_name", contract_code),
                    "position": item.get("position", ""),
                    "expiry_date": _normalize_date(item.get("expiry_date", "")),
                    "days_to_expiry": _to_int(item.get("days_to_expiry", 0)),
                    "futures_price": _to_float(item.get("futures_price", 0)),
                    "index_price": _to_float(item.get("index_price", 0)),
                    "premium_points": _to_float(item.get("premium_points", 0)),
                    "premium_rate": _to_float(item.get("premium_rate", 0)),
                    "annualized_rate": _to_float(
                        item.get("annualized_rate", item.get("annual_rate", 0))
                    ),
                    "volume": _to_int(item.get("volume", 0)),
                    "open_interest": _to_int(item.get("open_interest", 0)),
                    "index_change": _to_float(item.get("index_change", 0)),
                    "index_change_pct": _to_float(item.get("index_change_pct", 0)),
                    "source_futures": item.get("source_futures", "legacy_api"),
                    "source_index": item.get("source_index", "legacy_api"),
                    "data_quality": item.get("data_quality", "ok"),
                    "quality_reason": item.get("quality_reason", ""),
                    "freshness_seconds": _to_int(item.get("freshness_seconds", 0)),
                    "is_continuous": contract_code.endswith("0"),
                    "is_main": main_by_symbol.get(symbol) == contract_code,
                }
            )
        self.append_realtime_snapshots(rows)

    def _legacy_history_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return pd.DataFrame(columns=list(LEGACY_HISTORY_COLUMN_MAP.values()))
        renamed = frame.rename(columns=LEGACY_HISTORY_COLUMN_MAP)
        return renamed[list(LEGACY_HISTORY_COLUMN_MAP.values())].copy()

    def get_premium_history(
        self,
        contract_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        frame = self._read_csv(self.realtime_snapshot_file, REALTIME_COLUMNS)
        if frame.empty:
            return self._legacy_history_frame(frame)

        filtered = frame.copy()
        if contract_code:
            code = contract_code.upper()
            if len(code) <= 3:
                filtered = filtered[filtered["symbol"].astype(str).str.upper() == code]
            else:
                filtered = filtered[
                    filtered["contract_code"].astype(str).str.upper() == code
                ]
        if start_date:
            filtered = filtered[filtered["trade_date"].astype(str) >= start_date]
        if end_date:
            filtered = filtered[filtered["trade_date"].astype(str) <= end_date]

        filtered["quote_time"] = pd.to_datetime(filtered["quote_time"], errors="coerce")
        filtered = filtered.sort_values("quote_time", ascending=False)
        if limit:
            filtered = filtered.head(limit)
        filtered["quote_time"] = filtered["quote_time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        return self._legacy_history_frame(filtered.reset_index(drop=True))

    def get_premium_statistics(self, contract_code: str = "IF", days: int = 30) -> Dict[str, Any]:
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        history = self.get_premium_history(contract_code, start_date, end_date, limit=100000)
        if history.empty:
            return {}

        rate_col = "升贴水率"
        points_col = "升贴水点数"
        stats = {
            "contract_code": contract_code,
            "period": f"{start_date} 至 {end_date}",
            "record_count": int(len(history)),
            "avg_premium_points": _to_float(history[points_col].mean()),
            "max_premium_points": _to_float(history[points_col].max()),
            "min_premium_points": _to_float(history[points_col].min()),
            "current_premium_points": _to_float(history[points_col].iloc[0]),
            "avg_premium_rate": _to_float(history[rate_col].mean()),
            "max_premium_rate": _to_float(history[rate_col].max()),
            "min_premium_rate": _to_float(history[rate_col].min()),
        }
        return stats

    def export_to_excel(
        self,
        output_file: str,
        contract_code: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> bool:
        realtime_history = self.get_premium_history(contract_code, start_date, end_date, limit=100000)
        daily_history = self.load_daily_history((contract_code or "IF")[:2], limit=0)
        if realtime_history.empty and daily_history.empty:
            return False

        with pd.ExcelWriter(output_file, engine="openpyxl") as writer:
            realtime_history.to_excel(writer, sheet_name="RealtimeSnapshots", index=False)
            if not daily_history.empty:
                daily_history.to_excel(writer, sheet_name="DailyMainPremium", index=False)
        return True


class DashboardStorage(CSVStorage):
    pass
