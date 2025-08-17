# -*- coding: utf-8 -*-
"""
包括的エラーハンドリングサービス
ErrorHandlerクラスの実装、エラータイプ別の処理戦略を提供
"""

import logging
import traceback
import sys
import asyncio
from typing import Dict, List, Optional, Any, Callable, Type, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json
import inspect
from contextlib import asynccontextmanager, contextmanager

from src.services.cloudwatch_service import StructuredLogger, LogLevel
from src.services.slack_service import SlackService, SlackMessage, MessageType, Priority
from src.services.retry_manager import RetryManager, RetryConfig


logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """エラー重要度"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            ErrorSeverity.LOW: "軽微",
            ErrorSeverity.MEDIUM: "中程度",
            ErrorSeverity.HIGH: "重大",
            ErrorSeverity.CRITICAL: "致命的"
        }[self]

    @property
    def log_level(self) -> LogLevel:
        """対応するログレベル"""
        return {
            ErrorSeverity.LOW: LogLevel.WARNING,
            ErrorSeverity.MEDIUM: LogLevel.ERROR,
            ErrorSeverity.HIGH: LogLevel.ERROR,
            ErrorSeverity.CRITICAL: LogLevel.CRITICAL
        }[self]


class ErrorCategory(Enum):
    """エラーカテゴリ"""
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    NETWORK = "network"
    DATA_VALIDATION = "data_validation"
    API_ERROR = "api_error"
    CONFIGURATION = "configuration"
    BUSINESS_LOGIC = "business_logic"
    SYSTEM_ERROR = "system_error"
    EXTERNAL_SERVICE = "external_service"
    TIMEOUT = "timeout"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    UNKNOWN = "unknown"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            ErrorCategory.AUTHENTICATION: "認証エラー",
            ErrorCategory.AUTHORIZATION: "認可エラー",
            ErrorCategory.NETWORK: "ネットワークエラー",
            ErrorCategory.DATA_VALIDATION: "データ検証エラー",
            ErrorCategory.API_ERROR: "API呼び出しエラー",
            ErrorCategory.CONFIGURATION: "設定エラー",
            ErrorCategory.BUSINESS_LOGIC: "ビジネスロジックエラー",
            ErrorCategory.SYSTEM_ERROR: "システムエラー",
            ErrorCategory.EXTERNAL_SERVICE: "外部サービスエラー",
            ErrorCategory.TIMEOUT: "タイムアウトエラー",
            ErrorCategory.RESOURCE_EXHAUSTION: "リソース不足エラー",
            ErrorCategory.UNKNOWN: "不明なエラー"
        }[self]


class ErrorHandlingStrategy(Enum):
    """エラー処理戦略"""
    IGNORE = "ignore"
    LOG_ONLY = "log_only"
    RETRY = "retry"
    FALLBACK = "fallback"
    ESCALATE = "escalate"
    ABORT = "abort"
    CIRCUIT_BREAKER = "circuit_breaker"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            ErrorHandlingStrategy.IGNORE: "無視",
            ErrorHandlingStrategy.LOG_ONLY: "ログのみ",
            ErrorHandlingStrategy.RETRY: "リトライ",
            ErrorHandlingStrategy.FALLBACK: "フォールバック",
            ErrorHandlingStrategy.ESCALATE: "エスカレーション",
            ErrorHandlingStrategy.ABORT: "中断",
            ErrorHandlingStrategy.CIRCUIT_BREAKER: "サーキットブレーカー"
        }[self]


@dataclass
class ErrorInfo:
    """エラー情報"""
    error_id: str
    timestamp: datetime
    exception: Exception
    error_type: str
    error_message: str
    category: ErrorCategory
    severity: ErrorSeverity
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None
    source_function: Optional[str] = None
    source_file: Optional[str] = None
    source_line: Optional[int] = None
    handled: bool = False
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "error_id": self.error_id,
            "timestamp": self.timestamp.isoformat(),
            "error_type": self.error_type,
            "error_message": self.error_message,
            "category": self.category.value,
            "severity": self.severity.value,
            "context": self.context,
            "stack_trace": self.stack_trace,
            "source_function": self.source_function,
            "source_file": self.source_file,
            "source_line": self.source_line,
            "handled": self.handled,
            "retry_count": self.retry_count
        }


@dataclass
class ErrorHandlingConfig:
    """エラーハンドリング設定"""
    enable_logging: bool = True
    enable_notifications: bool = True
    enable_metrics: bool = True
    enable_circuit_breaker: bool = True
    max_error_history: int = 1000
    notification_threshold: int = 5
    escalation_threshold: int = 10
    circuit_breaker_threshold: int = 10
    circuit_breaker_timeout: int = 300
    retry_config: Optional[RetryConfig] = None

    def __post_init__(self):
        if self.retry_config is None:
            self.retry_config = RetryConfig(
                max_attempts=3,
                initial_delay=1.0,
                max_delay=30.0
            )


@dataclass
class ErrorHandlingRule:
    """エラーハンドリングルール"""
    error_types: List[str]
    categories: List[ErrorCategory]
    strategy: ErrorHandlingStrategy
    severity: ErrorSeverity
    max_retries: int = 3
    fallback_function: Optional[Callable] = None
    escalation_required: bool = False
    circuit_breaker_enabled: bool = False

    def matches(self, error_info: ErrorInfo) -> bool:
        """エラー情報がルールにマッチするか判定"""
        type_match = not self.error_types or error_info.error_type in self.error_types
        category_match = not self.categories or error_info.category in self.categories
        return type_match and category_match


class CircuitBreaker:
    """サーキットブレーカー"""
    
    def __init__(self, failure_threshold: int = 5, timeout: int = 60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func: Callable, *args, **kwargs):
        """関数呼び出し（サーキットブレーカー付き）"""
        if self.state == "OPEN":
            if self._should_attempt_reset():
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
    
    def _should_attempt_reset(self) -> bool:
        """リセット試行すべきか判定"""
        if self.last_failure_time is None:
            return True
        return (datetime.now() - self.last_failure_time).total_seconds() > self.timeout
    
    def _on_success(self):
        """成功時の処理"""
        self.failure_count = 0
        self.state = "CLOSED"
    
    def _on_failure(self):
        """失敗時の処理"""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"


class ErrorHandler:
    """包括的エラーハンドラー"""
    
    def __init__(self,
                 config: ErrorHandlingConfig,
                 structured_logger: Optional[StructuredLogger] = None,
                 slack_service: Optional[SlackService] = None,
                 retry_manager: Optional[RetryManager] = None):
        """
        Args:
            config: エラーハンドリング設定
            structured_logger: 構造化ログ
            slack_service: Slack通知サービス
            retry_manager: リトライマネージャー
        """
        self.config = config
        self.structured_logger = structured_logger
        self.slack_service = slack_service
        self.retry_manager = retry_manager or RetryManager(config.retry_config)
        self.logger = logging.getLogger(__name__)
        
        # エラー履歴と統計
        self.error_history: List[ErrorInfo] = []
        self.error_counts: Dict[str, int] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        
        # エラーハンドリングルール
        self.handling_rules = self._initialize_default_rules()
        
        # エラー分類マッピング
        self.error_classification = self._initialize_error_classification()
    
    def _initialize_default_rules(self) -> List[ErrorHandlingRule]:
        """デフォルトルールを初期化"""
        return [
            # 認証・認可エラー
            ErrorHandlingRule(
                error_types=["AuthenticationError", "UnauthorizedError", "PermissionError"],
                categories=[ErrorCategory.AUTHENTICATION, ErrorCategory.AUTHORIZATION],
                strategy=ErrorHandlingStrategy.ESCALATE,
                severity=ErrorSeverity.HIGH,
                escalation_required=True
            ),
            
            # ネットワークエラー
            ErrorHandlingRule(
                error_types=["ConnectionError", "NetworkError", "TimeoutError"],
                categories=[ErrorCategory.NETWORK, ErrorCategory.TIMEOUT],
                strategy=ErrorHandlingStrategy.RETRY,
                severity=ErrorSeverity.MEDIUM,
                max_retries=3
            ),
            
            # データ検証エラー
            ErrorHandlingRule(
                error_types=["ValidationError", "ValueError", "TypeError"],
                categories=[ErrorCategory.DATA_VALIDATION],
                strategy=ErrorHandlingStrategy.LOG_ONLY,
                severity=ErrorSeverity.MEDIUM
            ),
            
            # API エラー
            ErrorHandlingRule(
                error_types=["APIError", "HTTPError", "RequestException"],
                categories=[ErrorCategory.API_ERROR, ErrorCategory.EXTERNAL_SERVICE],
                strategy=ErrorHandlingStrategy.RETRY,
                severity=ErrorSeverity.MEDIUM,
                max_retries=2,
                circuit_breaker_enabled=True
            ),
            
            # システムエラー
            ErrorHandlingRule(
                error_types=["SystemError", "MemoryError", "OSError"],
                categories=[ErrorCategory.SYSTEM_ERROR, ErrorCategory.RESOURCE_EXHAUSTION],
                strategy=ErrorHandlingStrategy.ESCALATE,
                severity=ErrorSeverity.CRITICAL,
                escalation_required=True
            ),
            
            # 設定エラー
            ErrorHandlingRule(
                error_types=["ConfigurationError", "FileNotFoundError"],
                categories=[ErrorCategory.CONFIGURATION],
                strategy=ErrorHandlingStrategy.FALLBACK,
                severity=ErrorSeverity.HIGH
            ),
            
            # 一般的なエラー
            ErrorHandlingRule(
                error_types=["Exception"],
                categories=[ErrorCategory.UNKNOWN],
                strategy=ErrorHandlingStrategy.LOG_ONLY,
                severity=ErrorSeverity.MEDIUM
            )
        ]
    
    def _initialize_error_classification(self) -> Dict[str, ErrorCategory]:
        """エラー分類マッピングを初期化"""
        return {
            "AuthenticationError": ErrorCategory.AUTHENTICATION,
            "UnauthorizedError": ErrorCategory.AUTHORIZATION,
            "PermissionError": ErrorCategory.AUTHORIZATION,
            "ConnectionError": ErrorCategory.NETWORK,
            "NetworkError": ErrorCategory.NETWORK,
            "TimeoutError": ErrorCategory.TIMEOUT,
            "HTTPError": ErrorCategory.API_ERROR,
            "RequestException": ErrorCategory.API_ERROR,
            "ValidationError": ErrorCategory.DATA_VALIDATION,
            "ValueError": ErrorCategory.DATA_VALIDATION,
            "TypeError": ErrorCategory.DATA_VALIDATION,
            "ConfigurationError": ErrorCategory.CONFIGURATION,
            "FileNotFoundError": ErrorCategory.CONFIGURATION,
            "SystemError": ErrorCategory.SYSTEM_ERROR,
            "MemoryError": ErrorCategory.RESOURCE_EXHAUSTION,
            "OSError": ErrorCategory.SYSTEM_ERROR
        }
    
    async def handle_error(self, 
                          exception: Exception, 
                          context: Optional[Dict[str, Any]] = None,
                          function_name: Optional[str] = None) -> ErrorInfo:
        """
        エラーを処理
        
        Args:
            exception: 発生した例外
            context: エラーコンテキスト
            function_name: エラーが発生した関数名
            
        Returns:
            ErrorInfo: エラー情報
        """
        # エラー情報作成
        error_info = self._create_error_info(exception, context, function_name)
        
        # エラー処理戦略決定
        handling_rule = self._find_matching_rule(error_info)
        
        # 戦略実行
        await self._execute_handling_strategy(error_info, handling_rule)
        
        # エラー履歴記録
        self._record_error(error_info)
        
        return error_info
    
    def _create_error_info(self, 
                          exception: Exception, 
                          context: Optional[Dict[str, Any]] = None,
                          function_name: Optional[str] = None) -> ErrorInfo:
        """エラー情報を作成"""
        error_type = type(exception).__name__
        error_message = str(exception)
        
        # カテゴリ分類
        category = self.error_classification.get(error_type, ErrorCategory.UNKNOWN)
        
        # 重要度判定
        severity = self._determine_severity(error_type, category, exception)
        
        # スタックトレース取得
        stack_trace = traceback.format_exc()
        
        # ソース情報取得
        source_info = self._get_source_info()
        
        # エラーID生成
        error_id = f"ERR_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{hash(error_message) % 10000:04d}"
        
        return ErrorInfo(
            error_id=error_id,
            timestamp=datetime.now(),
            exception=exception,
            error_type=error_type,
            error_message=error_message,
            category=category,
            severity=severity,
            context=context or {},
            stack_trace=stack_trace,
            source_function=function_name or source_info.get("function"),
            source_file=source_info.get("file"),
            source_line=source_info.get("line")
        )
    
    def _determine_severity(self, error_type: str, category: ErrorCategory, exception: Exception) -> ErrorSeverity:
        """エラー重要度を判定"""
        # カテゴリベースの判定
        category_severity = {
            ErrorCategory.AUTHENTICATION: ErrorSeverity.HIGH,
            ErrorCategory.AUTHORIZATION: ErrorSeverity.HIGH,
            ErrorCategory.SYSTEM_ERROR: ErrorSeverity.CRITICAL,
            ErrorCategory.RESOURCE_EXHAUSTION: ErrorSeverity.CRITICAL,
            ErrorCategory.CONFIGURATION: ErrorSeverity.HIGH,
            ErrorCategory.NETWORK: ErrorSeverity.MEDIUM,
            ErrorCategory.API_ERROR: ErrorSeverity.MEDIUM,
            ErrorCategory.DATA_VALIDATION: ErrorSeverity.MEDIUM,
            ErrorCategory.BUSINESS_LOGIC: ErrorSeverity.LOW,
            ErrorCategory.TIMEOUT: ErrorSeverity.MEDIUM,
            ErrorCategory.EXTERNAL_SERVICE: ErrorSeverity.MEDIUM,
            ErrorCategory.UNKNOWN: ErrorSeverity.MEDIUM
        }
        
        return category_severity.get(category, ErrorSeverity.MEDIUM)
    
    def _get_source_info(self) -> Dict[str, Any]:
        """ソース情報を取得"""
        try:
            frame = inspect.currentframe()
            # エラーハンドラー内のフレームをスキップ
            while frame and frame.f_code.co_filename == __file__:
                frame = frame.f_back
            
            if frame:
                return {
                    "function": frame.f_code.co_name,
                    "file": frame.f_code.co_filename,
                    "line": frame.f_lineno
                }
        except Exception:
            pass
        
        return {}
    
    def _find_matching_rule(self, error_info: ErrorInfo) -> Optional[ErrorHandlingRule]:
        """マッチするルールを検索"""
        for rule in self.handling_rules:
            if rule.matches(error_info):
                return rule
        return None
    
    async def _execute_handling_strategy(self, error_info: ErrorInfo, rule: Optional[ErrorHandlingRule]):
        """ハンドリング戦略を実行"""
        if not rule:
            # デフォルト戦略
            await self._log_error(error_info)
            return
        
        strategy = rule.strategy
        error_info.handled = True
        
        if strategy == ErrorHandlingStrategy.IGNORE:
            pass  # 何もしない
        
        elif strategy == ErrorHandlingStrategy.LOG_ONLY:
            await self._log_error(error_info)
        
        elif strategy == ErrorHandlingStrategy.RETRY:
            await self._handle_retry(error_info, rule)
        
        elif strategy == ErrorHandlingStrategy.FALLBACK:
            await self._handle_fallback(error_info, rule)
        
        elif strategy == ErrorHandlingStrategy.ESCALATE:
            await self._handle_escalation(error_info, rule)
        
        elif strategy == ErrorHandlingStrategy.ABORT:
            await self._handle_abort(error_info, rule)
        
        elif strategy == ErrorHandlingStrategy.CIRCUIT_BREAKER:
            await self._handle_circuit_breaker(error_info, rule)
        
        # 共通処理
        if self.config.enable_logging:
            await self._log_error(error_info)
        
        if self.config.enable_notifications and error_info.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            await self._send_notification(error_info)
    
    async def _log_error(self, error_info: ErrorInfo):
        """エラーログ記録"""
        log_context = error_info.to_dict()
        
        if self.structured_logger:
            await self.structured_logger.log_structured(
                level=error_info.severity.log_level,
                message=f"エラー発生: {error_info.error_message}",
                context=log_context
            )
        
        # 標準ログにも記録
        self.logger.log(
            level=logging.ERROR if error_info.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL] else logging.WARNING,
            msg=f"[{error_info.error_id}] {error_info.category.display_name}: {error_info.error_message}",
            extra=log_context
        )
    
    async def _send_notification(self, error_info: ErrorInfo):
        """エラー通知送信"""
        if not self.slack_service:
            return
        
        try:
            error_context = {
                "error_id": error_info.error_id,
                "error_type": error_info.error_type,
                "category": error_info.category.display_name,
                "severity": error_info.severity.display_name,
                "source": error_info.source_function or "Unknown",
                "timestamp": error_info.timestamp.isoformat()
            }
            
            priority = Priority.CRITICAL if error_info.severity == ErrorSeverity.CRITICAL else Priority.HIGH
            
            response = self.slack_service.send_error_notification(
                error_info.error_message,
                error_context,
                priority
            )
            
            if not response.success:
                self.logger.warning(f"エラー通知送信失敗: {response.error_message}")
                
        except Exception as e:
            self.logger.error(f"エラー通知送信中にエラー: {e}")
    
    async def _handle_retry(self, error_info: ErrorInfo, rule: ErrorHandlingRule):
        """リトライ処理"""
        # リトライカウント更新
        error_info.retry_count += 1
        
        # 最大リトライ数チェック
        if error_info.retry_count >= rule.max_retries:
            self.logger.warning(f"最大リトライ数に到達: {error_info.error_id}")
            return
        
        # リトライマネージャーでの処理は呼び出し元で実装
        self.logger.info(f"リトライ対象エラー: {error_info.error_id} (試行回数: {error_info.retry_count})")
    
    async def _handle_fallback(self, error_info: ErrorInfo, rule: ErrorHandlingRule):
        """フォールバック処理"""
        if rule.fallback_function:
            try:
                result = rule.fallback_function()
                self.logger.info(f"フォールバック実行成功: {error_info.error_id}")
                return result
            except Exception as e:
                self.logger.error(f"フォールバック実行失敗: {error_info.error_id}, {e}")
        
        self.logger.warning(f"フォールバック関数が設定されていません: {error_info.error_id}")
    
    async def _handle_escalation(self, error_info: ErrorInfo, rule: ErrorHandlingRule):
        """エスカレーション処理"""
        self.logger.critical(f"エラーエスカレーション: {error_info.error_id}")
        
        # 管理者への通知などの実装
        if self.slack_service:
            escalation_message = f"重大エラーのエスカレーション\nエラーID: {error_info.error_id}\n詳細: {error_info.error_message}"
            await self.slack_service.send_alert(
                "システムエラーエスカレーション",
                escalation_message,
                Priority.CRITICAL,
                mention_channel=True
            )
    
    async def _handle_abort(self, error_info: ErrorInfo, rule: ErrorHandlingRule):
        """処理中断"""
        self.logger.critical(f"処理中断: {error_info.error_id}")
        # 中断ロジックは呼び出し元で実装
    
    async def _handle_circuit_breaker(self, error_info: ErrorInfo, rule: ErrorHandlingRule):
        """サーキットブレーカー処理"""
        circuit_key = f"{error_info.source_function}_{error_info.error_type}"
        
        if circuit_key not in self.circuit_breakers:
            self.circuit_breakers[circuit_key] = CircuitBreaker(
                failure_threshold=self.config.circuit_breaker_threshold,
                timeout=self.config.circuit_breaker_timeout
            )
        
        circuit_breaker = self.circuit_breakers[circuit_key]
        circuit_breaker._on_failure()  # エラーを記録
        
        self.logger.warning(f"サーキットブレーカー状態: {circuit_breaker.state} ({circuit_key})")
    
    def _record_error(self, error_info: ErrorInfo):
        """エラー履歴記録"""
        self.error_history.append(error_info)
        
        # 履歴サイズ制限
        if len(self.error_history) > self.config.max_error_history:
            self.error_history = self.error_history[-self.config.max_error_history//2:]
        
        # エラー統計更新
        error_key = f"{error_info.category.value}_{error_info.error_type}"
        self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
    
    def add_handling_rule(self, rule: ErrorHandlingRule):
        """ハンドリングルールを追加"""
        self.handling_rules.insert(0, rule)  # 先頭に追加（優先度高）
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """エラー統計を取得"""
        if not self.error_history:
            return {"message": "エラー履歴なし"}
        
        recent_errors = [e for e in self.error_history 
                        if (datetime.now() - e.timestamp).total_seconds() < 3600]  # 過去1時間
        
        severity_counts = {}
        category_counts = {}
        
        for error in self.error_history:
            severity_counts[error.severity.value] = severity_counts.get(error.severity.value, 0) + 1
            category_counts[error.category.value] = category_counts.get(error.category.value, 0) + 1
        
        return {
            "total_errors": len(self.error_history),
            "recent_errors_count": len(recent_errors),
            "severity_distribution": severity_counts,
            "category_distribution": category_counts,
            "error_counts": self.error_counts,
            "circuit_breaker_states": {k: v.state for k, v in self.circuit_breakers.items()}
        }
    
    @asynccontextmanager
    async def error_context(self, 
                           context_name: str, 
                           context_data: Optional[Dict[str, Any]] = None,
                           reraise: bool = True):
        """エラーコンテキストマネージャー"""
        try:
            yield
        except Exception as e:
            error_context = {"context_name": context_name}
            if context_data:
                error_context.update(context_data)
            
            await self.handle_error(e, error_context, context_name)
            
            if reraise:
                raise
    
    @contextmanager
    def sync_error_context(self, 
                          context_name: str, 
                          context_data: Optional[Dict[str, Any]] = None,
                          reraise: bool = True):
        """同期エラーコンテキストマネージャー"""
        try:
            yield
        except Exception as e:
            error_context = {"context_name": context_name}
            if context_data:
                error_context.update(context_data)
            
            # 非同期処理を同期的に実行
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.run_until_complete(self.handle_error(e, error_context, context_name))
            except RuntimeError:
                # イベントループが実行中の場合は、新しいループで実行
                asyncio.run(self.handle_error(e, error_context, context_name))
            
            if reraise:
                raise


def error_handler_decorator(error_handler: ErrorHandler, 
                          context_name: Optional[str] = None,
                          reraise: bool = True):
    """エラーハンドラーデコレータ"""
    def decorator(func: Callable):
        context = context_name or func.__name__
        
        if asyncio.iscoroutinefunction(func):
            async def async_wrapper(*args, **kwargs):
                async with error_handler.error_context(context, reraise=reraise):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            def sync_wrapper(*args, **kwargs):
                with error_handler.sync_error_context(context, reraise=reraise):
                    return func(*args, **kwargs)
            return sync_wrapper
    
    return decorator