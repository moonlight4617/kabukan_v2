# -*- coding: utf-8 -*-
"""
パフォーマンス最適化サービス
Lambda関数の実行時間最適化、メモリ使用量の監視と最適化機能を提供
"""

import logging
import asyncio
import psutil
import gc
import time
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import threading
import functools
import weakref
from concurrent.futures import ThreadPoolExecutor, as_completed
import sys
import tracemalloc


logger = logging.getLogger(__name__)


class OptimizationLevel(Enum):
    """最適化レベル"""
    NONE = "none"
    BASIC = "basic"
    MODERATE = "moderate"
    AGGRESSIVE = "aggressive"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            OptimizationLevel.NONE: "最適化なし",
            OptimizationLevel.BASIC: "基本",
            OptimizationLevel.MODERATE: "中程度",
            OptimizationLevel.AGGRESSIVE: "積極的"
        }[self]


class ResourceType(Enum):
    """リソースタイプ"""
    MEMORY = "memory"
    CPU = "cpu"
    NETWORK = "network"
    DISK = "disk"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            ResourceType.MEMORY: "メモリ",
            ResourceType.CPU: "CPU",
            ResourceType.NETWORK: "ネットワーク",
            ResourceType.DISK: "ディスク"
        }[self]


@dataclass
class PerformanceMetrics:
    """パフォーマンスメトリクス"""
    timestamp: datetime
    execution_time: float
    memory_usage_mb: float
    peak_memory_mb: float
    cpu_percent: float
    memory_percent: float
    gc_collections: int
    active_threads: int
    context: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "execution_time": self.execution_time,
            "memory_usage_mb": self.memory_usage_mb,
            "peak_memory_mb": self.peak_memory_mb,
            "cpu_percent": self.cpu_percent,
            "memory_percent": self.memory_percent,
            "gc_collections": self.gc_collections,
            "active_threads": self.active_threads,
            "context": self.context
        }


@dataclass
class OptimizationConfig:
    """最適化設定"""
    level: OptimizationLevel = OptimizationLevel.MODERATE
    enable_memory_monitoring: bool = True
    enable_gc_optimization: bool = True
    enable_threading_optimization: bool = True
    enable_caching: bool = True
    memory_threshold_mb: float = 512.0
    execution_timeout_seconds: float = 600.0
    gc_frequency: int = 100
    max_concurrent_operations: int = 10

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "level": self.level.value,
            "enable_memory_monitoring": self.enable_memory_monitoring,
            "enable_gc_optimization": self.enable_gc_optimization,
            "enable_threading_optimization": self.enable_threading_optimization,
            "enable_caching": self.enable_caching,
            "memory_threshold_mb": self.memory_threshold_mb,
            "execution_timeout_seconds": self.execution_timeout_seconds,
            "gc_frequency": self.gc_frequency,
            "max_concurrent_operations": self.max_concurrent_operations
        }


@dataclass
class OptimizationResult:
    """最適化結果"""
    success: bool
    optimization_type: str
    before_metrics: Optional[PerformanceMetrics]
    after_metrics: Optional[PerformanceMetrics]
    improvement_percent: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)

    @property
    def memory_improvement(self) -> float:
        """メモリ改善率"""
        if self.before_metrics and self.after_metrics:
            before = self.before_metrics.memory_usage_mb
            after = self.after_metrics.memory_usage_mb
            if before > 0:
                return ((before - after) / before) * 100
        return 0.0

    @property
    def time_improvement(self) -> float:
        """実行時間改善率"""
        if self.before_metrics and self.after_metrics:
            before = self.before_metrics.execution_time
            after = self.after_metrics.execution_time
            if before > 0:
                return ((before - after) / before) * 100
        return 0.0


class MemoryMonitor:
    """メモリ監視クラス"""
    
    def __init__(self):
        self.start_memory = 0
        self.peak_memory = 0
        self.current_memory = 0
        self.monitoring = False
        self.snapshots = []
    
    def start_monitoring(self):
        """監視開始"""
        if not self.monitoring:
            tracemalloc.start()
            self.monitoring = True
            self.start_memory = self._get_memory_usage()
            self.peak_memory = self.start_memory
    
    def stop_monitoring(self) -> Dict[str, float]:
        """監視停止"""
        if self.monitoring:
            self.current_memory = self._get_memory_usage()
            if tracemalloc.is_tracing():
                tracemalloc.stop()
            self.monitoring = False
            
            return {
                "start_memory_mb": self.start_memory,
                "end_memory_mb": self.current_memory,
                "peak_memory_mb": self.peak_memory,
                "memory_diff_mb": self.current_memory - self.start_memory
            }
        return {}
    
    def take_snapshot(self, context: str = ""):
        """メモリスナップショット取得"""
        if self.monitoring:
            current = self._get_memory_usage()
            self.peak_memory = max(self.peak_memory, current)
            
            snapshot = {
                "timestamp": datetime.now(),
                "memory_mb": current,
                "context": context
            }
            self.snapshots.append(snapshot)
            return snapshot
        return None
    
    def _get_memory_usage(self) -> float:
        """現在のメモリ使用量を取得（MB）"""
        try:
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0


class CacheManager:
    """キャッシュ管理クラス"""
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.cache = {}
        self.access_times = {}
        self.creation_times = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """キャッシュから取得"""
        with self._lock:
            if key not in self.cache:
                return None
            
            # TTLチェック
            if self._is_expired(key):
                self.delete(key)
                return None
            
            self.access_times[key] = datetime.now()
            return self.cache[key]
    
    def set(self, key: str, value: Any) -> bool:
        """キャッシュに設定"""
        with self._lock:
            # サイズ制限チェック
            if len(self.cache) >= self.max_size and key not in self.cache:
                self._evict_lru()
            
            self.cache[key] = value
            now = datetime.now()
            self.access_times[key] = now
            self.creation_times[key] = now
            return True
    
    def delete(self, key: str) -> bool:
        """キャッシュから削除"""
        with self._lock:
            if key in self.cache:
                del self.cache[key]
                self.access_times.pop(key, None)
                self.creation_times.pop(key, None)
                return True
            return False
    
    def clear(self):
        """全キャッシュクリア"""
        with self._lock:
            self.cache.clear()
            self.access_times.clear()
            self.creation_times.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """キャッシュ統計を取得"""
        with self._lock:
            return {
                "size": len(self.cache),
                "max_size": self.max_size,
                "hit_rate": 0.0,  # 簡略化
                "memory_usage_estimate": sys.getsizeof(self.cache)
            }
    
    def _is_expired(self, key: str) -> bool:
        """期限切れか確認"""
        if key not in self.creation_times:
            return True
        
        age = (datetime.now() - self.creation_times[key]).total_seconds()
        return age > self.ttl_seconds
    
    def _evict_lru(self):
        """LRU削除"""
        if not self.access_times:
            return
        
        lru_key = min(self.access_times.keys(), key=lambda k: self.access_times[k])
        self.delete(lru_key)


class PerformanceOptimizer:
    """パフォーマンス最適化サービス"""
    
    def __init__(self, config: OptimizationConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        
        # 監視・最適化コンポーネント
        self.memory_monitor = MemoryMonitor()
        self.cache_manager = CacheManager()
        
        # パフォーマンス履歴
        self.performance_history: List[PerformanceMetrics] = []
        self.optimization_results: List[OptimizationResult] = []
        
        # 実行時統計
        self.execution_count = 0
        self.total_execution_time = 0.0
        self.gc_collections_count = 0
        
        # スレッドプール
        if config.enable_threading_optimization:
            self.thread_pool = ThreadPoolExecutor(
                max_workers=config.max_concurrent_operations,
                thread_name_prefix="optimizer"
            )
        else:
            self.thread_pool = None
    
    def monitor_execution(self, func: Callable):
        """実行監視デコレータ"""
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await self._monitor_async_execution(func, *args, **kwargs)
        
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            return self._monitor_sync_execution(func, *args, **kwargs)
        
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    
    async def _monitor_async_execution(self, func: Callable, *args, **kwargs) -> Any:
        """非同期実行監視"""
        start_time = time.time()
        context = f"{func.__name__}"
        
        # 監視開始
        self.memory_monitor.start_monitoring()
        before_metrics = self._capture_metrics(context)
        
        try:
            # 実行
            if self.config.execution_timeout_seconds > 0:
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.config.execution_timeout_seconds
                )
            else:
                result = await func(*args, **kwargs)
            
            return result
            
        finally:
            # 監視終了
            execution_time = time.time() - start_time
            after_metrics = self._capture_metrics(context, execution_time)
            
            self.memory_monitor.stop_monitoring()
            self._record_performance(before_metrics, after_metrics)
            
            # 最適化実行
            if self.config.level != OptimizationLevel.NONE:
                await self._perform_post_execution_optimization()
    
    def _monitor_sync_execution(self, func: Callable, *args, **kwargs) -> Any:
        """同期実行監視"""
        start_time = time.time()
        context = f"{func.__name__}"
        
        # 監視開始
        self.memory_monitor.start_monitoring()
        before_metrics = self._capture_metrics(context)
        
        try:
            result = func(*args, **kwargs)
            return result
            
        finally:
            # 監視終了
            execution_time = time.time() - start_time
            after_metrics = self._capture_metrics(context, execution_time)
            
            self.memory_monitor.stop_monitoring()
            self._record_performance(before_metrics, after_metrics)
    
    def _capture_metrics(self, context: str, execution_time: float = 0.0) -> PerformanceMetrics:
        """メトリクス取得"""
        try:
            process = psutil.Process()
            memory_info = process.memory_info()
            
            return PerformanceMetrics(
                timestamp=datetime.now(),
                execution_time=execution_time,
                memory_usage_mb=memory_info.rss / 1024 / 1024,
                peak_memory_mb=self.memory_monitor.peak_memory,
                cpu_percent=process.cpu_percent(),
                memory_percent=process.memory_percent(),
                gc_collections=sum(gc.get_stats()[i]['collections'] for i in range(len(gc.get_stats()))),
                active_threads=threading.active_count(),
                context=context
            )
        except Exception as e:
            self.logger.warning(f"メトリクス取得エラー: {e}")
            return PerformanceMetrics(
                timestamp=datetime.now(),
                execution_time=execution_time,
                memory_usage_mb=0.0,
                peak_memory_mb=0.0,
                cpu_percent=0.0,
                memory_percent=0.0,
                gc_collections=0,
                active_threads=0,
                context=context
            )
    
    def _record_performance(self, before: PerformanceMetrics, after: PerformanceMetrics):
        """パフォーマンス記録"""
        self.performance_history.append(after)
        self.execution_count += 1
        self.total_execution_time += after.execution_time
        
        # 履歴サイズ制限
        if len(self.performance_history) > 100:
            self.performance_history = self.performance_history[-50:]
    
    async def _perform_post_execution_optimization(self):
        """実行後最適化"""
        try:
            # ガベージコレクション最適化
            if self.config.enable_gc_optimization:
                await self._optimize_garbage_collection()
            
            # メモリ最適化
            if self.config.enable_memory_monitoring:
                await self._optimize_memory_usage()
            
            # キャッシュ最適化
            if self.config.enable_caching:
                await self._optimize_cache()
                
        except Exception as e:
            self.logger.warning(f"実行後最適化エラー: {e}")
    
    async def _optimize_garbage_collection(self) -> OptimizationResult:
        """ガベージコレクション最適化"""
        before_metrics = self._capture_metrics("gc_optimization")
        
        try:
            # 強制的なガベージコレクション
            collected = gc.collect()
            
            # より積極的な最適化
            if self.config.level == OptimizationLevel.AGGRESSIVE:
                for generation in range(3):
                    gc.collect(generation)
            
            after_metrics = self._capture_metrics("gc_optimization")
            
            result = OptimizationResult(
                success=True,
                optimization_type="garbage_collection",
                before_metrics=before_metrics,
                after_metrics=after_metrics,
                details={"objects_collected": collected}
            )
            
            self.optimization_results.append(result)
            return result
            
        except Exception as e:
            self.logger.error(f"GC最適化エラー: {e}")
            return OptimizationResult(
                success=False,
                optimization_type="garbage_collection",
                before_metrics=before_metrics,
                after_metrics=None
            )
    
    async def _optimize_memory_usage(self) -> OptimizationResult:
        """メモリ使用量最適化"""
        before_metrics = self._capture_metrics("memory_optimization")
        
        try:
            # メモリ閾値チェック
            if before_metrics.memory_usage_mb > self.config.memory_threshold_mb:
                # キャッシュクリア
                cache_size_before = len(self.cache_manager.cache)
                self.cache_manager.clear()
                
                # 履歴データクリア
                if len(self.performance_history) > 10:
                    self.performance_history = self.performance_history[-10:]
                
                # ガベージコレクション
                gc.collect()
            
            after_metrics = self._capture_metrics("memory_optimization")
            
            result = OptimizationResult(
                success=True,
                optimization_type="memory_usage",
                before_metrics=before_metrics,
                after_metrics=after_metrics,
                details={
                    "memory_threshold_mb": self.config.memory_threshold_mb,
                    "cache_cleared": cache_size_before if 'cache_size_before' in locals() else 0
                }
            )
            
            self.optimization_results.append(result)
            return result
            
        except Exception as e:
            self.logger.error(f"メモリ最適化エラー: {e}")
            return OptimizationResult(
                success=False,
                optimization_type="memory_usage",
                before_metrics=before_metrics,
                after_metrics=None
            )
    
    async def _optimize_cache(self) -> OptimizationResult:
        """キャッシュ最適化"""
        before_stats = self.cache_manager.get_stats()
        
        try:
            # 期限切れエントリの削除
            expired_keys = []
            for key in list(self.cache_manager.cache.keys()):
                if self.cache_manager._is_expired(key):
                    expired_keys.append(key)
            
            for key in expired_keys:
                self.cache_manager.delete(key)
            
            after_stats = self.cache_manager.get_stats()
            
            result = OptimizationResult(
                success=True,
                optimization_type="cache",
                before_metrics=None,
                after_metrics=None,
                details={
                    "expired_entries_removed": len(expired_keys),
                    "cache_size_before": before_stats["size"],
                    "cache_size_after": after_stats["size"]
                }
            )
            
            self.optimization_results.append(result)
            return result
            
        except Exception as e:
            self.logger.error(f"キャッシュ最適化エラー: {e}")
            return OptimizationResult(
                success=False,
                optimization_type="cache",
                before_metrics=None,
                after_metrics=None
            )
    
    def cache_result(self, key: str, value: Any, ttl_seconds: Optional[int] = None):
        """結果をキャッシュ"""
        if self.config.enable_caching:
            if ttl_seconds:
                # TTL指定の場合は一時的なキャッシュマネージャーを使用
                temp_cache = CacheManager(ttl_seconds=ttl_seconds)
                temp_cache.set(key, value)
            else:
                self.cache_manager.set(key, value)
    
    def get_cached_result(self, key: str) -> Optional[Any]:
        """キャッシュから結果を取得"""
        if self.config.enable_caching:
            return self.cache_manager.get(key)
        return None
    
    async def execute_concurrent_operations(self, operations: List[Callable]) -> List[Any]:
        """並行処理実行"""
        if not self.config.enable_threading_optimization or not self.thread_pool:
            # 順次実行
            results = []
            for op in operations:
                if asyncio.iscoroutinefunction(op):
                    result = await op()
                else:
                    result = op()
                results.append(result)
            return results
        
        # 並行実行
        futures = []
        for op in operations:
            if asyncio.iscoroutinefunction(op):
                # 非同期関数は直接実行
                futures.append(asyncio.create_task(op()))
            else:
                # 同期関数はスレッドプールで実行
                future = self.thread_pool.submit(op)
                futures.append(future)
        
        # 結果収集
        results = []
        for future in futures:
            if asyncio.iscoroutinefunction(operations[futures.index(future)]):
                result = await future
            else:
                result = future.result()
            results.append(result)
        
        return results
    
    def get_performance_summary(self) -> Dict[str, Any]:
        """パフォーマンスサマリーを取得"""
        if not self.performance_history:
            return {"message": "パフォーマンスデータなし"}
        
        recent_metrics = self.performance_history[-10:]  # 直近10件
        
        avg_execution_time = sum(m.execution_time for m in recent_metrics) / len(recent_metrics)
        avg_memory_usage = sum(m.memory_usage_mb for m in recent_metrics) / len(recent_metrics)
        peak_memory = max(m.peak_memory_mb for m in recent_metrics)
        
        return {
            "total_executions": self.execution_count,
            "total_execution_time": self.total_execution_time,
            "average_execution_time": avg_execution_time,
            "average_memory_usage_mb": avg_memory_usage,
            "peak_memory_usage_mb": peak_memory,
            "optimization_count": len(self.optimization_results),
            "cache_stats": self.cache_manager.get_stats(),
            "config": self.config.to_dict()
        }
    
    def cleanup(self):
        """リソースクリーンアップ"""
        try:
            if self.thread_pool:
                self.thread_pool.shutdown(wait=True)
            
            self.cache_manager.clear()
            
            if self.memory_monitor.monitoring:
                self.memory_monitor.stop_monitoring()
                
        except Exception as e:
            self.logger.error(f"クリーンアップエラー: {e}")


# グローバル最適化インスタンス（Lambda環境での再利用）
_global_optimizer: Optional[PerformanceOptimizer] = None


def get_optimizer(config: Optional[OptimizationConfig] = None) -> PerformanceOptimizer:
    """グローバル最適化インスタンスを取得"""
    global _global_optimizer
    
    if _global_optimizer is None:
        if config is None:
            config = OptimizationConfig()
        _global_optimizer = PerformanceOptimizer(config)
    
    return _global_optimizer


def optimize_execution(func: Callable):
    """実行最適化デコレータ"""
    optimizer = get_optimizer()
    return optimizer.monitor_execution(func)