# -*- coding: utf-8 -*-
"""
Slack通知エラーハンドリングサービス
送信失敗時のリトライ機能、エラー通知機能の実装
"""

import logging
import time
import asyncio
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import json

from src.services.slack_service import SlackService, SlackMessage, SlackResponse, MessageType, Priority
from src.services.retry_manager import RetryManager, RetryConfig, RetryReason


logger = logging.getLogger(__name__)


class NotificationErrorType(Enum):
    """通知エラータイプ"""
    NETWORK_ERROR = "network_error"
    RATE_LIMIT = "rate_limit"
    WEBHOOK_INVALID = "webhook_invalid"
    MESSAGE_TOO_LARGE = "message_too_large"
    CHANNEL_NOT_FOUND = "channel_not_found"
    PERMISSION_DENIED = "permission_denied"
    SERVICE_UNAVAILABLE = "service_unavailable"
    TIMEOUT = "timeout"
    UNKNOWN_ERROR = "unknown_error"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            NotificationErrorType.NETWORK_ERROR: "ネットワークエラー",
            NotificationErrorType.RATE_LIMIT: "レート制限",
            NotificationErrorType.WEBHOOK_INVALID: "Webhook無効",
            NotificationErrorType.MESSAGE_TOO_LARGE: "メッセージサイズ超過",
            NotificationErrorType.CHANNEL_NOT_FOUND: "チャンネル未発見",
            NotificationErrorType.PERMISSION_DENIED: "権限不足",
            NotificationErrorType.SERVICE_UNAVAILABLE: "サービス利用不可",
            NotificationErrorType.TIMEOUT: "タイムアウト",
            NotificationErrorType.UNKNOWN_ERROR: "不明なエラー"
        }[self]

    @property
    def is_retryable(self) -> bool:
        """リトライ可能か"""
        return self in [
            NotificationErrorType.NETWORK_ERROR,
            NotificationErrorType.RATE_LIMIT,
            NotificationErrorType.SERVICE_UNAVAILABLE,
            NotificationErrorType.TIMEOUT
        ]


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


@dataclass
class NotificationError:
    """通知エラー"""
    error_type: NotificationErrorType
    severity: ErrorSeverity
    message: str
    timestamp: datetime
    original_message: SlackMessage
    attempt_count: int
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "error_type": self.error_type.value,
            "severity": self.severity.value,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
            "attempt_count": self.attempt_count,
            "context": self.context,
            "stack_trace": self.stack_trace
        }


@dataclass
class NotificationResult:
    """通知結果"""
    success: bool
    response: Optional[SlackResponse] = None
    error: Optional[NotificationError] = None
    total_attempts: int = 1
    total_time: float = 0.0
    fallback_used: bool = False

    @property
    def should_escalate(self) -> bool:
        """エスカレーションが必要か"""
        return (not self.success and 
                self.error and 
                self.error.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL])


@dataclass
class FallbackStrategy:
    """フォールバック戦略"""
    enabled: bool = True
    max_message_length: int = 1000
    simplify_attachments: bool = True
    use_simple_format: bool = True
    alternative_channels: List[str] = field(default_factory=list)


@dataclass
class NotificationConfig:
    """通知設定"""
    max_retries: int = 3
    retry_delay_base: float = 1.0
    retry_delay_max: float = 30.0
    rate_limit_delay: float = 5.0
    timeout_seconds: float = 30.0
    fallback_strategy: FallbackStrategy = field(default_factory=FallbackStrategy)
    escalation_enabled: bool = True
    escalation_channels: List[str] = field(default_factory=list)
    log_errors: bool = True


class SlackNotificationErrorHandler:
    """Slack通知エラーハンドリングサービス"""
    
    def __init__(self, 
                 slack_service: SlackService,
                 config: NotificationConfig,
                 retry_manager: Optional[RetryManager] = None):
        """
        Args:
            slack_service: Slackサービス
            config: 通知設定
            retry_manager: リトライマネージャー
        """
        self.slack_service = slack_service
        self.config = config
        self.retry_manager = retry_manager or RetryManager(RetryConfig(
            max_attempts=config.max_retries,
            initial_delay=config.retry_delay_base,
            max_delay=config.retry_delay_max
        ))
        self.logger = logging.getLogger(__name__)
        
        # エラー統計
        self.error_stats = {
            "total_attempts": 0,
            "successful_sends": 0,
            "failed_sends": 0,
            "fallback_uses": 0,
            "escalations": 0,
            "error_types": {}
        }
        
        # エラー分類マッピング
        self.error_classification = {
            429: (NotificationErrorType.RATE_LIMIT, ErrorSeverity.MEDIUM),
            404: (NotificationErrorType.WEBHOOK_INVALID, ErrorSeverity.HIGH),
            403: (NotificationErrorType.PERMISSION_DENIED, ErrorSeverity.HIGH),
            413: (NotificationErrorType.MESSAGE_TOO_LARGE, ErrorSeverity.MEDIUM),
            503: (NotificationErrorType.SERVICE_UNAVAILABLE, ErrorSeverity.MEDIUM),
            408: (NotificationErrorType.TIMEOUT, ErrorSeverity.MEDIUM),
        }
    
    async def send_notification_with_error_handling(self, message: SlackMessage) -> NotificationResult:
        """
        エラーハンドリング付きで通知を送信
        
        Args:
            message: Slackメッセージ
            
        Returns:
            NotificationResult: 通知結果
        """
        start_time = time.time()
        self.error_stats["total_attempts"] += 1
        
        self.logger.info(f"Slack通知送信開始: {message.message_type.value}")
        
        # 基本的な送信試行
        result = await self._attempt_notification_with_retries(message)
        
        # 失敗した場合のフォールバック処理
        if not result.success and self.config.fallback_strategy.enabled:
            self.logger.warning("基本送信失敗、フォールバック戦略を実行")
            fallback_result = await self._execute_fallback_strategy(message, result.error)
            
            if fallback_result.success:
                result = fallback_result
                result.fallback_used = True
                self.error_stats["fallback_uses"] += 1
        
        # エスカレーション処理
        if result.should_escalate and self.config.escalation_enabled:
            await self._escalate_notification_failure(message, result.error)
            self.error_stats["escalations"] += 1
        
        # 統計更新
        result.total_time = time.time() - start_time
        if result.success:
            self.error_stats["successful_sends"] += 1
        else:
            self.error_stats["failed_sends"] += 1
            if result.error:
                error_type = result.error.error_type.value
                self.error_stats["error_types"][error_type] = self.error_stats["error_types"].get(error_type, 0) + 1
        
        # エラーログ記録
        if not result.success and self.config.log_errors:
            self._log_notification_error(result.error)
        
        self.logger.info(f"通知送信完了: 成功={result.success}, 試行回数={result.total_attempts}, 時間={result.total_time:.2f}秒")
        return result
    
    async def _attempt_notification_with_retries(self, message: SlackMessage) -> NotificationResult:
        """リトライ付きで通知を試行"""
        last_error = None
        
        for attempt in range(1, self.config.max_retries + 1):
            try:
                self.logger.debug(f"通知試行 {attempt}/{self.config.max_retries}")
                
                # レート制限対応の待機
                if attempt > 1 and last_error and last_error.error_type == NotificationErrorType.RATE_LIMIT:
                    await asyncio.sleep(self.config.rate_limit_delay)
                
                # Slack送信実行
                response = await self._safe_slack_send(message)
                
                if response.success:
                    return NotificationResult(
                        success=True,
                        response=response,
                        total_attempts=attempt
                    )
                
                # エラー分析
                error = self._analyze_slack_error(response, message, attempt)
                last_error = error
                
                # リトライ不可能なエラーの場合は即座に終了
                if not error.error_type.is_retryable:
                    return NotificationResult(
                        success=False,
                        error=error,
                        total_attempts=attempt
                    )
                
                # リトライ待機
                if attempt < self.config.max_retries:
                    delay = min(
                        self.config.retry_delay_base * (2 ** (attempt - 1)),
                        self.config.retry_delay_max
                    )
                    self.logger.debug(f"リトライ前待機: {delay}秒")
                    await asyncio.sleep(delay)
                
            except Exception as e:
                last_error = NotificationError(
                    error_type=NotificationErrorType.UNKNOWN_ERROR,
                    severity=ErrorSeverity.HIGH,
                    message=str(e),
                    timestamp=datetime.now(),
                    original_message=message,
                    attempt_count=attempt,
                    stack_trace=str(e)
                )
        
        return NotificationResult(
            success=False,
            error=last_error,
            total_attempts=self.config.max_retries
        )
    
    async def _safe_slack_send(self, message: SlackMessage) -> SlackResponse:
        """安全なSlack送信"""
        try:
            if asyncio.iscoroutinefunction(self.slack_service.send_message):
                return await self.slack_service.send_message(message)
            else:
                return self.slack_service.send_message(message)
        except Exception as e:
            return SlackResponse(
                success=False,
                error_message=str(e)
            )
    
    def _analyze_slack_error(self, response: SlackResponse, message: SlackMessage, attempt: int) -> NotificationError:
        """Slackエラーを分析"""
        error_type = NotificationErrorType.UNKNOWN_ERROR
        severity = ErrorSeverity.MEDIUM
        
        # ステータスコードベースの分類
        if response.status_code in self.error_classification:
            error_type, severity = self.error_classification[response.status_code]
        elif response.is_rate_limited:
            error_type = NotificationErrorType.RATE_LIMIT
            severity = ErrorSeverity.MEDIUM
        elif response.error_message:
            # エラーメッセージベースの分類
            error_msg_lower = response.error_message.lower()
            if "network" in error_msg_lower or "connection" in error_msg_lower:
                error_type = NotificationErrorType.NETWORK_ERROR
                severity = ErrorSeverity.MEDIUM
            elif "timeout" in error_msg_lower:
                error_type = NotificationErrorType.TIMEOUT
                severity = ErrorSeverity.MEDIUM
            elif "channel" in error_msg_lower:
                error_type = NotificationErrorType.CHANNEL_NOT_FOUND
                severity = ErrorSeverity.HIGH
        
        return NotificationError(
            error_type=error_type,
            severity=severity,
            message=response.error_message or "Unknown error",
            timestamp=datetime.now(),
            original_message=message,
            attempt_count=attempt,
            context={
                "status_code": response.status_code,
                "response_time": response.response_time
            }
        )
    
    async def _execute_fallback_strategy(self, 
                                       original_message: SlackMessage, 
                                       error: Optional[NotificationError]) -> NotificationResult:
        """フォールバック戦略を実行"""
        fallback = self.config.fallback_strategy
        
        try:
            # メッセージの簡素化
            simplified_message = self._create_simplified_message(original_message, fallback)
            
            # 代替チャンネルでの送信試行
            for channel in fallback.alternative_channels:
                self.logger.info(f"代替チャンネル {channel} での送信を試行")
                simplified_message.channel = channel
                
                response = await self._safe_slack_send(simplified_message)
                if response.success:
                    return NotificationResult(
                        success=True,
                        response=response,
                        total_attempts=1,
                        fallback_used=True
                    )
            
            # 元のチャンネルで簡素化メッセージを送信
            simplified_message.channel = original_message.channel
            response = await self._safe_slack_send(simplified_message)
            
            return NotificationResult(
                success=response.success,
                response=response if response.success else None,
                error=error,
                total_attempts=1,
                fallback_used=True
            )
            
        except Exception as e:
            self.logger.error(f"フォールバック戦略実行エラー: {e}")
            return NotificationResult(
                success=False,
                error=NotificationError(
                    error_type=NotificationErrorType.UNKNOWN_ERROR,
                    severity=ErrorSeverity.HIGH,
                    message=f"フォールバック戦略失敗: {str(e)}",
                    timestamp=datetime.now(),
                    original_message=original_message,
                    attempt_count=1
                ),
                total_attempts=1
            )
    
    def _create_simplified_message(self, message: SlackMessage, fallback: FallbackStrategy) -> SlackMessage:
        """簡素化メッセージを作成"""
        simplified = SlackMessage(
            text=message.text,
            message_type=message.message_type,
            priority=message.priority,
            channel=message.channel,
            username=message.username,
            icon_emoji=message.icon_emoji
        )
        
        # テキスト長制限
        if len(simplified.text) > fallback.max_message_length:
            simplified.text = simplified.text[:fallback.max_message_length-3] + "..."
        
        # 添付ファイルの簡素化
        if not fallback.simplify_attachments and message.attachments:
            # 最初の添付ファイルのみ保持
            simplified.attachments = [message.attachments[0]]
            
            # フィールド数制限
            if simplified.attachments[0].fields and len(simplified.attachments[0].fields) > 3:
                simplified.attachments[0].fields = simplified.attachments[0].fields[:3]
        
        # シンプルフォーマット使用
        if fallback.use_simple_format:
            simplified.attachments = []
            simplified.blocks = []
        
        return simplified
    
    async def _escalate_notification_failure(self, 
                                           original_message: SlackMessage, 
                                           error: Optional[NotificationError]):
        """通知失敗をエスカレーション"""
        if not self.config.escalation_channels:
            return
        
        escalation_text = f":rotating_light: 通知送信に失敗しました\n"
        escalation_text += f"エラータイプ: {error.error_type.display_name if error else '不明'}\n"
        escalation_text += f"重要度: {error.severity.display_name if error else '不明'}\n"
        escalation_text += f"元メッセージ: {original_message.text[:100]}..."
        
        escalation_message = SlackMessage(
            text=escalation_text,
            message_type=MessageType.ERROR,
            priority=Priority.CRITICAL
        )
        
        for channel in self.config.escalation_channels:
            try:
                escalation_message.channel = channel
                await self._safe_slack_send(escalation_message)
            except Exception as e:
                self.logger.error(f"エスカレーション送信失敗 ({channel}): {e}")
    
    def _log_notification_error(self, error: Optional[NotificationError]):
        """通知エラーをログに記録"""
        if not error:
            return
        
        log_data = {
            "error_type": error.error_type.value,
            "severity": error.severity.value,
            "message": error.message,
            "timestamp": error.timestamp.isoformat(),
            "attempt_count": error.attempt_count,
            "context": error.context
        }
        
        if error.severity in [ErrorSeverity.HIGH, ErrorSeverity.CRITICAL]:
            self.logger.error(f"Slack通知エラー: {json.dumps(log_data, ensure_ascii=False, indent=2)}")
        else:
            self.logger.warning(f"Slack通知警告: {json.dumps(log_data, ensure_ascii=False, indent=2)}")
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """エラー統計を取得"""
        total_attempts = self.error_stats["total_attempts"]
        if total_attempts == 0:
            return {"message": "統計データなし"}
        
        success_rate = (self.error_stats["successful_sends"] / total_attempts) * 100
        failure_rate = (self.error_stats["failed_sends"] / total_attempts) * 100
        fallback_rate = (self.error_stats["fallback_uses"] / total_attempts) * 100
        
        return {
            "total_attempts": total_attempts,
            "successful_sends": self.error_stats["successful_sends"],
            "failed_sends": self.error_stats["failed_sends"],
            "success_rate": f"{success_rate:.2f}%",
            "failure_rate": f"{failure_rate:.2f}%",
            "fallback_uses": self.error_stats["fallback_uses"],
            "fallback_rate": f"{fallback_rate:.2f}%",
            "escalations": self.error_stats["escalations"],
            "error_types": self.error_stats["error_types"]
        }
    
    def reset_error_statistics(self):
        """エラー統計をリセット"""
        self.error_stats = {
            "total_attempts": 0,
            "successful_sends": 0,
            "failed_sends": 0,
            "fallback_uses": 0,
            "escalations": 0,
            "error_types": {}
        }
        self.logger.info("エラー統計をリセットしました")