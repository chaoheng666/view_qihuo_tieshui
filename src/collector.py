from __future__ import annotations

from typing import Any, Dict

from .market_data_service import MarketDataService


_service = MarketDataService()


def _legacy_contract_map(symbol_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for contract in symbol_data["contracts"]:
        result[contract["contract_code"]] = {
            "symbol": contract["contract_code"],
            "name": contract["contract_name"],
            "latest_price": contract["futures_price"],
            "change": contract["change"],
            "change_pct": contract["change_pct"],
            "volume": contract["volume"],
            "open_interest": contract["open_interest"],
            "quote_time": contract["quote_time"],
            "source_futures": contract["source_futures"],
            "data_quality": contract["data_quality"],
        }
    return result


def get_all_futures_data() -> Dict[str, Dict[str, Dict[str, Any]]]:
    snapshot = _service.get_market_snapshot()
    return {
        symbol: _legacy_contract_map(symbol_data)
        for symbol, symbol_data in snapshot["symbols"].items()
    }


def get_im_futures_realtime(contract_codes: Any = None) -> Dict[str, Dict[str, Any]]:
    snapshot = _service.get_market_snapshot()
    contracts = _legacy_contract_map(snapshot["symbols"]["IM"])
    if not contract_codes:
        return contracts
    return {code: contracts[code] for code in contract_codes if code in contracts}


class FuturesDataCollector:
    def __init__(self) -> None:
        self.service = _service

    def clear_cache(self) -> None:
        self.service.clear_cache()

    def refresh_data(self) -> Dict[str, Any]:
        return self.get_current_quotation(force_refresh=True)

    def get_index_realtime(self, symbol: str = "IF") -> Dict[str, Any]:
        snapshot = self.service.get_market_snapshot()
        symbol_data = snapshot["symbols"].get(symbol.upper(), snapshot["symbols"]["IF"])
        index = symbol_data["index"]
        return {
            "symbol": symbol.upper(),
            "name": symbol_data["symbol_name"],
            "latest_price": index.get("latest_price", 0.0),
            "prev_close": index.get("prev_close", 0.0),
            "open": index.get("open", 0.0),
            "high": index.get("high", 0.0),
            "low": index.get("low", 0.0),
            "change": index.get("change", 0.0),
            "change_pct": index.get("change_pct", 0.0),
            "volume": index.get("volume", 0.0),
            "amount": index.get("amount", 0.0),
            "date": index.get("quote_time", "")[:10],
            "time": index.get("quote_time", "")[11:19],
            "source_index": index.get("source_index", "missing"),
        }

    def get_current_quotation(self, force_refresh: bool = False) -> Dict[str, Any]:
        snapshot = self.service.get_market_snapshot(force_refresh=force_refresh)
        all_futures = {
            symbol: _legacy_contract_map(symbol_data)
            for symbol, symbol_data in snapshot["symbols"].items()
        }
        all_index = {
            symbol: self.get_index_realtime(symbol)
            for symbol in snapshot["symbols"].keys()
        }
        return {
            "timestamp": snapshot["generated_at"],
            "all_futures": all_futures,
            "all_index": all_index,
            "futures": all_futures.get("IF", {}),
            "index": all_index.get("IF", {}),
        }
