from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from flask import Flask, jsonify, make_response, render_template, request

from .market_data_service import MarketDataService


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "src" / "static"

app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0
app.jinja_env.auto_reload = True

service = MarketDataService()


def _flatten_contracts(snapshot: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for symbol_data in snapshot["symbols"].values():
        rows.extend(symbol_data["contracts"])
    return rows


def _legacy_realtime_payload(selected_symbol: str = "IF") -> Dict[str, Any]:
    snapshot = service.get_market_snapshot()
    symbols = snapshot["symbols"]
    selected = symbols.get(selected_symbol.upper()) or symbols["IF"]
    all_contracts = _flatten_contracts(snapshot)
    warnings: List[str] = []
    summaries: Dict[str, Any] = {}

    for symbol, symbol_data in symbols.items():
        summaries[symbol] = {
            "symbol": symbol,
            "index_name": symbol_data["symbol_name"],
            "index_data": symbol_data["index"],
            "main_contract": symbol_data["main_contract"],
            "avg_premium_rate": symbol_data["stats_30d"].get("mean_30d"),
            "contracts_count": len(symbol_data["contracts"]),
        }
        warnings.extend(alert["message"] for alert in symbol_data["alerts"])

    return {
        "success": True,
        "timestamp": snapshot["generated_at"],
        "quote_timestamp": snapshot["generated_at"],
        "served_at": snapshot["generated_at"],
        "index": selected["index"],
        "all_indexes": {symbol: data["index"] for symbol, data in symbols.items()},
        "contracts": all_contracts,
        "summary": {
            "main_contract": selected["main_contract"],
            "avg_premium_rate": selected["stats_30d"].get("mean_30d"),
            "contracts_count": len(all_contracts),
        },
        "all_summaries": summaries,
        "warnings": warnings,
        "thresholds": {
            "warning": service.warning_threshold,
            "alert": service.alert_threshold,
            "popup": service.get_alert_config()["config"].get("trigger_threshold"),
        },
    }


@app.route("/")
def index() -> str:
    response = make_response(render_template("index.html"))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.route("/favicon.ico")
def favicon() -> Any:
    return ("", 204)


@app.route("/api/dashboard/overview")
def dashboard_overview() -> Any:
    symbol = request.args.get("symbol", "IF").upper()
    force_refresh = request.args.get("refresh") == "1"
    return jsonify(service.get_dashboard_overview(symbol, force_refresh=force_refresh))


@app.route("/api/dashboard/details")
def dashboard_details() -> Any:
    symbol = request.args.get("symbol", "IF").upper()
    return jsonify(service.get_symbol_details(symbol))


@app.route("/api/dashboard/timeseries")
def dashboard_timeseries() -> Any:
    symbol = request.args.get("symbol", "IF").upper()
    range_name = request.args.get("range", "intraday").lower()
    return jsonify(service.get_timeseries(symbol, range_name))


@app.route("/api/premium/realtime")
def legacy_realtime() -> Any:
    symbol = request.args.get("symbol", "IF").upper()
    return jsonify(_legacy_realtime_payload(symbol))


@app.route("/api/premium/history")
def legacy_history() -> Any:
    contract = request.args.get("contract", "IF").upper()
    limit = int(request.args.get("limit", 100))
    data = service.storage.get_premium_history(contract_code=contract, limit=limit)
    return jsonify(
        {
            "success": True,
            "contract": contract,
            "count": len(data),
            "data": data.to_dict("records"),
        }
    )


@app.route("/api/premium/history/<symbol>")
def legacy_symbol_history(symbol: str) -> Any:
    symbol = symbol.upper()
    daily_series = service.get_timeseries(symbol, "30d")
    details = service.get_symbol_details(symbol)
    return jsonify(
        {
            "success": True,
            "data": daily_series.get("raw", []),
            "stats": details.get("stats_30d", {}),
        }
    )


@app.route("/api/premium/statistics")
def legacy_statistics() -> Any:
    contract = request.args.get("contract", "IF").upper()
    statistics = service.storage.get_premium_statistics(contract_code=contract)
    return jsonify({"success": True, "statistics": statistics})


@app.route("/api/contracts")
def legacy_contracts() -> Any:
    payload = service.get_dashboard_overview(request.args.get("symbol", "IF").upper())
    contracts = [
        {
            "code": item["contract_code"],
            "position": item["position"],
            "expiry_date": item["expiry_date"],
            "days_to_expiry": item["days_to_expiry"],
            "status": item["data_quality"],
        }
        for item in payload["selected"]["contracts"]
    ]
    return jsonify({"success": True, "contracts": contracts})


@app.route("/api/futures/collect")
def legacy_collect() -> Any:
    snapshot = service.refresh()
    return jsonify(
        {
            "success": True,
            "message": "数据已刷新",
            "timestamp": snapshot["generated_at"],
        }
    )


@app.route("/api/export")
def export_data() -> Any:
    contract = request.args.get("contract", "IF").upper()
    filename = BASE_DIR / f"premium_export_{contract}_{service.get_market_snapshot()['generated_at'].replace(':', '').replace(' ', '_')}.xlsx"
    success = service.storage.export_to_excel(str(filename), contract_code=contract)
    return jsonify(
        {
            "success": success,
            "file": str(filename.name) if success else "",
            "message": f"已导出到 {filename.name}" if success else "当前没有可导出的数据",
        }
    )


@app.route("/api/cache/stats")
def cache_stats() -> Any:
    return jsonify({"success": True, "data": service.get_cache_stats()})


@app.route("/api/cache/clear", methods=["POST"])
def cache_clear() -> Any:
    service.clear_cache()
    return jsonify({"success": True, "message": "缓存已清空"})


@app.route("/api/data/refresh", methods=["POST"])
def force_refresh() -> Any:
    snapshot = service.refresh()
    return jsonify({"success": True, "generated_at": snapshot["generated_at"]})


@app.route("/api/health")
def health() -> Any:
    snapshot = service.get_market_snapshot()
    return jsonify(
        {
            "status": "ok",
            "generated_at": snapshot["generated_at"],
            "symbols": list(snapshot["symbols"].keys()),
        }
    )


def run_server(port: int = 5005) -> None:
    counts = service.warm_intraday_minute_cache(strict=True)
    print(f"intraday minute cache ready: {counts}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True, use_reloader=False)


if __name__ == "__main__":
    run_server()
