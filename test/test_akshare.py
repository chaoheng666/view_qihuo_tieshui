"""
测试AkShare数据接口
"""
import akshare as ak
import pandas as pd
from datetime import datetime

print("=" * 60)
print("测试AkShare数据接口")
print("=" * 60)

# 测试1：获取IF期货实时行情
print("\n【测试1】获取IF期货实时行情")
try:
    df = ak.futures_zh_realtime(symbol="IF")
    print(f"返回类型: {type(df)}")
    print(f"数据形状: {df.shape if hasattr(df, 'shape') else 'N/A'}")
    print(f"列名: {df.columns.tolist() if hasattr(df, 'columns') else 'N/A'}")
    print("\n前5行数据:")
    print(df.head())
except Exception as e:
    print(f"错误: {e}")

# 测试2：获取沪深300指数实时行情
print("\n【测试2】获取沪深300指数实时行情")
try:
    df = ak.stock_zh_index_real_sina(symbol="sh000300")
    print(f"返回类型: {type(df)}")
    print(f"数据形状: {df.shape if hasattr(df, 'shape') else 'N/A'}")
    print(f"列名: {df.columns.tolist() if hasattr(df, 'columns') else 'N/A'}")
    print("\n数据:")
    print(df)
except Exception as e:
    print(f"错误: {e}")

# 测试3：尝试其他指数接口
print("\n【测试3】尝试eastmoney指数接口")
try:
    df = ak.stock_zh_index_spot_em()
    print(f"返回类型: {type(df)}")
    print(f"列名: {df.columns.tolist()}")
    # 筛选沪深300
    hs300 = df[df['代码'] == '000300']
    if not hs300.empty:
        print("\n沪深300数据:")
        print(hs300)
except Exception as e:
    print(f"错误: {e}")

print("\n" + "=" * 60)
