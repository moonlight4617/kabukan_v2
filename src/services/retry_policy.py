# -*- coding: utf-8 -*-
"""
リトライポリシーサービス
RetryPolicyクラスの作成、指数バックオフアルゴリズムの実装
"""

import logging
import asyncio
import random
import time
from typing import Dict, List, Optional, Any, Callable, Type, Union, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import functools
import inspect

from src.services.error_handler import ErrorHandler, ErrorInfo, ErrorCategory, ErrorSeverity


logger = logging.getLogger(__name__)


class BackoffStrategy(Enum):
    """バックオフ戦略"""
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    POLYNOMIAL = "polynomial"
    FIBONACCI = "fibonacci"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            BackoffStrategy.FIXED: "固定",
            BackoffStrategy.LINEAR: "線形",
            BackoffStrategy.EXPONENTIAL: "指数",
            BackoffStrategy.POLYNOMIAL: "多項式",
            BackoffStrategy.FIBONACCI: "フィボナッチ"
        }[self]


class RetryCondition(Enum):
    """リトライ条件"""
    ALL_EXCEPTIONS = "all_exceptions"
    SPECIFIC_EXCEPTIONS = "specific_exceptions"
    SPECIFIC_CATEGORIES = "specific_categories"
    SEVERITY_BASED = "severity_based"
    CUSTOM_CONDITION = "custom_condition"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            RetryCondition.ALL_EXCEPTIONS: "すべての例外",
            RetryCondition.SPECIFIC_EXCEPTIONS: "特定の例外",
            RetryCondition.SPECIFIC_CATEGORIES: "特定のカテゴリ",
            RetryCondition.SEVERITY_BASED: "重要度ベース",
            RetryCondition.CUSTOM_CONDITION: "カスタム条件"
        }[self]


@dataclass
class RetryPolicy:
    """リトライポリシー"""
    name: str
    max_attempts: int = 3
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    initial_delay: float = 1.0
    max_delay: float = 300.0
    multiplier: float = 2.0
    jitter: bool = True
    jitter_range: float = 0.1
    retry_condition: RetryCondition = RetryCondition.ALL_EXCEPTIONS
    retryable_exceptions: List[Type[Exception]] = field(default_factory=list)
    retryable_categories: List[ErrorCategory] = field(default_factory=list)
    retryable_severities: List[ErrorSeverity] = field(default_factory=list)
    custom_condition: Optional[Callable[[Exception], bool]] = None
    timeout_per_attempt: Optional[float] = None
    circuit_breaker_enabled: bool = False
    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: int = 300

    def __post_init__(self):
        """初期化後処理"""
        if self.retry_condition == RetryCondition.ALL_EXCEPTIONS:
            self.retryable_exceptions = [Exception]
        elif self.retry_condition == RetryCondition.SPECIFIC_CATEGORIES and not self.retryable_categories:
            self.retryable_categories = [ErrorCategory.NETWORK, ErrorCategory.TIMEOUT, ErrorCategory.API_ERROR]
        elif self.retry_condition == RetryCondition.SEVERITY_BASED and not self.retryable_severities:
            self.retryable_severities = [ErrorSeverity.LOW, ErrorSeverity.MEDIUM]

    def is_retryable(self, exception: Exception, error_info: Optional[ErrorInfo] = None) -> bool:
        """例外がリトライ可能か判定"""
        if self.retry_condition == RetryCondition.ALL_EXCEPTIONS:
            return True
        
        elif self.retry_condition == RetryCondition.SPECIFIC_EXCEPTIONS:
            return any(isinstance(exception, exc_type) for exc_type in self.retryable_exceptions)
        
        elif self.retry_condition == RetryCondition.SPECIFIC_CATEGORIES:
            if error_info:
                return error_info.category in self.retryable_categories
            return False
        
        elif self.retry_condition == RetryCondition.SEVERITY_BASED:
            if error_info:
                return error_info.severity in self.retryable_severities
            return False
        
        elif self.retry_condition == RetryCondition.CUSTOM_CONDITION:
            if self.custom_condition:
                return self.custom_condition(exception)
            return False
        
        return False

    def calculate_delay(self, attempt: int) -> float:
        """リトライ遅延時間を計算"""
        if self.backoff_strategy == BackoffStrategy.FIXED:
            delay = self.initial_delay
        
        elif self.backoff_strategy == BackoffStrategy.LINEAR:
            delay = self.initial_delay * attempt
        
        elif self.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = self.initial_delay * (self.multiplier ** (attempt - 1))
        
        elif self.backoff_strategy == BackoffStrategy.POLYNOMIAL:
            delay = self.initial_delay * (attempt ** self.multiplier)
        
        elif self.backoff_strategy == BackoffStrategy.FIBONACCI:
            delay = self.initial_delay * self._fibonacci(attempt)
        
        else:
            delay = self.initial_delay
        
        # 最大遅延時間制限
        delay = min(delay, self.max_delay)
        
        # ジッター追加
        if self.jitter:
            jitter_amount = delay * self.jitter_range
            delay += random.uniform(-jitter_amount, jitter_amount)
        
        return max(0.0, delay)

    def _fibonacci(self, n: int) -> int:
        """フィボナッチ数列計算"""
        if n <= 1:
            return n
        elif n == 2:
            return 1
        else:
            a, b = 1, 1
            for _ in range(3, n + 1):
                a, b = b, a + b
            return b

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "name": self.name,
            "max_attempts": self.max_attempts,
            "backoff_strategy": self.backoff_strategy.value,
            "initial_delay": self.initial_delay,
            "max_delay": self.max_delay,
            "multiplier": self.multiplier,
            "jitter": self.jitter,
            "retry_condition": self.retry_condition.value,
            "retryable_exceptions": [exc.__name__ for exc in self.retryable_exceptions],
            "retryable_categories": [cat.value for cat in self.retryable_categories],
            "retryable_severities": [sev.value for sev in self.retryable_severities],
            "circuit_breaker_enabled": self.circuit_breaker_enabled,
            "circuit_breaker_threshold": self.circuit_breaker_threshold,
            "circuit_breaker_timeout": self.circuit_breaker_timeout
        }


@dataclass
class RetryAttempt:
    """リトライ試行情報"""
    attempt_number: int
    timestamp: datetime
    exception: Exception
    delay: float
    total_elapsed: float
    
    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "attempt_number": self.attempt_number,
            "timestamp": self.timestamp.isoformat(),
            "exception_type": type(self.exception).__name__,
            "exception_message": str(self.exception),
            "delay": self.delay,
            "total_elapsed": self.total_elapsed
        }


@dataclass
class RetryResult:
    """リトライ結果"""
    success: bool
    final_result: Any = None
    final_exception: Optional[Exception] = None
    total_attempts: int = 0
    total_elapsed: float = 0.0
    attempts_history: List[RetryAttempt] = field(default_factory=list)
    policy_used: Optional[str] = None
    
    @property
    def failure_rate(self) -> float:
        """失敗率"""
        if self.total_attempts == 0:
            return 0.0
        failed_attempts = self.total_attempts - (1 if self.success else 0)
        return failed_attempts / self.total_attempts

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "success": self.success,
            "total_attempts": self.total_attempts,
            "total_elapsed": self.total_elapsed,
            "failure_rate": self.failure_rate,
            "policy_used": self.policy_used,
            "attempts_history": [attempt.to_dict() for attempt in self.attempts_history],
            "final_exception": {
                "type": type(self.final_exception).__name__,
                "message": str(self.final_exception)
            } if self.final_exception else None
        }


class CircuitBreakerState(Enum):
    """サーキットブレーカー状態"""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerInfo:
    """サーキットブレーカー情報"""
    state: CircuitBreakerState = CircuitBreakerState.CLOSED
    failure_count: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    total_requests: int = 0
    
    def should_allow_request(self, threshold: int, timeout: int) -> bool:
        """リクエストを許可すべきか判定"""
        if self.state == CircuitBreakerState.CLOSED:
            return True
        elif self.state == CircuitBreakerState.OPEN:
            if self.last_failure_time and (datetime.now() - self.last_failure_time).total_seconds() > timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False
        elif self.state == CircuitBreakerState.HALF_OPEN:
            return True
        return False
    
    def record_success(self):
        """成功を記録"""
        self.failure_count = 0
        self.last_success_time = datetime.now()
        self.state = CircuitBreakerState.CLOSED
        self.total_requests += 1
    
    def record_failure(self, threshold: int):
        """失敗を記録"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        self.total_requests += 1
        
        if self.failure_count >= threshold:
            self.state = CircuitBreakerState.OPEN


class RetryPolicyManager:
    """リトライポリシー管理クラス"""
    
    def __init__(self, error_handler: Optional[ErrorHandler] = None):
        self.error_handler = error_handler
        self.policies: Dict[str, RetryPolicy] = {}
        self.circuit_breakers: Dict[str, CircuitBreakerInfo] = {}
        self.retry_statistics: Dict[str, List[RetryResult]] = {}
        self.logger = logging.getLogger(__name__)
        
        # デフォルトポリシーを初期化
        self._initialize_default_policies()
    
    def _initialize_default_policies(self):
        """デフォルトポリシーを初期化"""
        # ネットワークエラー用ポリシー
        network_policy = RetryPolicy(
            name="network_errors",
            max_attempts=3,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            initial_delay=1.0,
            max_delay=30.0,
            retry_condition=RetryCondition.SPECIFIC_CATEGORIES,
            retryable_categories=[ErrorCategory.NETWORK, ErrorCategory.TIMEOUT]
        )
        
        # APIエラー用ポリシー
        api_policy = RetryPolicy(
            name="api_errors",
            max_attempts=5,
            backoff_strategy=BackoffStrategy.EXPONENTIAL,
            initial_delay=2.0,
            max_delay=60.0,
            retry_condition=RetryCondition.SPECIFIC_CATEGORIES,
            retryable_categories=[ErrorCategory.API_ERROR, ErrorCategory.EXTERNAL_SERVICE],
            circuit_breaker_enabled=True,
            circuit_breaker_threshold=5
        )
        
        # 一般的なエラー用ポリシー
        general_policy = RetryPolicy(
            name="general_errors",
            max_attempts=2,
            backoff_strategy=BackoffStrategy.LINEAR,
            initial_delay=0.5,
            max_delay=10.0,
            retry_condition=RetryCondition.SEVERITY_BASED,
            retryable_severities=[ErrorSeverity.LOW, ErrorSeverity.MEDIUM]
        )
        
        # 重要な処理用ポリシー
        critical_policy = RetryPolicy(
            name="critical_operations",
            max_attempts=5,
            backoff_strategy=BackoffStrategy.FIBONACCI,
            initial_delay=1.0,
            max_delay=120.0,
            retry_condition=RetryCondition.ALL_EXCEPTIONS,
            circuit_breaker_enabled=True
        )
        
        self.add_policy(network_policy)
        self.add_policy(api_policy)
        self.add_policy(general_policy)
        self.add_policy(critical_policy)
    
    def add_policy(self, policy: RetryPolicy):
        """ポリシーを追加"""
        self.policies[policy.name] = policy
        self.logger.info(f"リトライポリシーを追加: {policy.name}")
    
    def get_policy(self, name: str) -> Optional[RetryPolicy]:
        """ポリシーを取得"""
        return self.policies.get(name)
    
    async def execute_with_retry(self,
                               func: Callable,
                               policy_name: str = "general_errors",
                               *args,
                               **kwargs) -> RetryResult:
        """
        リトライ付きで関数を実行
        
        Args:
            func: 実行する関数
            policy_name: 使用するポリシー名
            *args, **kwargs: 関数の引数
            
        Returns:
            RetryResult: リトライ結果
        """
        policy = self.get_policy(policy_name)
        if not policy:
            raise ValueError(f"未知のポリシー: {policy_name}")
        
        start_time = datetime.now()
        attempts_history = []
        
        # サーキットブレーカーチェック
        if policy.circuit_breaker_enabled:
            circuit_key = f"{policy.name}_{func.__name__}"
            if not self._check_circuit_breaker(circuit_key, policy):
                return RetryResult(
                    success=False,
                    final_exception=Exception("Circuit breaker is OPEN"),
                    total_attempts=0,
                    total_elapsed=0.0,
                    policy_used=policy_name
                )
        
        for attempt in range(1, policy.max_attempts + 1):
            attempt_start = datetime.now()
            
            try:
                # タイムアウト設定
                if policy.timeout_per_attempt:
                    if asyncio.iscoroutinefunction(func):
                        result = await asyncio.wait_for(func(*args, **kwargs), timeout=policy.timeout_per_attempt)
                    else:
                        # 同期関数のタイムアウトは簡略化
                        result = func(*args, **kwargs)
                else:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = func(*args, **kwargs)
                
                # 成功
                total_elapsed = (datetime.now() - start_time).total_seconds()
                
                # サーキットブレーカー成功記録
                if policy.circuit_breaker_enabled:
                    self._record_circuit_breaker_success(circuit_key)
                
                # 統計記録
                retry_result = RetryResult(
                    success=True,
                    final_result=result,
                    total_attempts=attempt,
                    total_elapsed=total_elapsed,
                    attempts_history=attempts_history,
                    policy_used=policy_name
                )
                self._record_retry_statistics(policy_name, retry_result)
                
                return retry_result
                
            except Exception as e:
                total_elapsed = (datetime.now() - start_time).total_seconds()
                
                # エラー情報作成
                error_info = None
                if self.error_handler:
                    error_info = await self.error_handler.handle_error(e, {"retry_attempt": attempt}, func.__name__)
                
                # リトライ可能性判定
                if attempt < policy.max_attempts and policy.is_retryable(e, error_info):
                    delay = policy.calculate_delay(attempt)
                    
                    # 試行記録
                    attempts_history.append(RetryAttempt(
                        attempt_number=attempt,
                        timestamp=attempt_start,
                        exception=e,
                        delay=delay,
                        total_elapsed=total_elapsed
                    ))
                    
                    self.logger.info(f"リトライ実行: {attempt}/{policy.max_attempts}, 遅延: {delay:.2f}秒")
                    
                    # 遅延
                    await asyncio.sleep(delay)
                    
                    # サーキットブレーカー失敗記録
                    if policy.circuit_breaker_enabled:
                        self._record_circuit_breaker_failure(circuit_key, policy)
                    
                else:
                    # リトライ不可または最大試行数到達
                    retry_result = RetryResult(
                        success=False,
                        final_exception=e,
                        total_attempts=attempt,
                        total_elapsed=total_elapsed,
                        attempts_history=attempts_history,
                        policy_used=policy_name
                    )
                    self._record_retry_statistics(policy_name, retry_result)
                    
                    return retry_result
        
        # ここには到達しないはず
        return RetryResult(
            success=False,
            final_exception=Exception("Unexpected end of retry loop"),
            total_attempts=policy.max_attempts,
            total_elapsed=(datetime.now() - start_time).total_seconds(),
            attempts_history=attempts_history,
            policy_used=policy_name
        )
    
    def _check_circuit_breaker(self, circuit_key: str, policy: RetryPolicy) -> bool:
        """サーキットブレーカーチェック"""
        if circuit_key not in self.circuit_breakers:
            self.circuit_breakers[circuit_key] = CircuitBreakerInfo()
        
        circuit_breaker = self.circuit_breakers[circuit_key]
        return circuit_breaker.should_allow_request(
            policy.circuit_breaker_threshold,
            policy.circuit_breaker_timeout
        )
    
    def _record_circuit_breaker_success(self, circuit_key: str):
        """サーキットブレーカー成功記録"""
        if circuit_key in self.circuit_breakers:
            self.circuit_breakers[circuit_key].record_success()
    
    def _record_circuit_breaker_failure(self, circuit_key: str, policy: RetryPolicy):
        """サーキットブレーカー失敗記録"""
        if circuit_key not in self.circuit_breakers:
            self.circuit_breakers[circuit_key] = CircuitBreakerInfo()
        
        self.circuit_breakers[circuit_key].record_failure(policy.circuit_breaker_threshold)
    
    def _record_retry_statistics(self, policy_name: str, result: RetryResult):
        """リトライ統計記録"""
        if policy_name not in self.retry_statistics:
            self.retry_statistics[policy_name] = []
        
        self.retry_statistics[policy_name].append(result)
        
        # 統計データのサイズ制限
        if len(self.retry_statistics[policy_name]) > 100:
            self.retry_statistics[policy_name] = self.retry_statistics[policy_name][-50:]
    
    def retry_with_policy(self, policy_name: str = "general_errors"):
        """リトライデコレータ"""
        def decorator(func: Callable):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                result = await self.execute_with_retry(func, policy_name, *args, **kwargs)
                if result.success:
                    return result.final_result
                else:
                    raise result.final_exception
            
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                # 同期関数の場合はイベントループで実行
                import asyncio
                try:
                    loop = asyncio.get_event_loop()
                    result = loop.run_until_complete(self.execute_with_retry(func, policy_name, *args, **kwargs))
                except RuntimeError:
                    result = asyncio.run(self.execute_with_retry(func, policy_name, *args, **kwargs))
                
                if result.success:
                    return result.final_result
                else:
                    raise result.final_exception
            
            return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
        
        return decorator
    
    def get_retry_statistics(self) -> Dict[str, Any]:
        """リトライ統計を取得"""
        statistics = {}
        
        for policy_name, results in self.retry_statistics.items():
            if not results:
                continue
            
            total_attempts = sum(r.total_attempts for r in results)
            successful_results = [r for r in results if r.success]
            failed_results = [r for r in results if not r.success]
            
            statistics[policy_name] = {
                "total_executions": len(results),
                "successful_executions": len(successful_results),
                "failed_executions": len(failed_results),
                "success_rate": len(successful_results) / len(results) if results else 0,
                "average_attempts": total_attempts / len(results) if results else 0,
                "average_elapsed_time": sum(r.total_elapsed for r in results) / len(results) if results else 0,
                "circuit_breaker_states": {}
            }
        
        # サーキットブレーカー状態
        for circuit_key, circuit_info in self.circuit_breakers.items():
            policy_name = circuit_key.split('_')[0]
            if policy_name in statistics:
                statistics[policy_name]["circuit_breaker_states"][circuit_key] = {
                    "state": circuit_info.state.value,
                    "failure_count": circuit_info.failure_count,
                    "total_requests": circuit_info.total_requests
                }
        
        return statistics
    
    def get_circuit_breaker_status(self) -> Dict[str, Any]:
        """サーキットブレーカー状態を取得"""
        return {
            circuit_key: {
                "state": info.state.value,
                "failure_count": info.failure_count,
                "total_requests": info.total_requests,
                "last_failure": info.last_failure_time.isoformat() if info.last_failure_time else None,
                "last_success": info.last_success_time.isoformat() if info.last_success_time else None
            }
            for circuit_key, info in self.circuit_breakers.items()
        }
    
    def reset_circuit_breaker(self, circuit_key: str) -> bool:
        """サーキットブレーカーをリセット"""
        if circuit_key in self.circuit_breakers:
            self.circuit_breakers[circuit_key] = CircuitBreakerInfo()
            self.logger.info(f"サーキットブレーカーをリセット: {circuit_key}")
            return True
        return False


# グローバルリトライポリシーマネージャー
_global_retry_policy_manager: Optional[RetryPolicyManager] = None


def get_retry_policy_manager(error_handler: Optional[ErrorHandler] = None) -> RetryPolicyManager:
    """グローバルリトライポリシーマネージャーを取得"""
    global _global_retry_policy_manager
    
    if _global_retry_policy_manager is None:
        _global_retry_policy_manager = RetryPolicyManager(error_handler)
    
    return _global_retry_policy_manager


def retry_with_policy(policy_name: str = "general_errors"):
    """リトライデコレータ（グローバルマネージャー使用）"""
    manager = get_retry_policy_manager()
    return manager.retry_with_policy(policy_name)