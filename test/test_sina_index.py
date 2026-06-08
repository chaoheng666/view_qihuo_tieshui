"""测试新浪实时指数接口"""
import requests
import pandas as pd
from datetime import datetime

print('='*60)
print('测试新浪实时指数接口')
print('='*60)

# 新浪实时指数API
def get_sina_index_realtime(codes):
    """
    获取新浪实时指数数据
    codes: 指数代码列表，如 ['sh000300', 'sh000905', 'sh000016', 'sh000852']
    """
    try:
        url = f"http://hq.sinajs.cn/list={','.join(codes)}"
        headers = {
            'Referer': 'http://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gbk'
        
        results = {}
        
        for i, code in enumerate(codes):
            # 解析返回数据
            data_str = response.text.split('\n')[i]
            # 格式: var hq_str_sh000300="name,price,change,pct,open,high,low,prev_close,volume,amount..."
            data = data_str.split('="')[1].split('"')[0].split(',')
            
            if len(data) > 10:
                index_name = code.replace('sh', '')  # 去掉sh前缀
                results[code] = {
                    'code': index_name,
                    'name': data[0],
                    'latest_price': float(data[1]) if data[1] else 0,
                    'change': float(data[2]) if data[2] else 0,
                    'change_pct': float(data[3]) if data[3] else 0,
                    'open': float(data[4]) if data[4] else 0,
                    'high': float(data[5]) if data[5] else 0,
                    'low': float(data[6]) if data[6] else 0,
                    'prev_close': float(data[7]) if data[7] else 0,
                    'volume': float(data[8]) if data[8] else 0,
                    'amount': float(data[9]) if data[9] else 0
                }
        
        return results
        
    except Exception as e:
        print(f"获取新浪指数数据失败: {e}")
        return {}

# 测试获取实时指数
print("\n【测试】获取新浪实时指数数据")

# 指数代码映射
index_codes = {
    'IF': 'sh000300',  # 沪深300
    'IC': 'sh000905',  # 中证500
    'IH': 'sh000016',  # 上证50
    'IM': 'sh000852'   # 中证1000
}

results = get_sina_index_realtime(list(index_codes.values()))

print(f"\n获取到 {len(results)} 个指数数据:")
for symbol, code in index_codes.items():
    if code in results:
        data = results[code]
        print(f"\n【{symbol}】{data['name']} ({code}):")
        print(f"  最新价: {data['latest_price']}")
        print(f"  涨跌: {data['change']:+.2f} ({data['change_pct']:+.2f}%)")
        print(f"  开盘: {data['open']}")
        print(f"  最高: {data['high']}")
        print(f"  最低: {data['low']}")
        print(f"  昨收: {data['prev_close']}")
    else:
        print(f"\n【{symbol}】获取失败")

print("\n" + "="*60)
print('测试完成')
print("="*60)
