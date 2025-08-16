# -*- coding: utf-8 -*-
"""
高度なリトライマネージャー
指数バックオフ、サーキットブレーカー、適応的レート制限を実装
"""

import time
import random
import logging
import threading
from typing import Dict, List, Optional, Any, Callable, Type, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
import inspect


logger = logging.getLogger(__name__)


class RetryReason(Enum):
    """リトライ理由"""
    NETWORK_ERROR = "network_error"
    TIMEOUT = "timeout"
    RATE_LIMIT = "rate_limit"
    SERVER_ERROR = "server_error"
    TEMPORARY_FAILURE = "temporary_failure"
    CONNECTION_ERROR = "connection_error"
    AUTHENTICATION_ERROR = "authentication_error"


class CircuitState(Enum):
    """サーキットブレーカーの状態"""
    CLOSED = "closed"      # 正常状態
    OPEN = "open"          # 障害状態（リクエスト拒否）
    HALF_OPEN = "half_open"  # 回復テスト状態


@dataclass
class RetryConfig:
    """リトライ設定"""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter_factor: float = 0.1
    backoff_multiplier: float = 1.0
    retryable_exceptions: List[Type[Exception]] = field(default_factory=list)
    non_retryable_exceptions: List[Type[Exception]] = field(default_factory=list)


@dataclass
class RateLimitConfig:
    """レート制限設定"""
    requests_per_second: float = 10.0
    requests_per_minute: float = 600.0
    requests_per_hour: float = 36000.0
    burst_capacity: int = 50
    adaptive_scaling: bool = True
    cooldown_period: float = 30.0


@dataclass
class CircuitBreakerConfig:
    """サーキットブレーカー設定"""
    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    success_threshold: int = 3
    half_open_max_calls: int = 5
    sliding_window_size: int = 100


@dataclass
class RetryAttempt:
    """リトライ試行記録"""
    attempt_number: int
    timestamp: datetime
    delay: float
    exception: Optional[Exception]
    reason: RetryReason
    success: bool = False


@dataclass
class RetryResult:
    """リトライ結果"""
    success: bool
    result: Any = None
    exception: Optional[Exception] = None
    attempts: List[RetryAttempt] = field(default_factory=list)
    total_duration: float = 0.0
    
    @property
    def attempt_count(self) -> int:
        return len(self.attempts)
    
    @property
    def final_attempt(self) -> Optional[RetryAttempt]:
        return self.attempts[-1] if self.attempts else None


class TokenBucket:
    """トークンバケットアルゴリズム実装"""
    
    def __init__(self, 
                 capacity: int,
                 refill_rate: float,
                 initial_tokens: Optional[int] = None):
        """
        Args:
            capacity: バケット容量
            refill_rate: 毎秒のトークン補充レート
            initial_tokens: 初期トークン数
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = initial_tokens if initial_tokens is not None else capacity
        self.last_refill = time.time()
        self._lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        トークンを消費
        
        Args:
            tokens: 消費するトークン数
            
        Returns:
            bool: 消費成功したかどうか
        """
        with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def _refill(self):
        """トークンを補充"""
        now = time.time()
        elapsed = now - self.last_refill
        
        # 補充するトークン数を計算
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def wait_for_tokens(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """
        トークンが利用可能になるまで待機
        
        Args:
            tokens: 必要なトークン数
            timeout: タイムアウト時間
            
        Returns:
            bool: トークン取得成功したかどうか
        """
        start_time = time.time()
        
        while True:
            if self.consume(tokens):
                return True
            
            # タイムアウトチェック
            if timeout and (time.time() - start_time) >= timeout:
                return False
            
            # 次のトークン補充まで待機
            with self._lock:
                if self.tokens < tokens:
                    wait_time = (tokens - self.tokens) / self.refill_rate
                    wait_time = min(wait_time, 1.0)  # 最大1秒
                    time.sleep(wait_time)
    
    def get_status(self) -> Dict[str, Any]:
        """バケット状況を取得"""
        with self._lock:
            self._refill()
            return {
                "capacity": self.capacity,
                "current_tokens": self.tokens,
                "refill_rate": self.refill_rate,
                "utilization": (self.capacity - self.tokens) / self.capacity
            }


class CircuitBreaker:
    """サーキットブレーカー実装"""
    
    def __init__(self, config: CircuitBreakerConfig):
        self.config = config
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.half_open_calls = 0
        self._lock = threading.Lock()
        self.call_history = []  # 呼び出し履歴（スライディングウィンドウ用）
    
    def call(self, func: Callable, *args, **kwargs):
        """
        サーキットブレーカー経由での関数呼び出し
        
        Args:
            func: 呼び出す関数
            *args, **kwargs: 関数の引数
            
        Returns:
            関数の戻り値
            
        Raises:
            Exception: サーキットオープン時またはタイムアウト時
        """
        with self._lock:
            if self.state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_calls = 0
                    logger.info("サーキットブレーカー: HALF_OPEN状態に移行")
                else:
                    raise Exception("サーキットブレーカーがオープン状態です")
            
            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls >= self.config.half_open_max_calls:
                    raise Exception("HALF_OPEN状態での最大呼び出し数に達しました")
                self.half_open_calls += 1
        
        try:
            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            
            self._record_success(duration)
            return result
            
        except Exception as e:
            self._record_failure(e)
            raise
    
    def _record_success(self, duration: float):
        """成功を記録"""
        with self._lock:
            self.success_count += 1
            self._add_to_history(True, duration)
            
            if self.state == CircuitState.HALF_OPEN:
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    logger.info("サーキットブレーカー: CLOSED状態に回復")
            elif self.state == CircuitState.CLOSED:
                # 成功カウントをリセット（連続失敗のカウンターとして使用）
                self.failure_count = 0
    
    def _record_failure(self, exception: Exception):
        """失敗を記録"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()
            self._add_to_history(False, 0)
            
            if self.state == CircuitState.CLOSED:
                if self.failure_count >= self.config.failure_threshold:
                    self.state = CircuitState.OPEN
                    logger.warning(f"サーキットブレーカー: OPEN状態に移行 (失敗数: {self.failure_count})")
            elif self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning("サーキットブレーカー: HALF_OPEN中の失敗によりOPEN状態に戻る")
    
    def _add_to_history(self, success: bool, duration: float):
        """呼び出し履歴に追加"""
        record = {
            "timestamp": datetime.now(),
            "success": success,
            "duration": duration
        }
        
        self.call_history.append(record)
        
        # スライディングウィンドウサイズを維持
        if len(self.call_history) > self.config.sliding_window_size:
            self.call_history.pop(0)
    
    def _should_attempt_reset(self) -> bool:
        """リセット試行すべきかチェック"""
        if not self.last_failure_time:
            return True
        
        elapsed = datetime.now() - self.last_failure_time
        return elapsed.total_seconds() >= self.config.recovery_timeout
    
    def get_statistics(self) -> Dict[str, Any]:
        """統計情報を取得"""
        with self._lock:
            recent_calls = self.call_history[-50:] if self.call_history else []
            success_rate = 0.0
            
            if recent_calls:
                successes = sum(1 for call in recent_calls if call["success"])
                success_rate = successes / len(recent_calls)
            
            return {
                "state": self.state.value,
                "failure_count": self.failure_count,
                "success_count": self.success_count,
                "last_failure_time": self.last_failure_time,
                "recent_success_rate": success_rate,
                "total_calls": len(self.call_history),
                "half_open_calls": self.half_open_calls
            }


class AdaptiveRateLimiter:
    """適応的レート制限"""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self.second_bucket = TokenBucket(
            capacity=max(1, int(config.requests_per_second * 2)),
            refill_rate=config.requests_per_second
        )
        self.minute_bucket = TokenBucket(
            capacity=max(10, int(config.requests_per_minute * 0.1)),
            refill_rate=config.requests_per_minute / 60.0
        )
        self.hour_bucket = TokenBucket(
            capacity=max(100, int(config.requests_per_hour * 0.05)),
            refill_rate=config.requests_per_hour / 3600.0
        )
        
        self.recent_response_times = []
        self.recent_errors = []
        self.current_scale_factor = 1.0
        self._lock = threading.Lock()
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        レート制限チェック
        
        Args:
            timeout: タイムアウト時間
            
        Returns:
            bool: リクエスト許可されたかどうか
        """
        # 適応的スケーリング
        if self.config.adaptive_scaling:
            self._update_scale_factor()
        
        # 各レベルでのトークン消費
        buckets = [self.second_bucket, self.minute_bucket, self.hour_bucket]
        acquired_buckets = []
        
        try:
            for bucket in buckets:
                if bucket.wait_for_tokens(1, timeout):
                    acquired_buckets.append(bucket)
                else:
                    # 取得済みのトークンを返却
                    for acquired in acquired_buckets:
                        # 実際の返却はトークンバケットの実装次第
                        pass
                    return False
            
            return True
            
        except Exception:
            return False
    
    def record_response(self, duration: float, success: bool):
        """レスポンス結果を記録"""
        with self._lock:
            self.recent_response_times.append({
                "timestamp": time.time(),
                "duration": duration,
                "success": success
            })
            
            if not success:
                self.recent_errors.append(time.time())
            
            # 古いデータを削除（5分以内のデータのみ保持）
            cutoff_time = time.time() - 300
            self.recent_response_times = [
                r for r in self.recent_response_times 
                if r["timestamp"] > cutoff_time
            ]
            self.recent_errors = [
                t for t in self.recent_errors 
                if t > cutoff_time
            ]
    
    def _update_scale_factor(self):
        """スケールファクターを更新"""
        with self._lock:
            if not self.recent_response_times:
                return
            
            # 最近のレスポンス時間とエラー率を分析
            recent_times = [r["duration"] for r in self.recent_response_times[-20:]]
            avg_response_time = sum(recent_times) / len(recent_times)
            
            error_rate = len(self.recent_errors) / max(1, len(self.recent_response_times))
            
            # スケールファクターを調整
            if error_rate > 0.1 or avg_response_time > 5.0:
                # エラー率が高いまたはレスポンスが遅い場合は制限を強化
                self.current_scale_factor = max(0.1, self.current_scale_factor * 0.8)
            elif error_rate < 0.02 and avg_response_time < 1.0:
                # 安定している場合は制限を緩和
                self.current_scale_factor = min(2.0, self.current_scale_factor * 1.1)
            
            # バケットの補充レートを調整
            self.second_bucket.refill_rate = self.config.requests_per_second * self.current_scale_factor
    
    def get_status(self) -> Dict[str, Any]:
        """レート制限状況を取得"""
        return {
            "scale_factor": self.current_scale_factor,
            "second_bucket": self.second_bucket.get_status(),
            "minute_bucket": self.minute_bucket.get_status(),
            "hour_bucket": self.hour_bucket.get_status(),
            "recent_error_count": len(self.recent_errors),
            "recent_request_count": len(self.recent_response_times)
        }


class RetryManager:
    """統合リトライマネージャー"""
    
    def __init__(self,
                 retry_config: Optional[RetryConfig] = None,
                 rate_limit_config: Optional[RateLimitConfig] = None,
                 circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
                 enable_circuit_breaker: bool = True,
                 enable_rate_limiting: bool = True):
        """
        Args:
            retry_config: リトライ設定
            rate_limit_config: レート制限設定
            circuit_breaker_config: サーキットブレーカー設定
            enable_circuit_breaker: サーキットブレーカー有効化
            enable_rate_limiting: レート制限有効化
        """
        self.retry_config = retry_config or RetryConfig()
        self.rate_limit_config = rate_limit_config or RateLimitConfig()
        self.circuit_breaker_config = circuit_breaker_config or CircuitBreakerConfig()
        
        self.circuit_breaker = CircuitBreaker(self.circuit_breaker_config) if enable_circuit_breaker else None
        self.rate_limiter = AdaptiveRateLimiter(self.rate_limit_config) if enable_rate_limiting else None
        
        self.logger = logging.getLogger(__name__)
    
    def execute_with_retry(self, 
                          func: Callable,
                          *args,
                          retry_config: Optional[RetryConfig] = None,
                          **kwargs) -> RetryResult:
        """
        リトライ付きで関数を実行
        
        Args:
            func: 実行する関数
            retry_config: 個別のリトライ設定
            *args, **kwargs: 関数の引数
            
        Returns:
            RetryResult: 実行結果
        """
        config = retry_config or self.retry_config
        start_time = time.time()
        attempts = []
        
        for attempt_num in range(1, config.max_attempts + 1):
            attempt_start = time.time()
            
            try:
                # レート制限チェック
                if self.rate_limiter and not self.rate_limiter.acquire(timeout=30.0):
                    raise Exception("レート制限により実行が拒否されました")
                
                # サーキットブレーカー経由で実行
                if self.circuit_breaker:
                    result = self.circuit_breaker.call(func, *args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # 成功時の記録
                duration = time.time() - attempt_start
                if self.rate_limiter:
                    self.rate_limiter.record_response(duration, True)
                
                attempts.append(RetryAttempt(
                    attempt_number=attempt_num,
                    timestamp=datetime.now(),
                    delay=0,
                    exception=None,
                    reason=RetryReason.NETWORK_ERROR,  # 成功時は意味なし
                    success=True
                ))
                
                return RetryResult(
                    success=True,
                    result=result,
                    attempts=attempts,
                    total_duration=time.time() - start_time
                )
                
            except Exception as e:
                duration = time.time() - attempt_start
                if self.rate_limiter:
                    self.rate_limiter.record_response(duration, False)
                
                reason = self._classify_exception(e)
                
                # リトライ可能性の判定
                if not self._should_retry(e, config, attempt_num):
                    attempts.append(RetryAttempt(
                        attempt_number=attempt_num,
                        timestamp=datetime.now(),
                        delay=0,
                        exception=e,
                        reason=reason,
                        success=False
                    ))
                    
                    return RetryResult(
                        success=False,
                        exception=e,
                        attempts=attempts,
                        total_duration=time.time() - start_time
                    )
                
                # 遅延計算
                delay = self._calculate_delay(attempt_num, config, reason)
                
                attempts.append(RetryAttempt(
                    attempt_number=attempt_num,
                    timestamp=datetime.now(),
                    delay=delay,
                    exception=e,
                    reason=reason,
                    success=False
                ))
                
                if attempt_num < config.max_attempts:
                    self.logger.warning(
                        f"リトライ {attempt_num}/{config.max_attempts}: {e} "
                        f"(遅延: {delay:.2f}秒)"
                    )
                    time.sleep(delay)
                else:
                    self.logger.error(f"最大リトライ回数に達しました: {e}")
        
        # すべてのリトライが失敗
        final_exception = attempts[-1].exception if attempts else Exception("不明なエラー")
        return RetryResult(
            success=False,
            exception=final_exception,
            attempts=attempts,
            total_duration=time.time() - start_time
        )
    
    def _classify_exception(self, exception: Exception) -> RetryReason:
        """例外をリトライ理由に分類"""
        exception_str = str(exception).lower()
        
        if "rate limit" in exception_str or "too many requests" in exception_str:
            return RetryReason.RATE_LIMIT
        elif "timeout" in exception_str:
            return RetryReason.TIMEOUT
        elif "connection" in exception_str or "network" in exception_str:
            return RetryReason.CONNECTION_ERROR
        elif "auth" in exception_str or "unauthorized" in exception_str:
            return RetryReason.AUTHENTICATION_ERROR
        elif "server error" in exception_str or "503" in exception_str or "502" in exception_str:
            return RetryReason.SERVER_ERROR
        else:
            return RetryReason.TEMPORARY_FAILURE
    
    def _should_retry(self, exception: Exception, config: RetryConfig, attempt_num: int) -> bool:
        """リトライすべきかどうかを判定"""
        # 最大試行回数チェック
        if attempt_num >= config.max_attempts:
            return False
        
        exception_type = type(exception)
        
        # 明示的に非リトライ対象の例外
        if any(issubclass(exception_type, exc) for exc in config.non_retryable_exceptions):
            return False
        
        # 明示的にリトライ対象の例外
        if any(issubclass(exception_type, exc) for exc in config.retryable_exceptions):
            return True
        
        # デフォルトの判定ロジック
        reason = self._classify_exception(exception)
        
        # 認証エラーはリトライしない
        if reason == RetryReason.AUTHENTICATION_ERROR:
            return False
        
        return True
    
    def _calculate_delay(self, attempt_num: int, config: RetryConfig, reason: RetryReason) -> float:
        """遅延時間を計算"""
        # 基本遅延の計算
        delay = config.base_delay * (config.exponential_base ** (attempt_num - 1))
        delay *= config.backoff_multiplier
        
        # レート制限の場合は長めの遅延
        if reason == RetryReason.RATE_LIMIT:
            delay *= 2.0
        
        # 最大遅延の制限
        delay = min(delay, config.max_delay)
        
        # ジッターの追加
        jitter = delay * config.jitter_factor * (2 * random.random() - 1)
        delay += jitter
        
        return max(0, delay)
    
    def get_status(self) -> Dict[str, Any]:
        """マネージャーの状況を取得"""
        status = {
            "retry_config": {
                "max_attempts": self.retry_config.max_attempts,
                "base_delay": self.retry_config.base_delay,
                "max_delay": self.retry_config.max_delay
            }
        }
        
        if self.circuit_breaker:
            status["circuit_breaker"] = self.circuit_breaker.get_statistics()
        
        if self.rate_limiter:
            status["rate_limiter"] = self.rate_limiter.get_status()
        
        return status


def retry_on_failure(retry_config: Optional[RetryConfig] = None,
                    rate_limit_config: Optional[RateLimitConfig] = None,
                    circuit_breaker_config: Optional[CircuitBreakerConfig] = None):
    """
    リトライデコレーター
    
    Args:
        retry_config: リトライ設定
        rate_limit_config: レート制限設定
        circuit_breaker_config: サーキットブレーカー設定
    """
    def decorator(func):
        manager = RetryManager(
            retry_config=retry_config,
            rate_limit_config=rate_limit_config,
            circuit_breaker_config=circuit_breaker_config
        )
        
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = manager.execute_with_retry(func, *args, **kwargs)
            if result.success:
                return result.result
            else:
                raise result.exception
        
        return wrapper
    return decorator