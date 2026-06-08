"""测试所有品种期货数据获取"""
import akshare as ak
from datetime import datetime

print('='*60)
print('测试各品种期货数据获取')
print('='*60)

# 测试IF
print('\n【IF沪深300期货】')
try:
    df = ak.futures_zh_realtime(symbol='沪深300指数期货')
    if df is not None and not df.empty:
        print(f'获取到 {len(df)} 个合约')
        for _, row in df.iterrows():
            print(f"  {row.get('symbol', 'N/A')}: {row.get('trade', 0)}")
    else:
        print('未获取到数据')
except Exception as e:
    print(f'获取失败: {e}')

# 测试IC
print('\n【IC中证500期货】')
try:
    df = ak.futures_zh_realtime(symbol='中证500指数期货')
    if df is not None and not df.empty:
        print(f'获取到 {len(df)} 个合约')
        for _, row in df.iterrows():
            print(f"  {row.get('symbol', 'N/A')}: {row.get('trade', 0)}")
    else:
        print('未获取到数据')
except Exception as e:
    print(f'获取失败: {e}')

# 测试IH
print('\n【IH上证50期货】')
try:
    df = ak.futures_zh_realtime(symbol='上证50指数期货')
    if df is not None and not df.empty:
        print(f'获取到 {len(df)} 个合约')
        for _, row in df.iterrows():
            print(f"  {row.get('symbol', 'N/A')}: {row.get('trade', 0)}")
    else:
        print('未获取到数据')
except Exception as e:
    print(f'获取失败: {e}')

# 测试指数数据
print('\n【指数数据】')
try:
    # 沪深300
    df300 = ak.stock_zh_index_daily(symbol="sh000300")
    if df300 is not None and not df300.empty:
        latest = df300.iloc[-1]
        print(f'沪深300: {latest.get("close", 0)}')
    
    # 中证500
    df500 = ak.stock_zh_index_daily(symbol="sh000905")
    if df500 is not None and not df500.empty:
        latest = df500.iloc[-1]
        print(f'中证500: {latest.get("close", 0)}')
    
    # 上证50
    df50 = ak.stock_zh_index_daily(symbol="sh000016")
    if df50 is not None and not df50.empty:
        latest = df50.iloc[-1]
        print(f'上证50: {latest.get("close", 0)}')
except Exception as e:
    print(f'获取失败: {e}')

print('\n' + '='*60)
