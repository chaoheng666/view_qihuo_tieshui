from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from .storage import CSVStorage


class HistoricalAnalyzer:
    def __init__(self, storage_path: str = "data") -> None:
        self.storage = CSVStorage(storage_path)

    def save_premium_snapshot(self, premium_data: Dict[str, Any]) -> bool:
        rows = []
        today = datetime.now().strftime("%Y-%m-%d")
        for symbol, symbol_data in premium_data.items():
            main = symbol_data.get("main_contract")
            if not main:
                continue
            rows.append(
                {
                    "trade_date": today,
                    "symbol": symbol,
                    "symbol_name": symbol_data.get("index_data", {}).get("name", symbol),
                    "contract_code": main.get("contract_code", ""),
                    "contract_name": main.get("contract_name", main.get("contract_code", "")),
                    "expiry_date": main.get("expiry_date", ""),
                    "days_to_expiry": main.get("days_to_expiry", 0),
                    "futures_close": main.get("futures_price", 0),
                    "index_close": main.get("index_price", 0),
                    "premium_points": main.get("premium_points", 0),
                    "premium_rate": main.get("premium_rate", 0),
                    "annualized_rate": main.get("annual_rate", main.get("annualized_rate", 0)),
                    "volume": main.get("volume", 0),
                    "open_interest": main.get("open_interest", 0),
                }
            )
        if not rows:
            return False
        self.storage.upsert_daily_main_history(rows)
        return True

    def get_historical_premium(self, species_code: str, days: int = 30) -> pd.DataFrame:
        return self.storage.load_daily_history(species_code.upper(), limit=days)

    def calculate_statistics(self, species_code: str, days: int = 30) -> Dict[str, Any]:
        frame = self.get_historical_premium(species_code, days)
        if frame.empty:
            return {
                "mean": 0.0,
                "std": 0.0,
                "min": 0.0,
                "max": 0.0,
                "median": 0.0,
                "q25": 0.0,
                "q75": 0.0,
                "count": 0,
            }
        rates = pd.to_numeric(frame["premium_rate"], errors="coerce").dropna()
        if rates.empty:
            return {
                "mean": 0.0,
                "std": 0.0,
                "min": 0.0,
                "max": 0.0,
                "median": 0.0,
                "q25": 0.0,
                "q75": 0.0,
                "count": 0,
            }
        return {
            "mean": float(rates.mean()),
            "std": float(rates.std(ddof=0)) if len(rates) > 1 else 0.0,
            "min": float(rates.min()),
            "max": float(rates.max()),
            "median": float(rates.median()),
            "q25": float(rates.quantile(0.25)),
            "q75": float(rates.quantile(0.75)),
            "count": int(len(rates)),
        }

    def calculate_moving_average(self, species_code: str, window: int = 5) -> List[float]:
        frame = self.get_historical_premium(species_code, max(window * 3, 30))
        if frame.empty:
            return []
        rates = pd.to_numeric(frame["premium_rate"], errors="coerce").dropna()
        if len(rates) < window:
            return []
        return [float(value) for value in rates.rolling(window=window).mean().dropna().tolist()]

    def calculate_percentile(self, species_code: str, days: int = 30) -> float:
        frame = self.get_historical_premium(species_code, days)
        if frame.empty:
            return 50.0
        rates = pd.to_numeric(frame["premium_rate"], errors="coerce").dropna()
        if rates.empty:
            return 50.0
        latest = float(rates.iloc[-1])
        return float((rates < latest).mean() * 100)

    def detect_trend(self, species_code: str, window: int = 5) -> str:
        values = self.calculate_moving_average(species_code, window)
        if len(values) < 3:
            return "数据不足"
        recent = values[-3:]
        if recent[0] < recent[1] < recent[2]:
            return "上升"
        if recent[0] > recent[1] > recent[2]:
            return "下降"
        return "震荡"


class EnhancedAlertManager:
    def __init__(self) -> None:
        self.history: List[Dict[str, Any]] = []

    def check_premium_alert(self, premium_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        alerts: List[Dict[str, Any]] = []
        for symbol, symbol_data in premium_data.items():
            main = symbol_data.get("main_contract", {})
            rate = float(main.get("premium_rate", 0))
            level = "NORMAL"
            if abs(rate) >= 3:
                level = "ALERT"
            elif abs(rate) >= 2:
                level = "WARNING"
            alert = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "species_code": symbol,
                "contract_code": main.get("contract_code", ""),
                "level": level,
                "premium_rate": rate,
                "annual_rate": float(main.get("annual_rate", main.get("annualized_rate", 0))),
                "message": f"{symbol}({main.get('contract_code', '--')}) 升贴水率 {rate:+.3f}%",
            }
            alerts.append(alert)
        self.history.extend(alerts)
        self.history = self.history[-100:]
        return alerts

    def check_sudden_change(
        self,
        current_data: Dict[str, Any],
        previous_data: Optional[Dict[str, Any]],
        threshold: float = 0.5,
    ) -> List[Dict[str, Any]]:
        if not previous_data:
            return []
        alerts: List[Dict[str, Any]] = []
        for symbol, symbol_data in current_data.items():
            current_rate = float(symbol_data.get("main_contract", {}).get("premium_rate", 0))
            previous_rate = float(previous_data.get(symbol, {}).get("main_contract", {}).get("premium_rate", 0))
            change = abs(current_rate - previous_rate)
            if change >= threshold:
                alerts.append(
                    {
                        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "species_code": symbol,
                        "change": change,
                        "previous_rate": previous_rate,
                        "current_rate": current_rate,
                        "level": "WARNING",
                        "message": f"{symbol} 升贴水率变化 {change:.3f}%",
                    }
                )
        return alerts

    def get_alert_history(self, limit: int = 20) -> List[Dict[str, Any]]:
        return self.history[-limit:]

    def get_alert_summary(self) -> Dict[str, Any]:
        summary = {"NORMAL": 0, "WARNING": 0, "ALERT": 0}
        for item in self.history:
            summary[item["level"]] = summary.get(item["level"], 0) + 1
        return {
            "total": len(self.history),
            "by_level": summary,
            "latest": self.history[-1] if self.history else None,
        }


class CrossSpeciesAnalyzer:
    def __init__(self) -> None:
        self.analyzer = HistoricalAnalyzer()

    def calculate_spread(
        self,
        premium_data: Dict[str, Any],
        species1: str,
        species2: str,
    ) -> Optional[float]:
        rate1 = premium_data.get(species1, {}).get("main_contract", {}).get("premium_rate")
        rate2 = premium_data.get(species2, {}).get("main_contract", {}).get("premium_rate")
        if rate1 is None or rate2 is None:
            return None
        return float(rate1) - float(rate2)

    def get_all_spreads(self, premium_data: Dict[str, Any]) -> Dict[str, float]:
        pairs = [("IF", "IC"), ("IF", "IH"), ("IF", "IM"), ("IC", "IH"), ("IC", "IM"), ("IH", "IM")]
        spreads: Dict[str, float] = {}
        for left, right in pairs:
            spread = self.calculate_spread(premium_data, left, right)
            if spread is not None:
                spreads[f"{left}-{right}"] = spread
        return spreads

    def find_arbitrage_opportunity(self, premium_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        opportunities: List[Dict[str, Any]] = []
        spreads = self.get_all_spreads(premium_data)
        for pair, value in spreads.items():
            if abs(value) >= 1.5:
                opportunities.append(
                    {
                        "spread_key": pair,
                        "current_spread": value,
                        "message": f"{pair} 当前价差 {value:+.3f}%",
                    }
                )
        return opportunities


_historical_analyzer = HistoricalAnalyzer()
_alert_manager = EnhancedAlertManager()
_cross_analyzer = CrossSpeciesAnalyzer()


def get_historical_analyzer() -> HistoricalAnalyzer:
    return _historical_analyzer


def get_enhanced_alert_manager() -> EnhancedAlertManager:
    return _alert_manager


def get_cross_species_analyzer() -> CrossSpeciesAnalyzer:
    return _cross_analyzer
