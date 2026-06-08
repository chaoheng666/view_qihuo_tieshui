"""
期货价差监控系统 - 数据缓存模块
提供内存缓存和异步数据采集功能
"""

import time
import threading
from datetime import datetime, timedelta
from collections import deque
from typing import Dict, Any, Optional, Callable
import logging

logger = logging.getLogger(__name__)


class DataCache:
    """数据缓存管理器"""
    
    def __init__(self, ttl_seconds: int = 300, max_history: int = 100):
        """
        初始化缓存
        
        Args:
            ttl_seconds: 缓存过期时间（秒），默认5分钟
            max_history: 历史数据最大条数
        """
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._timestamps: Dict[str, float] = {}
        self._history: Dict[str, deque] = {}
        self._lock = threading.RLock()
        self._ttl_seconds = ttl_seconds
        self._max_history = max_history
        self._hit_count = 0
        self._miss_count = 0
        self._stats_lock = threading.Lock()
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """
        设置缓存
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 自定义过期时间（秒）
        """
        with self._lock:
            expire_time = time.time() + (ttl or self._ttl_seconds)
            self._cache[key] = {
                'value': value,
                'expire_time': expire_time
            }
            self._timestamps[key] = time.time()
            
            # 记录历史
            if key not in self._history:
                self._history[key] = deque(maxlen=self._max_history)
            
            self._history[key].append({
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'value': value
            })
            
            logger.debug(f"缓存已设置: {key}")
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        获取缓存
        
        Args:
            key: 缓存键
            default: 默认值
        
        Returns:
            缓存值或默认值
        """
        with self._lock:
            if key not in self._cache:
                self._miss_count += 1
                logger.debug(f"缓存未命中: {key}")
                return default
            
            cache_entry = self._cache[key]
            
            # 检查是否过期
            if time.time() > cache_entry['expire_time']:
                del self._cache[key]
                if key in self._timestamps:
                    del self._timestamps[key]
                self._miss_count += 1
                logger.debug(f"缓存已过期: {key}")
                return default
            
            self._hit_count += 1
            logger.debug(f"缓存命中: {key}")
            return cache_entry['value']
    
    def get_or_set(self, key: str, factory: Callable[[], Any], ttl: Optional[int] = None) -> Any:
        """
        获取缓存，如果不存在则调用工厂函数创建
        
        Args:
            key: 缓存键
            factory: 工厂函数
            ttl: 自定义过期时间
        
        Returns:
            缓存值
        """
        value = self.get(key)
        if value is None:
            logger.debug(f"缓存未命中，创建新值: {key}")
            value = factory()
            if value is not None:
                self.set(key, value, ttl)
        return value
    
    def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
        
        Returns:
            是否删除成功
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if key in self._timestamps:
                    del self._timestamps[key]
                logger.debug(f"缓存已删除: {key}")
                return True
            return False
    
    def clear(self) -> None:
        """清空所有缓存"""
        with self._lock:
            self._cache.clear()
            self._timestamps.clear()
            logger.info("所有缓存已清空")
    
    def get_history(self, key: str, limit: int = 10) -> list:
        """
        获取历史数据
        
        Args:
            key: 缓存键
            limit: 返回条数
        
        Returns:
            历史数据列表
        """
        with self._lock:
            if key not in self._history:
                return []
            return list(self._history[key])[-limit:]
    
    def is_expired(self, key: str) -> bool:
        """
        检查缓存是否过期
        
        Args:
            key: 缓存键
        
        Returns:
            是否过期
        """
        with self._lock:
            if key not in self._cache:
                return True
            
            return time.time() > self._cache[key]['expire_time']
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取缓存统计信息
        
        Returns:
            统计信息字典
        """
        with self._lock, self._stats_lock:
            total_requests = self._hit_count + self._miss_count
            hit_rate = self._hit_count / total_requests if total_requests > 0 else 0
            
            return {
                'hit_count': self._hit_count,
                'miss_count': self._miss_count,
                'hit_rate': f"{hit_rate:.2%}",
                'total_keys': len(self._cache),
                'total_history': sum(len(h) for h in self._history.values())
            }
    
    def refresh(self, key: str, factory: Callable[[], Any]) -> Any:
        """
        刷新缓存
        
        Args:
            key: 缓存键
            factory: 工厂函数
        
        Returns:
            新值
        """
        logger.info(f"刷新缓存: {key}")
        value = factory()
        if value is not None:
            self.set(key, value)
        return value
    
    def cleanup(self) -> int:
        """
        清理过期缓存
        
        Returns:
            清理的缓存数量
        """
        with self._lock:
            expired_keys = [
                key for key, entry in self._cache.items()
                if time.time() > entry['expire_time']
            ]
            
            for key in expired_keys:
                del self._cache[key]
                if key in self._timestamps:
                    del self._timestamps[key]
            
            if expired_keys:
                logger.info(f"已清理 {len(expired_keys)} 个过期缓存")
            
            return len(expired_keys)


class AsyncDataCollector:
    """异步数据采集器"""
    
    def __init__(self, timeout: int = 10, max_workers: int = 4):
        """
        初始化异步采集器
        
        Args:
            timeout: 超时时间（秒）
            max_workers: 最大并发数
        """
        self._timeout = timeout
        self._max_workers = max_workers
        self._executor = None
        self._lock = threading.Lock()
        self._results: Dict[str, Any] = {}
        self._errors: Dict[str, str] = {}
    
    def collect(self, tasks: Dict[str, Callable[[], Any]]) -> Dict[str, Any]:
        """
        并发采集多个数据源
        
        Args:
            tasks: 任务字典，键为任务名，值为采集函数
        
        Returns:
            结果字典
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        
        results = {}
        errors = {}
        
        try:
            with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
                # 提交所有任务
                future_to_name = {
                    executor.submit(self._safe_execute, name, func): name
                    for name, func in tasks.items()
                }
                
                # 收集结果
                for future in as_completed(future_to_name, timeout=self._timeout):
                    name = future_to_name[future]
                    try:
                        result = future.result(timeout=1)
                        if result is not None:
                            results[name] = result
                            logger.info(f"成功采集 {name}")
                        else:
                            errors[name] = "采集返回None"
                            logger.warning(f"{name} 采集返回None")
                    except Exception as e:
                        errors[name] = str(e)
                        logger.error(f"{name} 采集失败: {e}")
        
        except Exception as e:
            logger.error(f"异步采集异常: {e}")
        
        with self._lock:
            self._results = results
            self._errors = errors
        
        return results
    
    def _safe_execute(self, name: str, func: Callable[[], Any]) -> Any:
        """
        安全执行采集函数
        
        Args:
            name: 任务名
            func: 采集函数
        
        Returns:
            采集结果
        """
        try:
            return func()
        except Exception as e:
            logger.error(f"{name} 执行异常: {e}")
            raise
    
    def get_results(self) -> Dict[str, Any]:
        """
        获取采集结果
        
        Returns:
            结果字典
        """
        with self._lock:
            return self._results.copy()
    
    def get_errors(self) -> Dict[str, str]:
        """
        获取错误信息
        
        Returns:
            错误字典
        """
        with self._lock:
            return self._errors.copy()
    
    def has_errors(self) -> bool:
        """
        检查是否有错误
        
        Returns:
            是否有错误
        """
        with self._lock:
            return len(self._errors) > 0


class RetryManager:
    """重试管理器"""
    
    def __init__(self, max_retries: int = 3, backoff_factor: float = 1.5):
        """
        初始化重试管理器
        
        Args:
            max_retries: 最大重试次数
            backoff_factor: 退避因子
        """
        self._max_retries = max_retries
        self._backoff_factor = backoff_factor
    
    def execute(self, func: Callable[[], Any], *args, **kwargs) -> Any:
        """
        执行带重试的函数
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            函数返回值
        """
        last_exception = None
        wait_time = 1.0
        
        for attempt in range(self._max_retries):
            try:
                result = func(*args, **kwargs)
                if attempt > 0:
                    logger.info(f"重试成功 (尝试 {attempt + 1}/{self._max_retries})")
                return result
            except Exception as e:
                last_exception = e
                if attempt < self._max_retries - 1:
                    logger.warning(f"尝试 {attempt + 1}/{self._max_retries} 失败，{wait_time:.1f}秒后重试: {e}")
                    time.sleep(wait_time)
                    wait_time *= self._backoff_factor
                else:
                    logger.error(f"所有重试失败 ({self._max_retries}次): {e}")
        
        raise last_exception


class RateLimiter:
    """频率限制器"""
    
    def __init__(self, max_calls: int, time_window: int):
        """
        初始化频率限制器
        
        Args:
            max_calls: 最大调用次数
            time_window: 时间窗口（秒）
        """
        self._max_calls = max_calls
        self._time_window = time_window
        self._calls: deque = deque()
        self._lock = threading.Lock()
    
    def acquire(self) -> bool:
        """
        获取调用许可
        
        Returns:
            是否允许调用
        """
        with self._lock:
            now = time.time()
            
            # 清理过期的调用记录
            while self._calls and self._calls[0] < now - self._time_window:
                self._calls.popleft()
            
            # 检查是否超过限制
            if len(self._calls) >= self._max_calls:
                return False
            
            # 记录此次调用
            self._calls.append(now)
            return True
    
    def wait_if_needed(self) -> None:
        """如果达到限制则等待"""
        if not self.acquire():
            logger.warning("达到API调用频率限制，等待...")
            time.sleep(self._time_window)
            self.acquire()
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取统计信息
        
        Returns:
            统计信息
        """
        with self._lock:
            return {
                'max_calls': self._max_calls,
                'time_window': self._time_window,
                'current_calls': len(self._calls)
            }


# 全局缓存实例
_global_cache = DataCache()
_global_collector = AsyncDataCollector()
_global_retry_manager = RetryManager()


def get_cache() -> DataCache:
    """获取全局缓存实例"""
    return _global_cache


def get_collector() -> AsyncDataCollector:
    """获取全局采集器实例"""
    return _global_collector


def get_retry_manager() -> RetryManager:
    """获取全局重试管理器实例"""
    return _global_retry_manager
