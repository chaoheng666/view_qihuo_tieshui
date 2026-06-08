"""
期货价差框架优化功能测试
"""

import sys
import os
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def test_cache_module():
    """测试缓存模块"""
    print("\n" + "="*60)
    print("测试1: 数据缓存模块")
    print("="*60)
    
    try:
        from src.cache import DataCache, AsyncDataCollector, RetryManager
        
        # 测试缓存
        cache = DataCache(ttl_seconds=5)
        
        # 设置缓存
        cache.set('test_key', {'data': 'test_value'})
        print("✓ 设置缓存成功")
        
        # 获取缓存
        value = cache.get('test_key')
        assert value is not None
        assert value['data'] == 'test_value'
        print("✓ 获取缓存成功")
        
        # 测试过期
        import time
        time.sleep(6)
        expired = cache.get('test_key')
        assert expired is None
        print("✓ 缓存过期机制正常")
        
        # 测试统计
        cache.set('key1', 'value1')
        cache.get('key1')
        cache.get('nonexistent')
        stats = cache.get_stats()
        print(f"✓ 缓存统计: {stats}")
        
        # 测试历史记录
        for i in range(5):
            cache.set('history_key', f'value_{i}')
        history = cache.get_history('history_key', limit=3)
        print(f"✓ 历史记录条数: {len(history)}")
        
        print("\n✅ 缓存模块测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 缓存模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_async_collector():
    """测试异步采集器"""
    print("\n" + "="*60)
    print("测试2: 异步数据采集器")
    print("="*60)
    
    try:
        from src.cache import AsyncDataCollector
        
        collector = AsyncDataCollector(timeout=5, max_workers=4)
        
        # 定义任务
        def task1():
            import time
            time.sleep(0.5)
            return {'result': 'task1_success'}
        
        def task2():
            import time
            time.sleep(0.3)
            return {'result': 'task2_success'}
        
        def task3():
            raise Exception("Task3 故意失败")
        
        # 并发执行
        tasks = {
            'task1': task1,
            'task2': task2,
            'task3': task3,
        }
        
        results = collector.collect(tasks)
        errors = collector.get_errors()
        
        print(f"✓ 成功任务数: {len(results)}")
        print(f"✓ 失败任务数: {len(errors)}")
        print(f"✓ 任务结果: {results}")
        
        assert len(results) == 2
        assert len(errors) == 1
        assert 'task3' in errors
        
        print("\n✅ 异步采集器测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 异步采集器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_retry_manager():
    """测试重试管理器"""
    print("\n" + "="*60)
    print("测试3: 重试管理器")
    print("="*60)
    
    try:
        from src.cache import RetryManager
        
        retry_mgr = RetryManager(max_retries=3, backoff_factor=1.5)
        
        # 测试成功函数
        def success_func():
            return "success"
        
        result = retry_mgr.execute(success_func)
        assert result == "success"
        print("✓ 重试成功函数测试通过")
        
        # 测试失败后重试成功
        attempts = []
        def flaky_func():
            attempts.append(1)
            if len(attempts) < 2:
                raise Exception("第一次失败")
            return "success_after_retry"
        
        result = retry_mgr.execute(flaky_func)
        assert result == "success_after_retry"
        assert len(attempts) == 2
        print(f"✓ 重试机制测试通过（尝试次数: {len(attempts)})")
        
        # 测试全部失败
        attempts.clear()
        def fail_func():
            attempts.append(1)
            raise Exception("总是失败")
        
        try:
            retry_mgr.execute(fail_func)
            assert False, "应该抛出异常"
        except Exception as e:
            assert str(e) == "总是失败"
            assert len(attempts) == 3
            print(f"✓ 重试耗尽测试通过（尝试次数: {len(attempts)}）")
        
        print("\n✅ 重试管理器测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 重试管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_optimized_collector():
    """测试优化版采集器"""
    print("\n" + "="*60)
    print("测试4: 优化版数据采集器")
    print("="*60)
    
    try:
        from src.collector_optimized import get_collector_instance
        
        collector = get_collector_instance()
        
        # 测试获取数据（第一次，无缓存）
        print("正在获取实时数据（首次，无缓存）...")
        start_time = datetime.now()
        data1 = collector.get_current_quotation()
        time1 = (datetime.now() - start_time).total_seconds()
        print(f"✓ 首次获取耗时: {time1:.2f}秒")
        
        # 检查数据结构
        assert 'all_futures' in data1
        assert 'all_index' in data1
        assert 'timestamp' in data1
        print("✓ 数据结构正确")
        
        # 测试缓存获取（第二次）
        print("\n正在获取实时数据（第二次，使用缓存）...")
        start_time = datetime.now()
        data2 = collector.get_current_quotation()
        time2 = (datetime.now() - start_time).total_seconds()
        print(f"✓ 缓存获取耗时: {time2:.2f}秒")
        
        # 性能提升验证
        if time2 < time1:
            improvement = (1 - time2 / time1) * 100
            print(f"✓ 性能提升: {improvement:.1f}%")
        
        # 检查缓存统计
        stats = collector.get_cache_stats()
        print(f"✓ 缓存统计: {stats}")
        
        # 测试强制刷新
        print("\n正在测试强制刷新...")
        data3 = collector.refresh_data()
        assert 'timestamp' in data3
        print("✓ 强制刷新功能正常")
        
        print("\n✅ 优化版采集器测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 优化版采集器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_history_module():
    """测试历史分析模块"""
    print("\n" + "="*60)
    print("测试5: 历史数据分析模块")
    print("="*60)
    
    try:
        from src.history import (
            HistoricalAnalyzer, 
            EnhancedAlertManager, 
            CrossSpeciesAnalyzer
        )
        
        # 测试历史分析器
        analyzer = HistoricalAnalyzer(storage_path='data')
        print("✓ 历史分析器初始化成功")
        
        # 测试告警管理器
        alert_mgr = EnhancedAlertManager()
        
        # 模拟告警数据
        test_data = {
            'IF': {
                'main_contract': {
                    'contract_code': 'IF2606',
                    'premium_rate': 1.5,
                    'annual_rate': 18.25,
                }
            },
            'IC': {
                'main_contract': {
                    'contract_code': 'IC2606',
                    'premium_rate': -2.5,
                    'annual_rate': -30.4,
                }
            }
        }
        
        alerts = alert_mgr.check_premium_alert(test_data)
        print(f"✓ 告警检测: 生成 {len(alerts)} 个告警")
        
        for alert in alerts:
            print(f"  - {alert['message']}")
        
        # 测试告警摘要
        summary = alert_mgr.get_alert_summary()
        print(f"✓ 告警摘要: {summary['total']} 条总计")
        
        # 测试跨品种分析器
        cross_analyzer = CrossSpeciesAnalyzer()
        spreads = cross_analyzer.get_all_spreads(test_data)
        print(f"✓ 跨品种价差: {spreads}")
        
        print("\n✅ 历史分析模块测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 历史分析模块测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_premium_calculation():
    """测试升贴水计算"""
    print("\n" + "="*60)
    print("测试6: 完整升贴水计算流程")
    print("="*60)
    
    try:
        from src.collector_optimized import get_collector_instance
        from src.processor import PremiumCalculator
        from src.history import get_historical_analyzer
        
        # 获取采集器
        collector = get_collector_instance()
        
        # 获取实时数据
        quotation = collector.get_current_quotation()
        all_futures = quotation.get('all_futures', {})
        all_index = quotation.get('all_index', {})
        
        # 计算升贴水
        processor = PremiumCalculator()
        calculator = processor
        
        results = {}
        for symbol in ['IF', 'IC', 'IH', 'IM']:
            futures_data = all_futures.get(symbol, {})
            index_data = all_index.get(symbol)
            
            if not futures_data or not index_data:
                continue
            
            index_price = index_data.get('latest_price', 0)
            premium_results = calculator.calculate_all_contracts_premium(futures_data, index_price)
            
            results[symbol] = {
                'contracts': premium_results,
                'main_contract': premium_results[0] if premium_results else None,
                'index_data': index_data,
            }
            
            # 打印结果
            if premium_results:
                main = premium_results[0]
                print(f"\n【{symbol}】 {index_data.get('name', symbol)}")
                print(f"  指数: {index_price:.2f}")
                print(f"  主力: {main['contract_code']} @ {main['futures_price']:.2f}")
                print(f"  升贴水: {main['premium_points']:+.2f} ({main['premium_rate']:+.3f}%)")
                print(f"  年化: {main['annual_rate']:+.2f}%")
        
        # 保存快照
        hist_analyzer = get_historical_analyzer()
        saved = hist_analyzer.save_premium_snapshot(results)
        print(f"\n✓ 快照保存: {'成功' if saved else '失败'}")
        
        print("\n✅ 升贴水计算测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 升贴水计算测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "="*70)
    print("  期货价差监控框架 - 优化功能测试")
    print("="*70)
    
    tests = [
        ("缓存模块", test_cache_module),
        ("异步采集器", test_async_collector),
        ("重试管理器", test_retry_manager),
        ("优化版采集器", test_optimized_collector),
        ("历史分析模块", test_history_module),
        ("升贴水计算", test_premium_calculation),
    ]
    
    results = {}
    
    for name, test_func in tests:
        try:
            results[name] = test_func()
        except Exception as e:
            print(f"\n❌ {name} 测试异常: {e}")
            results[name] = False
    
    # 打印汇总
    print("\n" + "="*70)
    print("  测试结果汇总")
    print("="*70)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"  {name:20s}: {status}")
    
    print(f"\n  总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n🎉 所有测试通过！框架优化成功！")
        return 0
    else:
        print(f"\n⚠️  {total - passed} 个测试失败，请检查。")
        return 1


if __name__ == '__main__':
    import time
    start_time = time.time()
    exit_code = main()
    elapsed = time.time() - start_time
    print(f"\n总耗时: {elapsed:.2f} 秒")
    exit(exit_code)
