"""测试使用新浪API获取中证1000期货 - 调试版"""
import requests

def get_sina_futures_realtime(codes):
    """使用新浪API获取期货实时数据"""
    try:
        url = f"http://hq.sinajs.cn/list={codes}"
        headers = {
            'Referer': 'http://finance.sina.com.cn',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'gbk'
        
        # 打印原始数据供分析
        print("=" * 60)
        print("原始数据内容分析")
        print("=" * 60)
        
        # 解析返回数据
        results = {}
        for line in response.text.strip().split('\n'):
            if 'hq_str_nf_' not in line:
                continue
            
            # 获取合约代码
            var_name = line.split('hq_str_nf_')[1].split('=')[0]
            data_str = line.split('="')[1].split('"')[0]
            data = data_str.split(',')
            
            print(f"\n合约: {var_name}")
            print(f"数据字段总数: {len(data)}")
            
            # 打印前20个字段分析
            print("前20个字段:")
            for i, val in enumerate(data[:20]):
                print(f"  [{i}]: {val}")
            
            # 打印后10个字段
            print("后10个字段:")
            for i, val in enumerate(data[-10:]):
                print(f"  [{len(data)-10+i}]: {val}")
            
            if len(data) >= 20:
                # 根据分析结果解析
                # data[0]: 昨结算
                # data[1]: 昨收
                # data[2]: 今开
                # data[3]: 当前价
                # data[4]: 成交量(手)
                # data[5]: 成交额
                # data[6]: 持仓量
                # ...
                results[var_name] = {
                    'symbol': var_name,
                    'name': data[-2] if len(data) > 1 else var_name,  # 合约名称
                    'prev_settlement': float(data[0]) if data[0] else 0,  # 昨结算
                    'prev_close': float(data[1]) if data[1] else 0,  # 昨收
                    'open': float(data[2]) if data[2] else 0,  # 今开
                    'latest_price': float(data[3]) if data[3] else 0,  # 最新价
                    'volume': float(data[4]) if data[4] else 0,  # 成交量
                    'amount': float(data[5]) if data[5] else 0,  # 成交额
                    'open_interest': float(data[6]) if data[6] else 0,  # 持仓量
                }
        
        return results
    except Exception as e:
        print(f"获取新浪期货数据失败: {e}")
        import traceback
        traceback.print_exc()
        return {}

# 使用nf_前缀获取IM期货
print("获取中证1000期货(IM)数据\n")

im_codes = "nf_IM2606,nf_IM0"
results = get_sina_futures_realtime(im_codes)

if results:
    print("\n" + "=" * 60)
    print("解析结果")
    print("=" * 60)
    for code, data in results.items():
        print(f"\n合约: {data['name']} ({code})")
        print(f"  昨结算: {data['prev_settlement']:.1f}")
        print(f"  昨收:   {data['prev_close']:.1f}")
        print(f"  今开:   {data['open']:.1f}")
        print(f"  最新价: {data['latest_price']:.1f}")
        print(f"  成交量: {data['volume']:.0f} 手")
        print(f"  成交额: {data['amount']:.2f}")
        print(f"  持仓量: {data['open_interest']:.0f}")
