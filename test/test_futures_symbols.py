"""测试各品种期货数据获取"""
import akshare as ak
import logging
logging.basicConfig(level=logging.WARNING)

# 测试各个期货品种
symbols = [
    '沪深300指数期货',
    '中证500指数期货', 
    '上证50指数期货',
    '中证1000指数期货'
]

print("=" * 60)
print("测试AkShare期货数据获取")
print("=" * 60)

for symbol in symbols:
    try:
        print(f"\n【{symbol}】")
        df = ak.futures_zh_realtime(symbol=symbol)
        if df is not None and not df.empty:
            print(f"获取到 {len(df)} 条数据:")
            print(df[['symbol', 'name', 'trade', 'volume']].head(3))
        else:
            print("无数据")
    except Exception as e:
        print(f"错误: {e}")

print("\n" + "=" * 60)
print("测试完成")
