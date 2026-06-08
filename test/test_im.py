"""
测试IM期货接口 - 扩展测试
"""
import akshare as ak

print("测试IM期货接口 - 扩展测试")
print("=" * 50)

# 尝试直接用合约代码获取IM数据
# IM合约格式: IM2605, IM2606等
try:
    print("\n1. 尝试直接获取IM合约 (IM2605)...")
    df = ak.futures_zh_daily_sina(symbol="IM2605")
    if df is not None and not df.empty:
        print(f"成功! 共 {len(df)} 条")
        print(df.tail())
except Exception as e:
    print(f"失败: {e}")

# 尝试使用新浪期货接口获取所有期货
try:
    print("\n2. 尝试获取所有股指期货...")
    # 沪深300期货
    df_if = ak.futures_zh_daily_sina(symbol="IF2605")
    print(f"IF2605: {len(df_if) if df_if is not None else 0} 条")
    
    # 中证1000期货
    df_im = ak.futures_zh_daily_sina(symbol="IM2605")
    print(f"IM2605: {len(df_im) if df_im is not None else 0} 条")
except Exception as e:
    print(f"失败: {e}")

# 尝试获取中证1000指数
try:
    print("\n3. 获取中证1000指数...")
    df = ak.stock_zh_index_daily(symbol="sh000852")
    if df is not None and not df.empty:
        print(f"中证1000指数(000852): {len(df)} 条")
        print(df.tail())
except Exception as e:
    print(f"失败: {e}")
