# -*- coding: utf-8 -*-
"""
パフォーマンスオプティマイザーの単体テスト
"""

import pytest
import asyncio
import gc
import time
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from src.services.performance_optimizer import (
    PerformanceOptimizer, OptimizationLevel, ResourceType, PerformanceMetrics,
    OptimizationConfig, OptimizationResult, MemoryMonitor, CacheManager,
    get_optimizer, optimize_execution
)


class TestOptimizationLevel:
    """最適化レベルのテストクラス"""
    
    def test_optimization_level_values(self):
        """最適化レベル値のテスト"""
        assert OptimizationLevel.NONE.value == "none"
        assert OptimizationLevel.BASIC.value == "basic"
        assert OptimizationLevel.STANDARD.value == "standard"
        assert OptimizationLevel.AGGRESSIVE.value == "aggressive"
    
    def test_optimization_level_display_names(self):
        """最適化レベル表示名のテスト"""
        assert OptimizationLevel.NONE.display_name == "最適化なし"
        assert OptimizationLevel.BASIC.display_name == "基本"
        assert OptimizationLevel.STANDARD.display_name == "標準"
        assert OptimizationLevel.AGGRESSIVE.display_name == "積極的"


class TestResourceType:
    """リソースタイプのテストクラス"""
    
    def test_resource_type_values(self):
        """リソースタイプ値のテスト"""
        assert ResourceType.CPU.value == "cpu"
        assert ResourceType.MEMORY.value == "memory"
        assert ResourceType.NETWORK.value == "network"
        assert ResourceType.DISK.value == "disk"
    
    def test_resource_type_display_names(self):
        """リソースタイプ表示名のテスト"""
        assert ResourceType.CPU.display_name == "CPU"
        assert ResourceType.MEMORY.display_name == "メモリ"
        assert ResourceType.NETWORK.display_name == "ネットワーク"
        assert ResourceType.DISK.display_name == "ディスク"


class TestPerformanceMetrics:
    """パフォーマンスメトリクスのテストクラス"""
    
    def test_performance_metrics_creation(self):
        """パフォーマンスメトリクス作成のテスト"""
        start_time = datetime.now()
        
        metrics = PerformanceMetrics(
            start_time=start_time,
            end_time=start_time,
            duration_seconds=1.5,
            memory_usage_mb=256.0,
            peak_memory_mb=512.0,
            cpu_usage_percent=45.0,
            function_name="test_function",
            optimization_level=OptimizationLevel.STANDARD
        )
        
        assert metrics.start_time == start_time
        assert metrics.duration_seconds == 1.5
        assert metrics.memory_usage_mb == 256.0
        assert metrics.peak_memory_mb == 512.0
        assert metrics.cpu_usage_percent == 45.0
        assert metrics.function_name == "test_function"
        assert metrics.optimization_level == OptimizationLevel.STANDARD
    
    def test_performance_metrics_to_dict(self):
        """パフォーマンスメトリクス辞書変換のテスト"""
        start_time = datetime.now()
        end_time = datetime.now()
        
        metrics = PerformanceMetrics(
            start_time=start_time,
            end_time=end_time,
            duration_seconds=2.0,
            memory_usage_mb=128.0,
            function_name="test_func"
        )
        
        result = metrics.to_dict()
        
        assert result["start_time"] == start_time.isoformat()
        assert result["end_time"] == end_time.isoformat()
        assert result["duration_seconds"] == 2.0
        assert result["memory_usage_mb"] == 128.0
        assert result["function_name"] == "test_func"


class TestOptimizationConfig:
    """最適化設定のテストクラス"""
    
    def test_optimization_config_creation(self):
        """最適化設定作成のテスト"""
        config = OptimizationConfig(
            level=OptimizationLevel.AGGRESSIVE,
            enable_memory_monitoring=True,
            enable_gc_optimization=True,
            enable_caching=True,
            cache_size_limit=1000,
            memory_threshold_mb=512.0,
            gc_threshold=0.8
        )
        
        assert config.level == OptimizationLevel.AGGRESSIVE
        assert config.enable_memory_monitoring is True
        assert config.enable_gc_optimization is True
        assert config.enable_caching is True
        assert config.cache_size_limit == 1000
        assert config.memory_threshold_mb == 512.0
        assert config.gc_threshold == 0.8
    
    def test_optimization_config_defaults(self):
        """最適化設定デフォルト値のテスト"""
        config = OptimizationConfig()
        
        assert config.level == OptimizationLevel.STANDARD
        assert config.enable_memory_monitoring is True
        assert config.enable_gc_optimization is True
        assert config.enable_caching is True
        assert config.cache_size_limit == 1000
        assert config.memory_threshold_mb == 256.0
        assert config.gc_threshold == 0.7


class TestOptimizationResult:
    """最適化結果のテストクラス"""
    
    def test_optimization_result_creation(self):
        """最適化結果作成のテスト"""
        start_time = datetime.now()
        
        metrics = PerformanceMetrics(
            start_time=start_time,
            end_time=start_time,
            duration_seconds=1.0,
            memory_usage_mb=100.0,
            function_name="test"
        )
        
        result = OptimizationResult(
            success=True,
            metrics=metrics,
            optimizations_applied=["gc_collection", "cache_cleanup"],
            memory_freed_mb=50.0,
            performance_improvement_percent=15.0
        )
        
        assert result.success is True
        assert result.metrics == metrics
        assert result.optimizations_applied == ["gc_collection", "cache_cleanup"]
        assert result.memory_freed_mb == 50.0
        assert result.performance_improvement_percent == 15.0
    
    def test_optimization_result_to_dict(self):
        """最適化結果辞書変換のテスト"""
        metrics = PerformanceMetrics(
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=1.0,
            memory_usage_mb=100.0,
            function_name="test"
        )
        
        result = OptimizationResult(
            success=True,
            metrics=metrics,
            optimizations_applied=["optimization1"],
            memory_freed_mb=25.0
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["success"] is True
        assert "metrics" in result_dict
        assert result_dict["optimizations_applied"] == ["optimization1"]
        assert result_dict["memory_freed_mb"] == 25.0


class TestMemoryMonitor:
    """メモリモニターのテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.monitor = MemoryMonitor()
    
    def test_memory_monitor_initialization(self):
        """メモリモニター初期化のテスト"""
        assert self.monitor.initial_memory == 0.0
        assert self.monitor.peak_memory == 0.0
        assert self.monitor.current_memory == 0.0
    
    def test_start_monitoring(self):
        """監視開始のテスト"""
        self.monitor.start_monitoring()
        
        assert self.monitor.initial_memory > 0.0
        assert self.monitor.peak_memory > 0.0
        assert self.monitor.current_memory > 0.0
        assert self.monitor.is_monitoring is True
    
    def test_stop_monitoring(self):
        """監視停止のテスト"""
        self.monitor.start_monitoring()
        assert self.monitor.is_monitoring is True
        
        self.monitor.stop_monitoring()
        assert self.monitor.is_monitoring is False
    
    def test_update_memory_usage(self):
        """メモリ使用量更新のテスト"""
        self.monitor.start_monitoring()
        initial_peak = self.monitor.peak_memory
        
        # メモリ使用量を更新
        self.monitor.update_memory_usage()
        
        # ピークメモリが更新される可能性がある
        assert self.monitor.current_memory > 0.0
    
    def test_get_memory_usage_mb(self):
        """メモリ使用量取得のテスト"""
        self.monitor.start_monitoring()
        
        usage = self.monitor.get_memory_usage_mb()
        assert usage > 0.0
    
    def test_get_peak_memory_mb(self):
        """ピークメモリ取得のテスト"""
        self.monitor.start_monitoring()
        self.monitor.update_memory_usage()
        
        peak = self.monitor.get_peak_memory_mb()
        assert peak > 0.0
    
    def test_memory_freed_calculation(self):
        """解放メモリ計算のテスト"""
        self.monitor.start_monitoring()
        initial = self.monitor.current_memory
        
        # ガベージコレクション実行（メモリ解放をシミュレート）
        import gc
        gc.collect()
        
        self.monitor.update_memory_usage()
        freed = self.monitor.get_memory_freed_mb()
        
        # 解放されたメモリは非負
        assert freed >= 0.0


class TestCacheManager:
    """キャッシュマネージャーのテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.cache_manager = CacheManager(max_size=3)
    
    def test_cache_manager_initialization(self):
        """キャッシュマネージャー初期化のテスト"""
        assert self.cache_manager.max_size == 3
        assert len(self.cache_manager.cache) == 0
        assert self.cache_manager.hits == 0
        assert self.cache_manager.misses == 0
    
    def test_cache_set_and_get(self):
        """キャッシュ設定と取得のテスト"""
        self.cache_manager.set("key1", "value1")
        
        # ヒット
        value = self.cache_manager.get("key1")
        assert value == "value1"
        assert self.cache_manager.hits == 1
        assert self.cache_manager.misses == 0
        
        # ミス
        value = self.cache_manager.get("nonexistent")
        assert value is None
        assert self.cache_manager.hits == 1
        assert self.cache_manager.misses == 1
    
    def test_cache_eviction(self):
        """キャッシュ退避のテスト"""
        # 最大サイズまで追加
        self.cache_manager.set("key1", "value1")
        self.cache_manager.set("key2", "value2")
        self.cache_manager.set("key3", "value3")
        
        assert len(self.cache_manager.cache) == 3
        
        # 最大サイズを超えた場合、古いエントリが削除される
        self.cache_manager.set("key4", "value4")
        
        assert len(self.cache_manager.cache) == 3
        assert "key1" not in self.cache_manager.cache  # LRUで削除
        assert "key4" in self.cache_manager.cache
    
    def test_cache_clear(self):
        """キャッシュクリアのテスト"""
        self.cache_manager.set("key1", "value1")
        self.cache_manager.set("key2", "value2")
        
        assert len(self.cache_manager.cache) == 2
        
        self.cache_manager.clear()
        
        assert len(self.cache_manager.cache) == 0
    
    def test_cache_hit_rate(self):
        """キャッシュヒット率のテスト"""
        # 初期状態
        assert self.cache_manager.get_hit_rate() == 0.0
        
        # データを追加
        self.cache_manager.set("key1", "value1")
        
        # ヒットとミス
        self.cache_manager.get("key1")  # ヒット
        self.cache_manager.get("key2")  # ミス
        
        # ヒット率 = 1 / (1 + 1) = 0.5
        assert self.cache_manager.get_hit_rate() == 0.5
    
    def test_cache_size(self):
        """キャッシュサイズのテスト"""
        assert self.cache_manager.size() == 0
        
        self.cache_manager.set("key1", "value1")
        assert self.cache_manager.size() == 1
        
        self.cache_manager.set("key2", "value2")
        assert self.cache_manager.size() == 2
    
    def test_cache_statistics(self):
        """キャッシュ統計のテスト"""
        self.cache_manager.set("key1", "value1")
        self.cache_manager.get("key1")  # ヒット
        self.cache_manager.get("key2")  # ミス
        
        stats = self.cache_manager.get_statistics()
        
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
        assert stats["size"] == 1
        assert stats["max_size"] == 3


class TestPerformanceOptimizer:
    """パフォーマンスオプティマイザーのテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        config = OptimizationConfig(
            level=OptimizationLevel.STANDARD,
            enable_memory_monitoring=True,
            enable_gc_optimization=True,
            enable_caching=True
        )
        self.optimizer = PerformanceOptimizer(config)
    
    def test_optimizer_initialization(self):
        """オプティマイザー初期化のテスト"""
        assert self.optimizer.config.level == OptimizationLevel.STANDARD
        assert isinstance(self.optimizer.memory_monitor, MemoryMonitor)
        assert isinstance(self.optimizer.cache_manager, CacheManager)
        assert len(self.optimizer.metrics_history) == 0
    
    @pytest.mark.asyncio
    async def test_optimize_execution_async_function(self):
        """非同期関数の最適化実行のテスト"""
        async def test_function(x, y):
            await asyncio.sleep(0.01)  # 短い遅延
            return x + y
        
        result = await self.optimizer.optimize_execution(
            test_function,
            args=(2, 3),
            kwargs={}
        )
        
        assert result.success is True
        assert result.metrics.function_name == "test_function"
        assert result.metrics.duration_seconds > 0
        assert result.metrics.memory_usage_mb > 0
        
        # 関数の戻り値は結果に含まれない（最適化結果のみ）
        assert hasattr(result, 'function_result') is False
    
    @pytest.mark.asyncio
    async def test_optimize_execution_sync_function(self):
        """同期関数の最適化実行のテスト"""
        def test_function(x, y):
            time.sleep(0.01)  # 短い遅延
            return x * y
        
        result = await self.optimizer.optimize_execution(
            test_function,
            args=(4, 5),
            kwargs={}
        )
        
        assert result.success is True
        assert result.metrics.function_name == "test_function"
        assert result.metrics.duration_seconds > 0
    
    def test_pre_execution_optimizations(self):
        """実行前最適化のテスト"""
        with patch.object(self.optimizer, '_optimize_memory') as mock_memory:
            with patch.object(self.optimizer, '_optimize_gc') as mock_gc:
                optimizations = self.optimizer._apply_pre_execution_optimizations()
                
                # 設定に応じて最適化が呼ばれる
                if self.optimizer.config.enable_memory_monitoring:
                    mock_memory.assert_called_once()
                if self.optimizer.config.enable_gc_optimization:
                    mock_gc.assert_called_once()
                
                assert isinstance(optimizations, list)
    
    def test_post_execution_optimizations(self):
        """実行後最適化のテスト"""
        with patch.object(self.optimizer, '_cleanup_cache') as mock_cache:
            with patch.object(self.optimizer, '_optimize_gc') as mock_gc:
                optimizations = self.optimizer._apply_post_execution_optimizations()
                
                # 設定に応じてクリーンアップが呼ばれる
                if self.optimizer.config.enable_caching:
                    mock_cache.assert_called_once()
                if self.optimizer.config.enable_gc_optimization:
                    mock_gc.assert_called_once()
                
                assert isinstance(optimizations, list)
    
    def test_memory_optimization(self):
        """メモリ最適化のテスト"""
        initial_memory = self.optimizer.memory_monitor.get_memory_usage_mb()
        
        # メモリ最適化実行
        self.optimizer._optimize_memory()
        
        # メモリ監視が開始されている
        assert self.optimizer.memory_monitor.is_monitoring
    
    def test_gc_optimization(self):
        """ガベージコレクション最適化のテスト"""
        # GC最適化実行
        freed = self.optimizer._optimize_gc()
        
        # 解放されたメモリは非負
        assert freed >= 0
    
    def test_cache_cleanup(self):
        """キャッシュクリーンアップのテスト"""
        # キャッシュにデータを追加
        self.optimizer.cache_manager.set("test_key", "test_value")
        assert self.optimizer.cache_manager.size() == 1
        
        # 閾値を低く設定してクリーンアップを強制
        self.optimizer.config.cache_cleanup_threshold = 0.0
        
        cleaned = self.optimizer._cleanup_cache()
        
        # クリーンアップが実行される
        assert cleaned >= 0
    
    def test_get_optimization_metrics(self):
        """最適化メトリクス取得のテスト"""
        # テストメトリクスを追加
        metrics = PerformanceMetrics(
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=1.0,
            memory_usage_mb=100.0,
            function_name="test"
        )
        self.optimizer.metrics_history.append(metrics)
        
        summary = self.optimizer.get_optimization_metrics()
        
        assert summary["total_optimizations"] == 1
        assert summary["average_duration"] == 1.0
        assert summary["average_memory_usage"] == 100.0
        assert "cache_statistics" in summary
    
    def test_clear_metrics_history(self):
        """メトリクス履歴クリアのテスト"""
        # テストメトリクスを追加
        metrics = PerformanceMetrics(
            start_time=datetime.now(),
            end_time=datetime.now(),
            duration_seconds=1.0,
            memory_usage_mb=100.0,
            function_name="test"
        )
        self.optimizer.metrics_history.append(metrics)
        
        assert len(self.optimizer.metrics_history) == 1
        
        # クリア実行
        self.optimizer.clear_metrics_history()
        
        assert len(self.optimizer.metrics_history) == 0


class TestGlobalFunctions:
    """グローバル関数のテストクラス"""
    
    def test_get_optimizer(self):
        """グローバルオプティマイザー取得のテスト"""
        optimizer1 = get_optimizer()
        optimizer2 = get_optimizer()
        
        # シングルトンパターン
        assert optimizer1 is optimizer2
        assert isinstance(optimizer1, PerformanceOptimizer)
    
    @pytest.mark.asyncio
    async def test_optimize_execution_decorator(self):
        """最適化実行デコレータのテスト"""
        @optimize_execution
        async def test_decorated_function(x, y):
            await asyncio.sleep(0.01)
            return x + y
        
        result = await test_decorated_function(2, 3)
        
        # デコレータは関数の戻り値を返す
        assert result == 5
        
        # グローバルオプティマイザーのメトリクス履歴に記録される
        optimizer = get_optimizer()
        assert len(optimizer.metrics_history) > 0
    
    @pytest.mark.asyncio
    async def test_optimize_execution_decorator_sync(self):
        """最適化実行デコレータ（同期関数）のテスト"""
        @optimize_execution
        def test_decorated_sync_function(x, y):
            time.sleep(0.01)
            return x * y
        
        # 同期関数でもデコレータが動作する
        result = test_decorated_sync_function(3, 4)
        assert result == 12


if __name__ == "__main__":
    pytest.main([__file__])