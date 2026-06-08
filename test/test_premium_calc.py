"""测试升贴水计算"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from src.collector import FuturesDataCollector
from src.processor import PremiumCalculator

# 初始化
collector = FuturesDataCollector()
processor = PremiumCalculator()

print('='*60)
print('测试升贴水计算')
print('='*60)

# 获取实时行情
quotation = collector.get_current_quotation()

# 获取所有品种数据
all_futures = quotation.get('all_futures', {})
all_index = quotation.get('all_index', {})

print(f"\n获取到 {len(all_futures)} 个品种的期货数据:")
for symbol, futures_list in all_futures.items():
    print(f"  {symbol}: {len(futures_list)} 个合约")

print(f"\n获取到 {len(all_index)} 个品种的指数数据:")
for symbol, index_data in all_index.items():
    print(f"  {symbol}: {index_data['name']} = {index_data['latest_price']}")

# 计算每个品种的升贴水
print('\n' + '='*60)
print('升贴水计算结果')
print('='*60)

all_contracts = []

for symbol in ['IF', 'IC', 'IH', 'IM']:
    futures_data = all_futures.get(symbol, [])
    index_data = all_index.get(symbol, {})
    
    if not futures_data or not index_data:
        print(f"\n【{symbol}】数据不完整，跳过")
        continue
    
    index_price = index_data['latest_price']
    
    # 计算该品种的升贴水
    premium_results = processor.calculate_all_contracts_premium(futures_data, index_price)
    
    print(f"\n【{symbol} vs {index_data['name']}】")
    print(f"指数价格: {index_price}")
    print("-" * 50)
    
    for result in premium_results:
        print(f"  {result['contract_code']}: 期货={result['futures_price']}, "
              f"升贴水={result['premium_points']:.2f}点 "
              f"({result['premium_rate']:.4f}%) "
              f"[{result['status']}]")
    
    all_contracts.extend(premium_results)

print(f"\n\n共获取 {len(all_contracts)} 个合约数据")

# 测试品种筛选
print("\n" + "="*60)
print("测试品种筛选")
print("="*60)

symbol_filter = 'IF'
filtered = [c for c in all_contracts if c['contract_code'].startswith(symbol_filter)]
print(f"筛选 '{symbol_filter}' 后: {len(filtered)} 个合约")
for c in filtered:
    print(f"  {c['contract_code']}: {c['premium_points']:.2f}点")

print("\n" + "="*60)
