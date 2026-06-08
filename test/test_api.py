import requests
import json

try:
    r = requests.get('http://localhost:5001/api/premium/realtime', timeout=10)
    data = r.json()
    
    print('=' * 60)
    print('期货价差监控系统 - API测试')
    print('=' * 60)
    
    if data.get('success'):
        print('✓ 数据获取成功')
        contracts = data.get('contracts', [])
        print(f'\n共获取 {len(contracts)} 个合约数据:\n')
        
        for c in contracts:
            print(f"【{c['contract_code']}】")
            print(f"  合约位置: {c['position']}")
            print(f"  期货价格: {c['futures_price']}")
            print(f"  指数价格: {c['index_price']}")
            print(f"  升贴水: {c['premium_points']:.2f} 点")
            print(f"  升贴水率: {c['premium_rate']:.2f}%")
            print(f"  年化升贴水率: {c['annual_rate']:.2f}%")
            print(f"  距到期: {c['days_to_expiry']} 天")
            print(f"  状态: {c['status']}")
            print()
        
        # 显示摘要
        print('-' * 60)
        summaries = data.get('all_summaries', {})
        print('各品种主力合约摘要:')
        for symbol, summary in summaries.items():
            if summary:
                print(f"  {symbol}: 升贴水 {summary.get('premium_points', 0):.2f}点 "
                      f"({summary.get('premium_rate', 0):.2f}%)")
    else:
        print('✗ 数据获取失败')
        print(f"错误信息: {data.get('error', '未知错误')}")
        
except Exception as e:
    print(f'✗ 请求失败: {e}')
