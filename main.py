from __future__ import annotations

import argparse

from src.market_data_service import MarketDataService
from src.web_app import run_server


def print_snapshot(symbol: str = "IF") -> None:
    service = MarketDataService()
    snapshot = service.refresh()
    selected = snapshot["symbols"].get(symbol.upper(), snapshot["symbols"]["IF"])
    print("=" * 72)
    print(f"股指期货升贴水监控 | {selected['symbol']} {selected['symbol_name']}")
    print("=" * 72)
    main = selected["main_contract"]
    print(f"更新时间: {snapshot['generated_at']}")
    print(f"主力合约: {main.get('contract_code', '--')}")
    print(f"期货价格: {main.get('futures_price', 0):.2f}")
    print(f"指数价格: {main.get('index_price', 0):.2f}")
    print(f"升贴水点数: {main.get('premium_points', 0):+.2f}")
    print(f"升贴水率: {main.get('premium_rate', 0):+.4f}%")
    print(f"年化升贴水率: {main.get('annualized_rate', 0):+.2f}%")
    print(f"数据质量: {main.get('data_quality', '--')}")
    print()
    print("近月合约基差曲线:")
    for item in selected["contracts"]:
        print(
            f"  {item['contract_code']:8s} "
            f"{item['position']:4s} "
            f"{item['premium_rate']:+8.4f}% "
            f"vol={item['volume']:>7d} "
            f"oi={item['open_interest']:>7d}"
        )


def print_history(symbol: str = "IF", days: int = 30) -> None:
    service = MarketDataService()
    series = service.get_timeseries(symbol.upper(), "30d")
    print("=" * 72)
    print(f"{symbol.upper()} 最近 {days} 个交易日日终主力升贴水")
    print("=" * 72)
    for item in series.get("raw", [])[-days:]:
        print(f"{item['timestamp']}  {item['contract_code']:8s}  {item['premium_rate']:+8.4f}%")


def backfill_daily_history() -> None:
    service = MarketDataService()
    service.ensure_daily_history_backfill(force=True)
    print("daily history backfill finished")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="股指期货升贴水监控")
    parser.add_argument("--web", action="store_true", help="启动 Web 服务")
    parser.add_argument("--port", type=int, default=5005, help="Web 服务端口")
    parser.add_argument("--collect", action="store_true", help="拉取并打印当前快照")
    parser.add_argument("--history", action="store_true", help="打印 30 日主力日终历史")
    parser.add_argument("--symbol", default="IF", help="目标品种: IF/IC/IH/IM")
    parser.add_argument("--days", type=int, default=30, help="历史交易日数量")
    parser.add_argument("--backfill-daily", action="store_true", help="manual daily history backfill")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.web:
        run_server(args.port)
        return
    if args.collect:
        print_snapshot(args.symbol)
        return
    if args.history:
        print_history(args.symbol, args.days)
        return
    if args.backfill_daily:
        backfill_daily_history()
        return

    parser.print_help()


if __name__ == "__main__":
    main()
