"""测试东方财富实时指数接口"""
import akshare as ak
import pandas as pd
from datetime import datetime

print('='*60)
print('测试东方财富实时指数接口')
print('='*60)

# 测试东方财富实时行情接口
try:
    print("\n【测试1】stock_zh_a_spot_em() - 东方财富实时行情")
    # 这个接口可以获取实时指数数据
    df = ak.stock_zh_index_spot_em()
    if df is not None and not df.empty:
        print(f"获取到 {len(df)} 条数据")
        print("列名:", df.columns.tolist())
        
        # 筛选沪深300、中证500、上证50、中证1000
        indices = ['沪深300', '中证500', '上证50', '中证1000']
        for idx_name in indices:
            filtered = df[df['名称'].str.contains(idx_name, na=False)]
            if not filtered.empty:
                print(f"\n{idx_name}:")
                for _, row in filtered.head(2).iterrows():
                    print(f"  {row['名称']}: 最新价={row['最新价']}, 涨跌幅={row['涨跌幅']}%")
    else:
        print("未获取到数据")
except Exception as e:
    print(f"测试失败: {e}")

# 测试东方财富指数实时行情
try:
    print("\n\n【测试2】stock_zh_index_spot_em() - 东方财富指数实时行情")
    df = ak.stock_zh_index_spot_em()
    if df is not None and not df.empty:
        print(f"获取到 {len(df)} 条数据")
        
        # 查找特定指数
        target_indices = {
            '000300': '沪深300',
            '000905': '中证500',
            '000016': '上证50',
            '000852': '中证1000'
        }
        
        for code, name in target_indices.items():
            filtered = df[df['代码'] == code]
            if not filtered.empty:
                row = filtered.iloc[0]
                print(f"\n{code} {name}:")
                print(f"  最新价: {row['最新价']}")
                print(f"  涨跌幅: {row['涨跌幅']}%")
                print(f"  昨收: {row['昨收']}")
    else:
        print("未获取到数据")
except Exception as e:
    print(f"测试失败: {e}")

# 测试获取多个指数的实时数据
try:
    print("\n\n【测试3】获取指定指数的实时数据")
    index_codes = ['000300', '000905', '000016', '000852']
    index_names = {
        '000300': '沪深300',
        '000905': '中证500',
        '000016': '上证50',
        '000852': '中证1000'
    }
    
    results = {}
    df = ak.stock_zh_index_spot_em()
    if df is not None and not df.empty:
        for code in index_codes:
            filtered = df[df['代码'] == code]
            if not filtered.empty:
                row = filtered.iloc[0]
                results[code] = {
                    'name': index_names[code],
                    'latest_price': float(row['最新价']),
                    'change': float(row['涨跌额']),
                    'change_pct': float(row['涨跌幅']),
                    'open': float(row['开盘']),
                    'high': float(row['最高']),
                    'low': float(row['最低']),
                    'prev_close': float(row['昨收'])
                }
                print(f"\n{index_names[code]} ({code}):")
                print(f"  最新价: {results[code]['latest_price']}")
                print(f"  涨跌幅: {results[code]['change_pct']}%")
    else:
        print("未获取到数据")
        
except Exception as e:
    print(f"测试失败: {e}")

print("\n" + "="*60)
print('测试完成')
print("="*60)
