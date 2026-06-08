"""
期货价差监控 - 价差计算和月份自动切换模块
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os
import logging

# 获取当前脚本所在目录
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(CURRENT_DIR)
sys.path.append(BASE_DIR)

from .config import WARNING_THRESHOLD, ALERT_THRESHOLD

logger = logging.getLogger(__name__)


class PremiumCalculator:
    """升贴水计算器"""
    
    def __init__(self):
        self.warning_threshold = WARNING_THRESHOLD
        self.alert_threshold = ALERT_THRESHOLD
    
    def calculate_premium(self, futures_price, index_price, days_to_expiry=90, timestamp=None):
        """
        计算单个合约的升贴水
        
        Args:
            futures_price: 期货价格
            index_price: 指数价格
            days_to_expiry: 距离到期天数
            timestamp: 数据时间戳（用于同步检查）
        
        Returns:
            dict: 包含升贴水点数、比率和年化比率
        """
        # 数据有效性检查
        if not futures_price or not index_price or index_price <= 0 or futures_price <= 0:
            return {
                'premium_points': 0,
                'premium_rate': 0.0,
                'annual_rate': 0.0,
                'data_quality': 'invalid'
            }
        
        # 价格合理性检查：IF/IH 通常在 2000-6000，但 IC/IM 会正常运行在 8000 点附近。
        if futures_price < 1000 or futures_price > 12000 or index_price < 1000 or index_price > 12000:
            logger.warning(f"价格异常 - 期货: {futures_price}, 指数: {index_price}")
            return {
                'premium_points': 0,
                'premium_rate': 0.0,
                'annual_rate': 0.0,
                'data_quality': 'outlier'
            }
        
        premium_points = float(round(futures_price - index_price, 4))
        premium_rate = float(round((premium_points / index_price) * 100, 4))
        
        # 计算年化升贴水率
        # 年化 = 升贴水率 / 距到期天数 * 365
        if days_to_expiry > 0:
            annual_rate = float(round((premium_rate / days_to_expiry) * 365, 4))
        else:
            annual_rate = 0.0
        
        # 数据质量评估
        data_quality = 'good'
        if abs(premium_rate) > 10:  # 超过10%的升贴水可能有问题
            data_quality = 'warning'
        if abs(premium_rate) > 20:
            data_quality = 'critical'
        
        return {
            'premium_points': round(premium_points, 2),
            'premium_rate': round(premium_rate, 4),
            'annual_rate': annual_rate,
            'data_quality': data_quality
        }
    
    def calculate_all_contracts_premium(self, futures_data, index_price):
        """
        计算所有合约的升贴水
        
        Args:
            futures_data: 期货行情（可以是列表或字典格式）
            index_price: 指数价格
        
        Returns:
            list: 包含各合约升贴水信息
        """
        results = []
        
        # 处理字典格式（来自collector的数据）
        contracts_list = []
        if isinstance(futures_data, dict):
            # 将字典转换为列表
            for code, contract_dict in futures_data.items():
                if isinstance(contract_dict, dict):
                    contract_dict_copy = contract_dict.copy()
                    contract_dict_copy['code'] = code
                    contracts_list.append(contract_dict_copy)
        elif isinstance(futures_data, list):
            contracts_list = futures_data
        
            # 处理每个合约
        for contract in contracts_list:
            # 提取合约信息
            contract_code = contract.get('code', '')
            position = self._get_contract_position(contract_code)
            expiry_date = self._get_contract_expiry_date(contract_code)
            days_to_expiry = self._get_days_to_expiry(expiry_date, contract_code)
            
            try:
                futures_price = float(contract.get('latest_price', 0))
            except Exception:
                futures_price = 0.0
            
            try:
                index_price = float(index_price)
            except Exception:
                index_price = 0.0
            
            # 计算升贴水（使用实际距到期天数）
            premium = self.calculate_premium(
                futures_price,
                index_price,
                days_to_expiry
            )
            
            # 判断状态（考虑数据质量）
            data_quality = premium.get('data_quality', 'good')
            
            if data_quality in ['invalid', 'outlier']:
                status = "数据异常"
                warning = True
            elif premium['premium_rate'] > self.alert_threshold:
                status = "大幅升水"
                warning = True
            elif premium['premium_rate'] < -self.alert_threshold:
                status = "大幅贴水"
                warning = True
            elif premium['premium_rate'] > self.warning_threshold:
                status = "升水"
                warning = False
            elif premium['premium_rate'] < -self.warning_threshold:
                status = "贴水"
                warning = False
            else:
                status = "正常"
                warning = False
            
            # 如果数据质量有问题，标记警告
            if data_quality in ['warning', 'critical']:
                warning = True
                status += f"({data_quality})"
            
            # 确定品种代码
            symbol = 'IF'
            if 'IC' in contract_code:
                symbol = 'IC'
            elif 'IH' in contract_code:
                symbol = 'IH'
            elif 'IM' in contract_code:
                symbol = 'IM'
            
            results.append({
                'contract_code': contract_code,
                'contract_name': contract.get('name', contract_code),
                'symbol': symbol,
                'position': position,
                'expiry_date': expiry_date,
                'days_to_expiry': days_to_expiry,
                'futures_price': float(contract.get('latest_price', 0)),
                'index_price': float(index_price),
                'premium_points': premium['premium_points'],
                'premium_rate': premium['premium_rate'],
                'annual_rate': premium['annual_rate'],
                'data_quality': data_quality,
                'change': float(contract.get('change', 0)),
                'change_pct': float(contract.get('change_pct', 0)),
                'volume': int(contract.get('volume', 0)),
                'open_interest': int(contract.get('open_interest', 0)),
                'status': status,
                'warning': warning
            })
        
        # 按成交量排序
        results.sort(key=lambda x: x['volume'], reverse=True)
        
        return results
    
    def _get_contract_position(self, contract_code):
        """获取合约位置"""
        if not contract_code or len(contract_code) < 6:
            return "其他"
        
        # 提取年月
        year_month = contract_code[-4:]
        if not year_month.isdigit():
            return "其他"
        
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # 计算当前年月
        current_ym = current_year * 100 + current_month
        
        try:
            contract_ym = int(year_month)
            
            if contract_ym == current_ym:
                return "当月"
            # 下月
            next_month = current_month + 1
            next_year = current_year
            if next_month > 12:
                next_month = 1
                next_year += 1
            if contract_ym == next_year * 100 + next_month:
                return "下月"
            # 下季
            quarter_month = current_month + 3
            quarter_year = current_year
            if quarter_month > 12:
                quarter_month -= 12
                quarter_year += 1
            if contract_ym == quarter_year * 100 + quarter_month:
                return "下季"
            # 隔季
            next_quarter_month = quarter_month + 3
            next_quarter_year = quarter_year
            if next_quarter_month > 12:
                next_quarter_month -= 12
                next_quarter_year += 1
            if contract_ym == next_quarter_year * 100 + next_quarter_month:
                return "隔季"
        except:
            pass
        
        return "其他"
    
    def _get_contract_expiry_date(self, contract_code):
        """获取合约到期日（每月第三个周五）"""
        if not contract_code or len(contract_code) < 6:
            return ""
        
        # 提取年月
        year_month = contract_code[-4:]
        if not year_month.isdigit():
            return ""
        
        try:
            year = int("20" + year_month[:2])
            month = int(year_month[2:])
            
            # 计算每月第三个周五
            expiry_date = self._get_third_friday(year, month)
            return expiry_date.strftime('%Y-%m-%d')
        except:
            return ""
    
    def _get_third_friday(self, year, month):
        """获取某月第三个周五"""
        from datetime import date
        import calendar
        
        # 获取该月第一天是周几
        first_day = date(year, month, 1)
        
        # 周一=0, 周二=1, ..., 周日=6
        first_weekday = first_day.weekday()
        
        # 周五是4
        # 计算第一个周五
        days_until_friday = (4 - first_weekday) % 7
        first_friday = first_day + timedelta(days=days_until_friday)
        
        # 第三个周五
        third_friday = first_friday + timedelta(weeks=2)
        
        return third_friday
    
    def _get_days_to_expiry(self, expiry_date_str, contract_code=''):
        """计算距离到期天数"""
        if not expiry_date_str:
            # 对于主力合约（如IF0），估算约30天
            if contract_code.endswith('0'):
                return 30
            return 0
        
        try:
            expiry_date = datetime.strptime(expiry_date_str, '%Y-%m-%d')
            days = (expiry_date - datetime.now()).days
            return max(1, days)  # 至少返回1，避免除以0
        except:
            return 0
    
    def get_premium_summary(self, premium_results):
        """生成升贴水摘要"""
        if not premium_results:
            return {
                'main_contract': None,
                'all_premium_avg': 0,
                'all_premium_count': 0
            }
        
        # 找出主力合约（成交量最大）
        main_contract = premium_results[0] if premium_results else None
        
        # 计算所有合约的平均升贴水
        if premium_results:
            avg_premium = sum(p['premium_rate'] for p in premium_results) / len(premium_results)
        else:
            avg_premium = 0
        
        return {
            'main_contract': main_contract,
            'all_premium_avg': avg_premium,
            'all_premium_count': len(premium_results)
        }
    
    def generate_warning_message(self, summary):
        """生成告警信息"""
        warnings = []
        
        if not summary or not summary.get('main_contract'):
            return warnings
        
        main = summary['main_contract']
        premium_rate = main['premium_rate']
        
        if premium_rate > self.alert_threshold:
            warnings.append(f"🚨 {main['contract_code']} 大幅升水 {premium_rate:.2f}%，注意回调风险！")
        elif premium_rate < -self.alert_threshold:
            warnings.append(f"🚨 {main['contract_code']} 大幅贴水 {premium_rate:.2f}%，可能存在反弹机会！")
        elif premium_rate > self.warning_threshold:
            warnings.append(f"⚠️ {main['contract_code']} 升水 {premium_rate:.2f}%，关注价差收窄")
        elif premium_rate < -self.warning_threshold:
            warnings.append(f"⚠️ {main['contract_code']} 贴水 {premium_rate:.2f}%，关注价差扩大")
        
        return warnings
    
    def calculate_multi_species_premium(self, all_futures, all_index):
        """
        计算多品种升贴水（IF/IC/IM）
        
        Args:
            all_futures: dict，品种代码 -> 期货行情列表
            all_index: dict，品种代码 -> 指数数据
        
        Returns:
            dict: 品种代码 -> 升贴水结果列表
        """
        results = {}
        
        for species_code in ['IF', 'IC', 'IM']:
            futures_data = all_futures.get(species_code, [])
            index_data = all_index.get(species_code)
            
            if not futures_data or not index_data:
                continue
            
            index_price = index_data.get('latest_price', 0)
            if index_price == 0:
                continue
            
            # 计算该品种所有合约的升贴水
            species_results = self.calculate_all_contracts_premium(futures_data, index_price)
            
            # 添加品种信息
            for r in species_results:
                r['species_code'] = species_code
                r['species_name'] = index_data.get('name', species_code)
                r['index_price'] = index_price
            
            if species_results:
                results[species_code] = {
                    'species_name': index_data.get('name', species_code),
                    'index_data': index_data,
                    'contracts': species_results,
                    'main_contract': species_results[0] if species_results else None
                }
        
        return results


class ContractSwitcher:
    """合约自动切换器"""
    
    def __init__(self):
        self.contracts = [
            {'code': 'IF当月', 'position': '当月'},
            {'code': 'IF下月', 'position': '下月'},
            {'code': 'IF下季', 'position': '下季'},
            {'code': 'IF隔季', 'position': '隔季'}
        ]
    
    def get_delivery_months(self):
        """
        获取当月、下月、下季、隔季合约代码
        
        Returns:
            list: 合约信息列表
        """
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        contracts = []
        
        # 当月
        contracts.append({
            'code': f'IF{current_year % 100:02d}{current_month:02d}',
            'position': '当月',
            'expiry_date': self._get_third_friday(current_year, current_month).strftime('%Y-%m-%d')
        })
        
        # 下月
        next_month = current_month + 1
        next_year = current_year
        if next_month > 12:
            next_month = 1
            next_year += 1
        contracts.append({
            'code': f'IF{next_year % 100:02d}{next_month:02d}',
            'position': '下月',
            'expiry_date': self._get_third_friday(next_year, next_month).strftime('%Y-%m-%d')
        })
        
        # 下季（季月：3,6,9,12）
        quarter_months = [3, 6, 9, 12]
        next_quarter_idx = (quarter_months.index(current_month) + 1) % 4 if current_month in quarter_months else 0
        contracts.append({
            'code': f'IF{next_year % 100:02d}{quarter_months[next_quarter_idx]:02d}',
            'position': '下季',
            'expiry_date': self._get_third_friday(next_year, quarter_months[next_quarter_idx]).strftime('%Y-%m-%d')
        })
        
        # 隔季
        next_quarter_idx2 = (next_quarter_idx + 1) % 4
        next_quarter_year2 = next_year
        if quarter_months[next_quarter_idx2] < quarter_months[next_quarter_idx]:
            next_quarter_year2 += 1
        contracts.append({
            'code': f'IF{next_quarter_year2 % 100:02d}{quarter_months[next_quarter_idx2]:02d}',
            'position': '隔季',
            'expiry_date': self._get_third_friday(next_quarter_year2, quarter_months[next_quarter_idx2]).strftime('%Y-%m-%d')
        })
        
        return contracts
    
    def _get_third_friday(self, year, month):
        """获取某月第三个周五"""
        from datetime import date
        import calendar
        
        # 获取该月第一天是周几
        first_day = date(year, month, 1)
        
        # 周一=0, 周二=1, ..., 周日=6
        first_weekday = first_day.weekday()
        
        # 周五是4
        # 计算第一个周五
        days_until_friday = (4 - first_weekday) % 7
        first_friday = first_day + timedelta(days=days_until_friday)
        
        # 第三个周五
        third_friday = first_friday + timedelta(weeks=2)
        
        return third_friday
    
    def format_contract_info(self, contracts):
        """格式化合约信息用于显示"""
        result = []
        
        for c in contracts:
            expiry = datetime.strptime(c['expiry_date'], '%Y-%m-%d')
            days_to_expiry = (expiry - datetime.now()).days
            
            result.append({
                'code': c['code'],
                'position': c['position'],
                'expiry_date': c['expiry_date'],
                'days_to_expiry': days_to_expiry,
                'status': self._get_status_text(days_to_expiry)
            })
        
        return result
    
    def _get_status_text(self, days):
        """获取状态描述"""
        if days <= 0:
            return "已到期"
        elif days <= 7:
            return "即将到期"
        elif days <= 30:
            return f"{days}天后到期"
        else:
            return f"{days}天后到期"
    
    def is_contract_expired(self, contract_code):
        """检查合约是否已到期"""
        if not contract_code or len(contract_code) < 6:
            return True
        
        year_month = contract_code[-4:]
        if not year_month.isdigit():
            return True
        
        try:
            year = int("20" + year_month[:2])
            month = int(year_month[2:])
            
            expiry = self._get_third_friday(year, month)
            return datetime.now() > expiry
        except:
            return True
    
    def get_recommended_contract(self, contracts_data):
        """根据成交量推荐主力合约"""
        if not contracts_data:
            return None
        
        # 按成交量排序
        sorted_contracts = sorted(
            contracts_data,
            key=lambda x: x.get('volume', 0),
            reverse=True
        )
        
        # 返回成交量最大的合约
        if sorted_contracts:
            recommended = sorted_contracts[0]['code']
            
            # 检查是否已到期
            if self.is_contract_expired(recommended):
                # 如果主力已到期，返回下一个
                if len(sorted_contracts) > 1:
                    return sorted_contracts[1]['code']
                else:
                    return None
            
            return recommended
        
        return None
