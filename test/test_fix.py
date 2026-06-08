"""测试价差计算修复"""
import sys
import os

# 添加路径
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CURRENT_DIR, '..'))

from src.collector import FuturesDataCollector
from src.processor import PremiumCalculator

def test_realtime_premium():
    """测试实时升贴水计算"""
    print("=" * 80)
    print("测试实时升贴水计算")
    print("=" * 80)
    
    # 初始化
    collector = FuturesDataCollector()
    processor = PremiumCalculator()
    
    # 获取当前行情
    quotation = collector.get_current_quotation()
    
    # 获取所有期货和指数数据
    all_futures = quotation.get('all_futures', {})
    all_index = quotation.get('all_index', {})
    
    print(f"\n获取到 {len(all_futures)} 个品种的期货数据")
    print(f"获取到 {len(all_index)} 个品种的指数数据")
    
    # 显示每个品种的数据
    for symbol, futures_data in all_futures.items():
        index_data = all_index.get(symbol, {})
        
        print(f"\n{'='*60}")
        print(f"【{symbol}】")
        print(f"指数: {index_data.get('name', symbol)} = {index_data.get('latest_price', 0)}")
        print(f"合约数量: {len(futures_data)}")
        
        # 计算升贴水
        index_price = index_data.get('latest_price', 0)
        if index_price > 0:
            premium_results = processor.calculate_all_contracts_premium(futures_data, index_price)
            print(f"\n计算后的合约数量: {len(premium_results)}")
            
            # 显示合约
            for result in premium_results[:10]:  # 只显示前10个
                print(f"  {result['contract_code']:12} | "
                      f"期货={result['futures_price']:10.2f} | "
                      f"升贴水={result['premium_points']:8.2f} ({result['premium_rate']:+.3f}%) | "
                      f"状态={result['status']}")
            
            # 显示摘要
            summary = processor.get_premium_summary(premium_results)
            main = summary.get('main_contract')
            if main:
                print(f"\n主力合约: {main['contract_code']}")
                print(f"  升贴水: {main['premium_points']:.2f} ({main['premium_rate']:+.3f}%)")
                print(f"  年化: {main['annual_rate']:+.2f}%")
                print(f"  状态: {main['status']}")

if __name__ == '__main__':
    test_realtime_premium()
