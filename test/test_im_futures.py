"""测试中证1000期货的正确名称"""
import akshare as ak
import logging
logging.basicConfig(level=logging.WARNING)

# 尝试不同的名称
test_names = [
    '中证1000指数期货',
    '中证1000期货',
    'IM指数期货',
    'IM期货',
    '中证1000',
]

print("测试中证1000期货的不同名称...")

for name in test_names:
    try:
        df = ak.futures_zh_realtime(symbol=name)
        if df is not None and not df.empty:
            print(f"✓ '{name}' 有效！获取到 {len(df)} 条数据")
            print(df[['symbol', 'name', 'trade', 'volume']].head(3))
        else:
            print(f"✗ '{name}' 无数据")
    except Exception as e:
        print(f"✗ '{name}' 错误: {str(e)[:50]}")

# 尝试获取所有期货数据，看看有哪些品种
print("\n\n获取所有股指期货品种...")
try:
    # 尝试获取所有期货
    df = ak.futures_zh_realtime(symbol="沪深300指数期货")
    if df is not None and not df.empty:
        print("现有数据中的品种代码:")
        for idx, row in df.iterrows():
            print(f"  {row['symbol']}: {row['name']}")
except Exception as e:
    print(f"错误: {e}")
