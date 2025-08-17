# -*- coding: utf-8 -*-
"""
リトライポリシーサービスの単体テスト
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.services.retry_policy import (
    RetryPolicyManager, RetryPolicy, BackoffStrategy, RetryCondition,
    RetryAttempt, RetryResult, CircuitBreakerState, CircuitBreakerInfo
)
from src.services.error_handler import ErrorHandler, ErrorInfo, ErrorCategory, ErrorSeverity


class TestRetryPolicy:
    """リトライポリシーのテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.policy = RetryPolicy(
            name="test_policy",
            max_attempts=3,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            initial_delay=1.0,
            max_delay=30.0,
            retry_condition=RetryCondition.ALL_EXCEPTIONS
        )
    
    def test_policy_creation(self):
        """ポリシー作成のテスト"""
        assert self.policy.name == "test_policy"
        assert self.policy.max_attempts == 3
        assert self.policy.backoff_strategy == BackoffStrategy.EXPONENTIAL
        assert self.policy.initial_delay == 1.0
        assert self.policy.max_delay == 30.0
        assert self.policy.retry_condition == RetryCondition.ALL_EXCEPTIONS
    
    def test_is_retryable_all_exceptions(self):
        """すべての例外がリトライ可能かのテスト"""
        policy = RetryPolicy(
            name="all_policy",
            retry_condition=RetryCondition.ALL_EXCEPTIONS
        )
        
        assert policy.is_retryable(ValueError("test"))
        assert policy.is_retryable(ConnectionError("test"))
        assert policy.is_retryable(Exception("test"))
    
    def test_is_retryable_specific_exceptions(self):
        """特定の例外のリトライ可能性テスト"""
        policy = RetryPolicy(
            name="specific_policy",
            retry_condition=RetryCondition.SPECIFIC_EXCEPTIONS,
            retryable_exceptions=[ValueError, TypeError]
        )
        
        assert policy.is_retryable(ValueError("test"))
        assert policy.is_retryable(TypeError("test"))
        assert not policy.is_retryable(ConnectionError("test"))
    
    def test_is_retryable_categories(self):
        """カテゴリベースのリトライ可能性テスト"""
        policy = RetryPolicy(
            name="category_policy",
            retry_condition=RetryCondition.SPECIFIC_CATEGORIES,
            retryable_categories=[ErrorCategory.NETWORK, ErrorCategory.TIMEOUT]
        )
        
        # ネットワークエラー
        error_info = ErrorInfo(
            error_id="test",
            timestamp=datetime.now(),
            exception=ConnectionError("Network error"),
            error_type="ConnectionError",
            error_message="Network error",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM
        )
        assert policy.is_retryable(ConnectionError("test"), error_info)
        
        # データ検証エラー（リトライ対象外）
        error_info.category = ErrorCategory.DATA_VALIDATION
        assert not policy.is_retryable(ValueError("test"), error_info)
    
    def test_calculate_delay_exponential(self):
        """指数バックオフ遅延計算のテスト"""
        policy = RetryPolicy(
            name="exp_policy",
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            initial_delay=1.0,
            multiplier=2.0,
            jitter=False
        )
        
        assert policy.calculate_delay(1) == 1.0
        assert policy.calculate_delay(2) == 2.0
        assert policy.calculate_delay(3) == 4.0
        assert policy.calculate_delay(4) == 8.0
    
    def test_calculate_delay_linear(self):
        """線形バックオフ遅延計算のテスト"""
        policy = RetryPolicy(
            name="linear_policy",
            backoff_strategy=BackoffStrategy.LINEAR,
            initial_delay=2.0,
            jitter=False
        )
        
        assert policy.calculate_delay(1) == 2.0
        assert policy.calculate_delay(2) == 4.0
        assert policy.calculate_delay(3) == 6.0
    
    def test_calculate_delay_fibonacci(self):
        """フィボナッチバックオフ遅延計算のテスト"""
        policy = RetryPolicy(
            name="fib_policy",
            backoff_strategy=BackoffStrategy.FIBONACCI,
            initial_delay=1.0,
            jitter=False
        )
        
        assert policy.calculate_delay(1) == 1.0
        assert policy.calculate_delay(2) == 1.0
        assert policy.calculate_delay(3) == 2.0
        assert policy.calculate_delay(4) == 3.0
        assert policy.calculate_delay(5) == 5.0
    
    def test_calculate_delay_max_limit(self):
        """最大遅延時間制限のテスト"""
        policy = RetryPolicy(
            name="limit_policy",
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            initial_delay=1.0,
            max_delay=5.0,
            jitter=False
        )
        
        assert policy.calculate_delay(1) == 1.0
        assert policy.calculate_delay(2) == 2.0
        assert policy.calculate_delay(3) == 4.0
        assert policy.calculate_delay(4) == 5.0  # 最大値制限
        assert policy.calculate_delay(5) == 5.0
    
    def test_to_dict(self):
        """辞書変換のテスト"""
        result = self.policy.to_dict()
        
        assert result["name"] == "test_policy"
        assert result["max_attempts"] == 3
        assert result["backoff_strategy"] == "exponential"
        assert result["initial_delay"] == 1.0
        assert result["retry_condition"] == "all_exceptions"


class TestRetryAttempt:
    """リトライ試行のテストクラス"""
    
    def test_retry_attempt_creation(self):
        """リトライ試行作成のテスト"""
        timestamp = datetime.now()
        exception = ValueError("Test error")
        
        attempt = RetryAttempt(
            attempt_number=2,
            timestamp=timestamp,
            exception=exception,
            delay=1.5,
            total_elapsed=3.2
        )
        
        assert attempt.attempt_number == 2
        assert attempt.timestamp == timestamp
        assert attempt.exception == exception
        assert attempt.delay == 1.5
        assert attempt.total_elapsed == 3.2
    
    def test_to_dict(self):
        """辞書変換のテスト"""
        timestamp = datetime.now()
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=timestamp,
            exception=ValueError("Test"),
            delay=1.0,
            total_elapsed=2.0
        )
        
        result = attempt.to_dict()
        
        assert result["attempt_number"] == 1
        assert result["timestamp"] == timestamp.isoformat()
        assert result["exception_type"] == "ValueError"
        assert result["exception_message"] == "Test"
        assert result["delay"] == 1.0
        assert result["total_elapsed"] == 2.0


class TestRetryResult:
    """リトライ結果のテストクラス"""
    
    def test_retry_result_success(self):
        """成功結果のテスト"""
        result = RetryResult(
            success=True,
            final_result="success_value",
            total_attempts=2,
            total_elapsed=3.5,
            policy_used="test_policy"
        )
        
        assert result.success is True
        assert result.final_result == "success_value"
        assert result.total_attempts == 2
        assert result.failure_rate == 0.5  # 1回失敗、1回成功
    
    def test_retry_result_failure(self):
        """失敗結果のテスト"""
        result = RetryResult(
            success=False,
            final_exception=ValueError("Final error"),
            total_attempts=3,
            total_elapsed=7.2,
            policy_used="test_policy"
        )
        
        assert result.success is False
        assert isinstance(result.final_exception, ValueError)
        assert result.total_attempts == 3
        assert result.failure_rate == 1.0  # すべて失敗
    
    def test_to_dict(self):
        """辞書変換のテスト"""
        result = RetryResult(
            success=False,
            final_exception=ValueError("Error"),
            total_attempts=2,
            total_elapsed=5.0,
            policy_used="test_policy"
        )
        
        result_dict = result.to_dict()
        
        assert result_dict["success"] is False
        assert result_dict["total_attempts"] == 2
        assert result_dict["total_elapsed"] == 5.0
        assert result_dict["failure_rate"] == 1.0
        assert result_dict["policy_used"] == "test_policy"
        assert result_dict["final_exception"]["type"] == "ValueError"


class TestCircuitBreakerInfo:
    """サーキットブレーカー情報のテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.circuit_breaker = CircuitBreakerInfo()
    
    def test_initial_state(self):
        """初期状態のテスト"""
        assert self.circuit_breaker.state == CircuitBreakerState.CLOSED
        assert self.circuit_breaker.failure_count == 0
        assert self.circuit_breaker.total_requests == 0
    
    def test_should_allow_request_closed(self):
        """CLOSED状態でのリクエスト許可テスト"""
        assert self.circuit_breaker.should_allow_request(threshold=3, timeout=60)
    
    def test_record_failure(self):
        """失敗記録のテスト"""
        threshold = 3
        
        # 失敗を記録
        self.circuit_breaker.record_failure(threshold)
        assert self.circuit_breaker.failure_count == 1
        assert self.circuit_breaker.state == CircuitBreakerState.CLOSED
        
        self.circuit_breaker.record_failure(threshold)
        assert self.circuit_breaker.failure_count == 2
        assert self.circuit_breaker.state == CircuitBreakerState.CLOSED
        
        # 閾値到達でOPEN状態に
        self.circuit_breaker.record_failure(threshold)
        assert self.circuit_breaker.failure_count == 3
        assert self.circuit_breaker.state == CircuitBreakerState.OPEN
    
    def test_record_success(self):
        """成功記録のテスト"""
        # 失敗を記録してからリセット
        self.circuit_breaker.record_failure(3)
        self.circuit_breaker.record_failure(3)
        
        assert self.circuit_breaker.failure_count == 2
        
        # 成功でリセット
        self.circuit_breaker.record_success()
        assert self.circuit_breaker.failure_count == 0
        assert self.circuit_breaker.state == CircuitBreakerState.CLOSED
    
    def test_half_open_state(self):
        """HALF_OPEN状態のテスト"""
        # OPEN状態にする
        for _ in range(3):
            self.circuit_breaker.record_failure(3)
        
        assert self.circuit_breaker.state == CircuitBreakerState.OPEN
        
        # タイムアウト時間を過去に設定
        self.circuit_breaker.last_failure_time = datetime.now() - timedelta(seconds=61)
        
        # リクエスト許可でHALF_OPEN状態に
        allowed = self.circuit_breaker.should_allow_request(threshold=3, timeout=60)
        assert allowed
        assert self.circuit_breaker.state == CircuitBreakerState.HALF_OPEN


class TestRetryPolicyManager:
    """リトライポリシーマネージャーのテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.mock_error_handler = Mock(spec=ErrorHandler)
        self.mock_error_handler.handle_error = AsyncMock()
        self.manager = RetryPolicyManager(self.mock_error_handler)
    
    def test_manager_initialization(self):
        """マネージャー初期化のテスト"""
        assert "network_errors" in self.manager.policies
        assert "api_errors" in self.manager.policies
        assert "general_errors" in self.manager.policies
        assert "critical_operations" in self.manager.policies
    
    def test_add_policy(self):
        """ポリシー追加のテスト"""
        custom_policy = RetryPolicy(
            name="custom_policy",
            max_attempts=5,
            backoff_strategy=BackoffStrategy.LINEAR
        )
        
        self.manager.add_policy(custom_policy)
        assert "custom_policy" in self.manager.policies
        assert self.manager.get_policy("custom_policy") == custom_policy
    
    def test_get_policy(self):
        """ポリシー取得のテスト"""
        policy = self.manager.get_policy("network_errors")
        assert policy is not None
        assert policy.name == "network_errors"
        
        # 存在しないポリシー
        assert self.manager.get_policy("nonexistent") is None
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_success(self):
        """リトライ付き実行（成功）のテスト"""
        async def successful_function():
            return "success"
        
        result = await self.manager.execute_with_retry(
            successful_function,
            "general_errors"
        )
        
        assert result.success is True
        assert result.final_result == "success"
        assert result.total_attempts == 1
        assert result.policy_used == "general_errors"
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_failure_then_success(self):
        """リトライ付き実行（失敗後成功）のテスト"""
        call_count = 0
        
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Network error")
            return "success"
        
        # すべての例外をリトライするポリシーを使用
        result = await self.manager.execute_with_retry(
            flaky_function,
            "critical_operations"
        )
        
        assert result.success is True
        assert result.final_result == "success"
        assert result.total_attempts == 3
        assert len(result.attempts_history) == 2  # 失敗した試行
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_max_attempts_reached(self):
        """リトライ付き実行（最大試行数到達）のテスト"""
        async def always_failing_function():
            raise ValueError("Always fails")
        
        result = await self.manager.execute_with_retry(
            always_failing_function,
            "critical_operations"
        )
        
        assert result.success is False
        assert isinstance(result.final_exception, ValueError)
        assert result.total_attempts == 5  # critical_operationsの最大試行数
        assert len(result.attempts_history) == 4  # 失敗した試行数（最後の試行は含まれない）
    
    @pytest.mark.asyncio
    async def test_execute_with_retry_non_retryable(self):
        """リトライ付き実行（リトライ不可）のテスト"""
        async def critical_function():
            raise MemoryError("Critical error")
        
        # 重要度ベースのポリシーでメモリエラーはリトライ対象外
        result = await self.manager.execute_with_retry(
            critical_function,
            "general_errors"
        )
        
        assert result.success is False
        assert isinstance(result.final_exception, MemoryError)
        assert result.total_attempts == 1
    
    def test_circuit_breaker_functionality(self):
        """サーキットブレーカー機能のテスト"""
        circuit_key = "test_circuit"
        policy = self.manager.get_policy("api_errors")
        
        # 初期状態チェック
        assert self.manager._check_circuit_breaker(circuit_key, policy)
        
        # 失敗を記録
        for _ in range(5):
            self.manager._record_circuit_breaker_failure(circuit_key, policy)
        
        # OPEN状態になりリクエスト拒否
        assert not self.manager._check_circuit_breaker(circuit_key, policy)
    
    def test_circuit_breaker_reset(self):
        """サーキットブレーカーリセットのテスト"""
        circuit_key = "test_circuit"
        policy = self.manager.get_policy("api_errors")
        
        # 失敗を記録してOPEN状態に
        for _ in range(5):
            self.manager._record_circuit_breaker_failure(circuit_key, policy)
        
        assert not self.manager._check_circuit_breaker(circuit_key, policy)
        
        # リセット
        reset_result = self.manager.reset_circuit_breaker(circuit_key)
        assert reset_result is True
        assert self.manager._check_circuit_breaker(circuit_key, policy)
        
        # 存在しないキーのリセット
        assert self.manager.reset_circuit_breaker("nonexistent") is False
    
    @pytest.mark.asyncio
    async def test_retry_decorator(self):
        """リトライデコレータのテスト"""
        call_count = 0
        
        @self.manager.retry_with_policy("critical_operations")
        async def decorated_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Network error")
            return "decorated_success"
        
        result = await decorated_function()
        assert result == "decorated_success"
        assert call_count == 2
    
    def test_get_retry_statistics(self):
        """リトライ統計取得のテスト"""
        # 統計データを追加
        result1 = RetryResult(
            success=True,
            total_attempts=2,
            total_elapsed=3.0,
            policy_used="test_policy"
        )
        result2 = RetryResult(
            success=False,
            final_exception=Exception("Test"),
            total_attempts=3,
            total_elapsed=5.0,
            policy_used="test_policy"
        )
        
        self.manager._record_retry_statistics("test_policy", result1)
        self.manager._record_retry_statistics("test_policy", result2)
        
        stats = self.manager.get_retry_statistics()
        
        assert "test_policy" in stats
        policy_stats = stats["test_policy"]
        assert policy_stats["total_executions"] == 2
        assert policy_stats["successful_executions"] == 1
        assert policy_stats["failed_executions"] == 1
        assert policy_stats["success_rate"] == 0.5
    
    def test_get_circuit_breaker_status(self):
        """サーキットブレーカー状態取得のテスト"""
        circuit_key = "test_circuit"
        
        # サーキットブレーカー情報を追加
        self.manager.circuit_breakers[circuit_key] = CircuitBreakerInfo(
            state=CircuitBreakerState.OPEN,
            failure_count=5,
            total_requests=10
        )
        
        status = self.manager.get_circuit_breaker_status()
        
        assert circuit_key in status
        circuit_status = status[circuit_key]
        assert circuit_status["state"] == "open"
        assert circuit_status["failure_count"] == 5
        assert circuit_status["total_requests"] == 10


if __name__ == "__main__":
    pytest.main([__file__])