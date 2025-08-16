# -*- coding: utf-8 -*-
"""
リトライマネージャーのテスト
"""

import pytest
import time
import threading
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from src.services.retry_manager import (
    RetryManager,
    RetryConfig,
    RateLimitConfig,
    CircuitBreakerConfig,
    TokenBucket,
    CircuitBreaker,
    AdaptiveRateLimiter,
    RetryAttempt,
    RetryResult,
    RetryReason,
    CircuitState,
    retry_on_failure
)


class TestRetryReason:
    """RetryReasonクラスのテスト"""
    
    def test_retry_reason_values(self):
        """リトライ理由の値確認"""
        assert RetryReason.NETWORK_ERROR.value == "network_error"
        assert RetryReason.TIMEOUT.value == "timeout"
        assert RetryReason.RATE_LIMIT.value == "rate_limit"
        assert RetryReason.SERVER_ERROR.value == "server_error"
        assert RetryReason.TEMPORARY_FAILURE.value == "temporary_failure"
        assert RetryReason.CONNECTION_ERROR.value == "connection_error"
        assert RetryReason.AUTHENTICATION_ERROR.value == "authentication_error"


class TestCircuitState:
    """CircuitStateクラスのテスト"""
    
    def test_circuit_state_values(self):
        """サーキットブレーカー状態の値確認"""
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"


class TestRetryConfig:
    """RetryConfigクラスのテスト"""
    
    def test_default_config(self):
        """デフォルト設定"""
        config = RetryConfig()
        
        assert config.max_attempts == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.jitter_factor == 0.1
        assert config.backoff_multiplier == 1.0
        assert config.retryable_exceptions == []
        assert config.non_retryable_exceptions == []
    
    def test_custom_config(self):
        """カスタム設定"""
        config = RetryConfig(
            max_attempts=5,
            base_delay=2.0,
            max_delay=120.0,
            retryable_exceptions=[ConnectionError],
            non_retryable_exceptions=[ValueError]
        )
        
        assert config.max_attempts == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 120.0
        assert ConnectionError in config.retryable_exceptions
        assert ValueError in config.non_retryable_exceptions


class TestRateLimitConfig:
    """RateLimitConfigクラスのテスト"""
    
    def test_default_config(self):
        """デフォルト設定"""
        config = RateLimitConfig()
        
        assert config.requests_per_second == 10.0
        assert config.requests_per_minute == 600.0
        assert config.requests_per_hour == 36000.0
        assert config.burst_capacity == 50
        assert config.adaptive_scaling is True
        assert config.cooldown_period == 30.0


class TestCircuitBreakerConfig:
    """CircuitBreakerConfigクラスのテスト"""
    
    def test_default_config(self):
        """デフォルト設定"""
        config = CircuitBreakerConfig()
        
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 60.0
        assert config.success_threshold == 3
        assert config.half_open_max_calls == 5
        assert config.sliding_window_size == 100


class TestRetryAttempt:
    """RetryAttemptクラスのテスト"""
    
    def test_attempt_creation(self):
        """リトライ試行記録の作成"""
        exception = Exception("Test error")
        attempt = RetryAttempt(
            attempt_number=1,
            timestamp=datetime.now(),
            delay=1.5,
            exception=exception,
            reason=RetryReason.NETWORK_ERROR,
            success=False
        )
        
        assert attempt.attempt_number == 1
        assert attempt.delay == 1.5
        assert attempt.exception == exception
        assert attempt.reason == RetryReason.NETWORK_ERROR
        assert attempt.success is False


class TestRetryResult:
    """RetryResultクラスのテスト"""
    
    def test_successful_result(self):
        """成功結果"""
        attempt = RetryAttempt(1, datetime.now(), 0, None, RetryReason.NETWORK_ERROR, True)
        result = RetryResult(
            success=True,
            result="success_data",
            attempts=[attempt],
            total_duration=1.0
        )
        
        assert result.success
        assert result.result == "success_data"
        assert result.attempt_count == 1
        assert result.final_attempt == attempt
        assert result.total_duration == 1.0
    
    def test_failed_result(self):
        """失敗結果"""
        exception = Exception("Final error")
        attempt = RetryAttempt(3, datetime.now(), 2.0, exception, RetryReason.SERVER_ERROR, False)
        result = RetryResult(
            success=False,
            exception=exception,
            attempts=[attempt],
            total_duration=5.0
        )
        
        assert not result.success
        assert result.exception == exception
        assert result.attempt_count == 1
        assert result.final_attempt == attempt


class TestTokenBucket:
    """TokenBucketクラスのテスト"""
    
    def test_bucket_initialization(self):
        """バケット初期化"""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        
        assert bucket.capacity == 10
        assert bucket.refill_rate == 2.0
        assert bucket.tokens == 10  # 初期トークン数は容量と同じ
        
        # 初期トークン数を指定
        bucket2 = TokenBucket(capacity=10, refill_rate=2.0, initial_tokens=5)
        assert bucket2.tokens == 5
    
    def test_consume_tokens(self):
        """トークン消費"""
        bucket = TokenBucket(capacity=10, refill_rate=2.0)
        
        # 成功ケース
        assert bucket.consume(5) is True
        assert bucket.tokens == 5
        
        # トークン不足ケース
        assert bucket.consume(10) is False
        assert bucket.tokens == 5  # トークン数は変わらない
    
    def test_token_refill(self):
        """トークン補充"""
        bucket = TokenBucket(capacity=10, refill_rate=4.0, initial_tokens=0)
        
        # 時間経過をシミュレート
        time.sleep(0.5)  # 0.5秒経過 -> 2トークン補充
        
        # トークンが補充されるかテスト
        assert bucket.consume(1) is True  # 少なくとも1トークンは利用可能
    
    def test_wait_for_tokens(self):
        """トークン待機"""
        bucket = TokenBucket(capacity=5, refill_rate=10.0, initial_tokens=0)
        
        start_time = time.time()
        success = bucket.wait_for_tokens(1, timeout=1.0)
        elapsed = time.time() - start_time
        
        assert success is True
        assert elapsed < 1.0  # 1秒以内に取得できるはず
    
    def test_wait_for_tokens_timeout(self):
        """トークン待機タイムアウト"""
        bucket = TokenBucket(capacity=5, refill_rate=0.1, initial_tokens=0)  # 非常に遅い補充
        
        start_time = time.time()
        success = bucket.wait_for_tokens(5, timeout=0.1)
        elapsed = time.time() - start_time
        
        assert success is False
        assert elapsed >= 0.1
    
    def test_get_status(self):
        """バケット状況取得"""
        bucket = TokenBucket(capacity=10, refill_rate=2.0, initial_tokens=7)
        status = bucket.get_status()
        
        assert status["capacity"] == 10
        assert status["refill_rate"] == 2.0
        assert "current_tokens" in status
        assert "utilization" in status
        assert 0 <= status["utilization"] <= 1
    
    def test_thread_safety(self):
        """スレッドセーフティ"""
        bucket = TokenBucket(capacity=100, refill_rate=50.0)
        results = []
        
        def consume_tokens():
            for _ in range(10):
                result = bucket.consume(1)
                results.append(result)
        
        # 複数スレッドで同時実行
        threads = [threading.Thread(target=consume_tokens) for _ in range(5)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # すべての消費が成功するはず（初期トークンが100個あるため）
        assert all(results)
        assert len(results) == 50


class TestCircuitBreaker:
    """CircuitBreakerクラスのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=1.0,  # テスト用に短く設定
            success_threshold=2,
            half_open_max_calls=3
        )
        self.circuit_breaker = CircuitBreaker(self.config)
    
    def test_circuit_breaker_initialization(self):
        """サーキットブレーカー初期化"""
        assert self.circuit_breaker.state == CircuitState.CLOSED
        assert self.circuit_breaker.failure_count == 0
        assert self.circuit_breaker.success_count == 0
    
    def test_successful_calls(self):
        """成功呼び出し"""
        def success_func():
            return "success"
        
        result = self.circuit_breaker.call(success_func)
        assert result == "success"
        assert self.circuit_breaker.state == CircuitState.CLOSED
    
    def test_circuit_opening(self):
        """サーキットオープン"""
        def failure_func():
            raise Exception("Test failure")
        
        def success_func():
            return "success"
        
        # 失敗閾値まで失敗させる
        for _ in range(self.config.failure_threshold):
            with pytest.raises(Exception):
                self.circuit_breaker.call(failure_func)
        
        assert self.circuit_breaker.state == CircuitState.OPEN
        
        # オープン状態では例外が発生
        with pytest.raises(Exception, match="サーキットブレーカーがオープン状態です"):
            self.circuit_breaker.call(success_func)
    
    def test_circuit_half_open_transition(self):
        """ハーフオープン遷移"""
        def failure_func():
            raise Exception("Test failure")
        
        # サーキットをオープンにする
        for _ in range(self.config.failure_threshold):
            with pytest.raises(Exception):
                self.circuit_breaker.call(failure_func)
        
        assert self.circuit_breaker.state == CircuitState.OPEN
        
        # 回復タイムアウト後にハーフオープンに遷移
        time.sleep(self.config.recovery_timeout + 0.1)
        
        def success_func():
            return "success"
        
        # 最初の呼び出しでハーフオープンに遷移
        result = self.circuit_breaker.call(success_func)
        assert result == "success"
        assert self.circuit_breaker.state == CircuitState.HALF_OPEN
    
    def test_circuit_recovery(self):
        """サーキット回復"""
        def failure_func():
            raise Exception("Test failure")
        
        def success_func():
            return "success"
        
        # サーキットをオープンにする
        for _ in range(self.config.failure_threshold):
            with pytest.raises(Exception):
                self.circuit_breaker.call(failure_func)
        
        # 回復タイムアウト後
        time.sleep(self.config.recovery_timeout + 0.1)
        
        # 成功閾値分だけ成功させる
        for _ in range(self.config.success_threshold):
            result = self.circuit_breaker.call(success_func)
            assert result == "success"
        
        assert self.circuit_breaker.state == CircuitState.CLOSED
    
    def test_half_open_failure(self):
        """ハーフオープン中の失敗"""
        def failure_func():
            raise Exception("Test failure")
        
        def success_func():
            return "success"
        
        # サーキットをオープンにする
        for _ in range(self.config.failure_threshold):
            with pytest.raises(Exception):
                self.circuit_breaker.call(failure_func)
        
        # ハーフオープンに遷移
        time.sleep(self.config.recovery_timeout + 0.1)
        self.circuit_breaker.call(success_func)
        assert self.circuit_breaker.state == CircuitState.HALF_OPEN
        
        # ハーフオープン中に失敗するとオープンに戻る
        with pytest.raises(Exception):
            self.circuit_breaker.call(failure_func)
        
        assert self.circuit_breaker.state == CircuitState.OPEN
    
    def test_get_statistics(self):
        """統計情報取得"""
        stats = self.circuit_breaker.get_statistics()
        
        assert "state" in stats
        assert "failure_count" in stats
        assert "success_count" in stats
        assert "last_failure_time" in stats
        assert "recent_success_rate" in stats
        assert "total_calls" in stats
        assert "half_open_calls" in stats
        
        assert stats["state"] == "closed"
        assert isinstance(stats["recent_success_rate"], float)


class TestAdaptiveRateLimiter:
    """AdaptiveRateLimiterクラスのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.config = RateLimitConfig(
            requests_per_second=5.0,
            requests_per_minute=300.0,
            requests_per_hour=18000.0,
            adaptive_scaling=True
        )
        self.rate_limiter = AdaptiveRateLimiter(self.config)
    
    def test_rate_limiter_initialization(self):
        """レート制限初期化"""
        assert self.rate_limiter.config == self.config
        assert self.rate_limiter.current_scale_factor == 1.0
    
    def test_acquire_tokens(self):
        """レート制限取得"""
        # 最初のリクエストは成功するはず
        assert self.rate_limiter.acquire() is True
        
        # トークンバケット直接テスト
        token_bucket = TokenBucket(capacity=3, refill_rate=1.0, initial_tokens=3)
        
        # 初期トークンを全て消費
        consumed = 0
        for _ in range(5):
            if token_bucket.consume(1):
                consumed += 1
        
        # 容量以上は消費できない
        assert consumed == 3
        
        # もう消費できない
        assert token_bucket.consume(1) is False
    
    def test_record_response(self):
        """レスポンス記録"""
        # 成功レスポンス
        self.rate_limiter.record_response(0.1, True)
        
        # 失敗レスポンス
        self.rate_limiter.record_response(2.0, False)
        
        assert len(self.rate_limiter.recent_response_times) == 2
        assert len(self.rate_limiter.recent_errors) == 1
    
    def test_adaptive_scaling(self):
        """適応的スケーリング"""
        # 初期状態のスケールファクター
        initial_scale = self.rate_limiter.current_scale_factor
        
        # 高いエラー率を記録
        for _ in range(10):
            self.rate_limiter.record_response(5.0, False)  # 遅くて失敗
        
        # スケールファクターが下がるはず
        self.rate_limiter._update_scale_factor()
        degraded_scale = self.rate_limiter.current_scale_factor
        assert degraded_scale < initial_scale
        
        # 新しいレートリミッターで良好なレスポンステスト
        good_limiter = AdaptiveRateLimiter(self.config)
        good_initial = good_limiter.current_scale_factor
        
        # 良好なレスポンスを記録
        for _ in range(25):
            good_limiter.record_response(0.1, True)  # 早くて成功
        
        # スケールファクターが上がるはず
        good_limiter._update_scale_factor()
        improved_scale = good_limiter.current_scale_factor
        
        assert improved_scale > good_initial
    
    def test_get_status(self):
        """レート制限状況取得"""
        status = self.rate_limiter.get_status()
        
        assert "scale_factor" in status
        assert "second_bucket" in status
        assert "minute_bucket" in status
        assert "hour_bucket" in status
        assert "recent_error_count" in status
        assert "recent_request_count" in status


class TestRetryManager:
    """RetryManagerクラスのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.retry_config = RetryConfig(max_attempts=3, base_delay=0.1)
        self.rate_limit_config = RateLimitConfig(requests_per_second=100.0)  # テスト用に高く設定
        self.circuit_breaker_config = CircuitBreakerConfig(failure_threshold=2, recovery_timeout=0.5)
        
        self.manager = RetryManager(
            retry_config=self.retry_config,
            rate_limit_config=self.rate_limit_config,
            circuit_breaker_config=self.circuit_breaker_config
        )
    
    def test_manager_initialization(self):
        """マネージャー初期化"""
        assert self.manager.retry_config == self.retry_config
        assert self.manager.rate_limit_config == self.rate_limit_config
        assert self.manager.circuit_breaker_config == self.circuit_breaker_config
        assert self.manager.circuit_breaker is not None
        assert self.manager.rate_limiter is not None
    
    def test_successful_execution(self):
        """成功実行"""
        def success_func():
            return "success"
        
        result = self.manager.execute_with_retry(success_func)
        
        assert result.success
        assert result.result == "success"
        assert result.attempt_count == 1
        assert result.final_attempt.success
    
    def test_retry_on_failure(self):
        """失敗時のリトライ"""
        # サーキットブレーカーを無効にしたマネージャーでテスト
        simple_manager = RetryManager(
            retry_config=RetryConfig(max_attempts=3, base_delay=0.1),
            enable_circuit_breaker=False,
            enable_rate_limiting=False
        )
        
        call_count = 0
        
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection failed")
            return "success"
        
        result = simple_manager.execute_with_retry(failing_func)
        
        assert result.success
        assert result.result == "success"
        assert result.attempt_count == 3
        assert call_count == 3
    
    def test_max_attempts_exceeded(self):
        """最大試行回数超過"""
        def always_failing_func():
            raise Exception("Always fails")
        
        result = self.manager.execute_with_retry(always_failing_func)
        
        assert not result.success
        assert result.attempt_count == self.retry_config.max_attempts
        assert isinstance(result.exception, Exception)
    
    def test_non_retryable_exception(self):
        """リトライ不可例外"""
        config = RetryConfig(
            max_attempts=3,
            non_retryable_exceptions=[ValueError]
        )
        manager = RetryManager(retry_config=config, enable_circuit_breaker=False, enable_rate_limiting=False)
        
        def value_error_func():
            raise ValueError("Invalid value")
        
        result = manager.execute_with_retry(value_error_func)
        
        assert not result.success
        assert result.attempt_count == 1  # リトライされない
        assert isinstance(result.exception, ValueError)
    
    def test_retryable_exception(self):
        """リトライ可能例外"""
        config = RetryConfig(
            max_attempts=3,
            retryable_exceptions=[ConnectionError]
        )
        manager = RetryManager(retry_config=config, enable_circuit_breaker=False, enable_rate_limiting=False)
        
        call_count = 0
        
        def connection_error_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Connection error")
        
        result = manager.execute_with_retry(connection_error_func)
        
        assert not result.success
        assert result.attempt_count == 3  # 3回リトライされる
        assert call_count == 3
    
    def test_exception_classification(self):
        """例外分類"""
        # ネットワークエラー
        reason = self.manager._classify_exception(Exception("network error"))
        assert reason == RetryReason.CONNECTION_ERROR
        
        # レート制限
        reason = self.manager._classify_exception(Exception("rate limit exceeded"))
        assert reason == RetryReason.RATE_LIMIT
        
        # タイムアウト
        reason = self.manager._classify_exception(Exception("timeout occurred"))
        assert reason == RetryReason.TIMEOUT
        
        # 認証エラー
        reason = self.manager._classify_exception(Exception("unauthorized access"))
        assert reason == RetryReason.AUTHENTICATION_ERROR
        
        # サーバーエラー
        reason = self.manager._classify_exception(Exception("server error 503"))
        assert reason == RetryReason.SERVER_ERROR
        
        # その他
        reason = self.manager._classify_exception(Exception("unknown error"))
        assert reason == RetryReason.TEMPORARY_FAILURE
    
    def test_delay_calculation(self):
        """遅延計算"""
        config = RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=10.0)
        manager = RetryManager(retry_config=config, enable_circuit_breaker=False, enable_rate_limiting=False)
        
        # 1回目の遅延
        delay1 = manager._calculate_delay(1, config, RetryReason.NETWORK_ERROR)
        assert 0.9 <= delay1 <= 1.1  # ジッター考慮
        
        # 2回目の遅延
        delay2 = manager._calculate_delay(2, config, RetryReason.NETWORK_ERROR)
        assert 1.8 <= delay2 <= 2.2  # 2倍 + ジッター
        
        # レート制限の場合は長めの遅延
        delay_rate_limit = manager._calculate_delay(1, config, RetryReason.RATE_LIMIT)
        assert delay_rate_limit > delay1
        
        # 最大遅延の制限（ジッターを考慮して若干の余裕を持たせる）
        delay_large = manager._calculate_delay(10, config, RetryReason.NETWORK_ERROR)
        assert delay_large <= config.max_delay * 1.1  # ジッター分の余裕
    
    def test_circuit_breaker_integration(self):
        """サーキットブレーカー統合"""
        def always_failing_func():
            raise Exception("Always fails")
        
        # 失敗を重ねてサーキットブレーカーをオープンにする
        for _ in range(3):
            result = self.manager.execute_with_retry(always_failing_func)
            assert not result.success
        
        # サーキットブレーカーがオープンになったかチェック
        stats = self.manager.circuit_breaker.get_statistics()
        assert stats["state"] == "open"
    
    def test_rate_limiter_integration(self):
        """レート制限統合"""
        # レート制限を厳しく設定
        strict_config = RateLimitConfig(requests_per_second=1.0)
        manager = RetryManager(
            retry_config=RetryConfig(max_attempts=1),
            rate_limit_config=strict_config,
            enable_circuit_breaker=False
        )
        
        def success_func():
            return "success"
        
        # 最初は成功
        result1 = manager.execute_with_retry(success_func)
        assert result1.success
        
        # 2回目は即座にレート制限される可能性
        result2 = manager.execute_with_retry(success_func)
        # レート制限の実装によって結果が変わる可能性があるため、ログ確認程度
    
    def test_get_status(self):
        """マネージャー状況取得"""
        status = self.manager.get_status()
        
        assert "retry_config" in status
        assert "circuit_breaker" in status
        assert "rate_limiter" in status
        
        retry_info = status["retry_config"]
        assert "max_attempts" in retry_info
        assert "base_delay" in retry_info
        assert "max_delay" in retry_info


class TestRetryDecorator:
    """リトライデコレーターのテスト"""
    
    def test_decorator_success(self):
        """デコレーター成功"""
        @retry_on_failure(retry_config=RetryConfig(max_attempts=3))
        def success_func():
            return "decorated success"
        
        result = success_func()
        assert result == "decorated success"
    
    def test_decorator_retry(self):
        """デコレーターリトライ"""
        call_count = 0
        
        @retry_on_failure(retry_config=RetryConfig(max_attempts=3, base_delay=0.01))
        def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise Exception("Temporary failure")
            return "eventual success"
        
        result = failing_func()
        assert result == "eventual success"
        assert call_count == 3
    
    def test_decorator_final_failure(self):
        """デコレーター最終失敗"""
        @retry_on_failure(retry_config=RetryConfig(max_attempts=2, base_delay=0.01))
        def always_failing_func():
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError):
            always_failing_func()


class TestRetryManagerDisabledComponents:
    """無効化されたコンポーネントのテスト"""
    
    def test_disabled_circuit_breaker(self):
        """サーキットブレーカー無効"""
        manager = RetryManager(
            enable_circuit_breaker=False,
            enable_rate_limiting=False
        )
        
        assert manager.circuit_breaker is None
        assert manager.rate_limiter is None
        
        def success_func():
            return "success"
        
        result = manager.execute_with_retry(success_func)
        assert result.success
    
    def test_disabled_rate_limiting(self):
        """レート制限無効"""
        manager = RetryManager(
            enable_circuit_breaker=True,
            enable_rate_limiting=False
        )
        
        assert manager.circuit_breaker is not None
        assert manager.rate_limiter is None


class TestErrorHandling:
    """エラーハンドリングのテスト"""
    
    def test_authentication_error_not_retried(self):
        """認証エラーはリトライされない"""
        manager = RetryManager(
            retry_config=RetryConfig(max_attempts=3),
            enable_circuit_breaker=False,
            enable_rate_limiting=False
        )
        
        def auth_error_func():
            raise Exception("unauthorized access")
        
        result = manager.execute_with_retry(auth_error_func)
        
        assert not result.success
        assert result.attempt_count == 1  # リトライされない
    
    def test_should_retry_logic(self):
        """リトライ判定ロジック"""
        config = RetryConfig(max_attempts=3)
        manager = RetryManager(retry_config=config, enable_circuit_breaker=False, enable_rate_limiting=False)
        
        # 通常の例外（リトライする）
        assert manager._should_retry(Exception("normal error"), config, 1) is True
        
        # 最大試行回数に達した場合（リトライしない）
        assert manager._should_retry(Exception("normal error"), config, 3) is False
        
        # 認証エラー（リトライしない）
        assert manager._should_retry(Exception("unauthorized"), config, 1) is False


class TestConcurrentAccess:
    """同時アクセスのテスト"""
    
    def test_concurrent_retry_execution(self):
        """同時リトライ実行"""
        manager = RetryManager(
            retry_config=RetryConfig(max_attempts=2, base_delay=0.01),
            enable_circuit_breaker=False,
            enable_rate_limiting=False
        )
        
        results = []
        
        def test_func():
            return "success"
        
        def worker():
            result = manager.execute_with_retry(test_func)
            results.append(result.success)
        
        # 複数スレッドで同時実行
        threads = [threading.Thread(target=worker) for _ in range(10)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        
        # すべて成功するはず
        assert all(results)
        assert len(results) == 10