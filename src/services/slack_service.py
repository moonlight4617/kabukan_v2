# -*- coding: utf-8 -*-
"""
Slack通知サービス
Slack Webhook APIとの統合、メッセージ送信機能を提供
"""

import logging
import json
import time
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from src.services.retry_manager import RetryManager, RetryConfig


logger = logging.getLogger(__name__)


class MessageType(Enum):
    """メッセージタイプ"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    SUCCESS = "success"
    ANALYSIS_RESULT = "analysis_result"
    ALERT = "alert"

    @property
    def color(self) -> str:
        """Slackメッセージカラー"""
        return {
            MessageType.INFO: "#36a64f",      # 緑
            MessageType.WARNING: "#ff9500",   # オレンジ
            MessageType.ERROR: "#ff0000",     # 赤
            MessageType.SUCCESS: "#00ff00",   # 明るい緑
            MessageType.ANALYSIS_RESULT: "#0099cc",  # 青
            MessageType.ALERT: "#ff6600"      # 濃いオレンジ
        }[self]

    @property
    def emoji(self) -> str:
        """メッセージ絵文字"""
        return {
            MessageType.INFO: ":information_source:",
            MessageType.WARNING: ":warning:",
            MessageType.ERROR: ":x:",
            MessageType.SUCCESS: ":white_check_mark:",
            MessageType.ANALYSIS_RESULT: ":chart_with_upwards_trend:",
            MessageType.ALERT: ":rotating_light:"
        }[self]


class Priority(Enum):
    """優先度"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            Priority.LOW: "低",
            Priority.NORMAL: "通常",
            Priority.HIGH: "高",
            Priority.CRITICAL: "重大"
        }[self]


@dataclass
class SlackField:
    """Slackフィールド"""
    title: str
    value: str
    short: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        return {
            "title": self.title,
            "value": self.value,
            "short": self.short
        }


@dataclass
class SlackAttachment:
    """Slack添付ファイル"""
    color: str
    title: Optional[str] = None
    title_link: Optional[str] = None
    text: Optional[str] = None
    fields: List[SlackField] = field(default_factory=list)
    footer: Optional[str] = None
    footer_icon: Optional[str] = None
    timestamp: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        attachment = {"color": self.color}
        
        if self.title:
            attachment["title"] = self.title
        if self.title_link:
            attachment["title_link"] = self.title_link
        if self.text:
            attachment["text"] = self.text
        if self.fields:
            attachment["fields"] = [field.to_dict() for field in self.fields]
        if self.footer:
            attachment["footer"] = self.footer
        if self.footer_icon:
            attachment["footer_icon"] = self.footer_icon
        if self.timestamp:
            attachment["ts"] = self.timestamp
        
        return attachment


@dataclass
class SlackBlock:
    """Slackブロック"""
    block_type: str
    text: Optional[Dict[str, str]] = None
    elements: Optional[List[Dict[str, Any]]] = None
    accessory: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        block = {"type": self.block_type}
        
        if self.text:
            block["text"] = self.text
        if self.elements:
            block["elements"] = self.elements
        if self.accessory:
            block["accessory"] = self.accessory
        
        return block


@dataclass
class SlackMessage:
    """Slackメッセージ"""
    text: str
    username: Optional[str] = None
    icon_emoji: Optional[str] = None
    icon_url: Optional[str] = None
    channel: Optional[str] = None
    attachments: List[SlackAttachment] = field(default_factory=list)
    blocks: List[SlackBlock] = field(default_factory=list)
    thread_ts: Optional[str] = None
    message_type: MessageType = MessageType.INFO
    priority: Priority = Priority.NORMAL

    def to_dict(self) -> Dict[str, Any]:
        """辞書形式に変換"""
        message = {"text": self.text}
        
        if self.username:
            message["username"] = self.username
        if self.icon_emoji:
            message["icon_emoji"] = self.icon_emoji
        if self.icon_url:
            message["icon_url"] = self.icon_url
        if self.channel:
            message["channel"] = self.channel
        if self.attachments:
            message["attachments"] = [att.to_dict() for att in self.attachments]
        if self.blocks:
            message["blocks"] = [block.to_dict() for block in self.blocks]
        if self.thread_ts:
            message["thread_ts"] = self.thread_ts
        
        return message


@dataclass
class SlackResponse:
    """Slack送信レスポンス"""
    success: bool
    message_ts: Optional[str] = None
    channel: Optional[str] = None
    error_message: Optional[str] = None
    status_code: Optional[int] = None
    response_time: float = 0.0

    @property
    def is_rate_limited(self) -> bool:
        """レート制限されているか"""
        return self.status_code == 429


@dataclass
class SlackConfig:
    """Slack設定"""
    webhook_url: str
    default_channel: Optional[str] = None
    default_username: str = "株価分析Bot"
    default_icon_emoji: str = ":chart_with_upwards_trend:"
    timeout_seconds: float = 30.0
    max_retries: int = 3
    rate_limit_delay: float = 1.0
    enable_threading: bool = True

    def __post_init__(self):
        """設定検証"""
        if not self.webhook_url:
            raise ValueError("Webhook URLが設定されていません")
        if not self.webhook_url.startswith("https://hooks.slack.com/"):
            raise ValueError("有効なSlack Webhook URLではありません")


class SlackService:
    """Slack通知サービス"""
    
    def __init__(self, config: SlackConfig, retry_manager: Optional[RetryManager] = None):
        """
        Args:
            config: Slack設定
            retry_manager: リトライマネージャー
        """
        self.config = config
        self.retry_manager = retry_manager or RetryManager(RetryConfig(
            max_attempts=config.max_retries,
            initial_delay=1.0,
            max_delay=30.0,
            exponential_base=2.0
        ))
        self.logger = logging.getLogger(__name__)
        
        # HTTPセッション設定
        self.session = requests.Session()
        retry_strategy = Retry(
            total=config.max_retries,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("https://", adapter)
        
        # レート制限管理
        self.last_request_time = 0.0
        self.rate_limit_delay = config.rate_limit_delay
    
    def send_message(self, message: SlackMessage) -> SlackResponse:
        """
        メッセージを送信
        
        Args:
            message: Slackメッセージ
            
        Returns:
            SlackResponse: 送信結果
        """
        start_time = time.time()
        self.logger.info(f"Slackメッセージ送信開始: {message.message_type.value}")
        
        try:
            # デフォルト値の設定
            if not message.username:
                message.username = self.config.default_username
            if not message.icon_emoji and not message.icon_url:
                message.icon_emoji = self.config.default_icon_emoji
            if not message.channel and self.config.default_channel:
                message.channel = self.config.default_channel
            
            # メッセージタイプに応じた装飾
            self._apply_message_styling(message)
            
            # レート制限対応
            self._handle_rate_limiting()
            
            # HTTP送信
            response = self._send_http_request(message)
            
            response_time = time.time() - start_time
            response.response_time = response_time
            
            if response.success:
                self.logger.info(f"Slackメッセージ送信成功: {response_time:.2f}秒")
            else:
                self.logger.error(f"Slackメッセージ送信失敗: {response.error_message}")
            
            return response
            
        except Exception as e:
            response_time = time.time() - start_time
            self.logger.error(f"Slackメッセージ送信エラー: {e}")
            
            return SlackResponse(
                success=False,
                error_message=str(e),
                response_time=response_time
            )
    
    def send_simple_message(self, 
                          text: str, 
                          message_type: MessageType = MessageType.INFO,
                          priority: Priority = Priority.NORMAL,
                          channel: Optional[str] = None) -> SlackResponse:
        """
        シンプルなメッセージを送信
        
        Args:
            text: メッセージテキスト
            message_type: メッセージタイプ
            priority: 優先度
            channel: チャンネル
            
        Returns:
            SlackResponse: 送信結果
        """
        message = SlackMessage(
            text=f"{message_type.emoji} {text}",
            message_type=message_type,
            priority=priority,
            channel=channel
        )
        
        return self.send_message(message)
    
    def send_analysis_result(self,
                           title: str,
                           summary: str,
                           fields: List[SlackField],
                           priority: Priority = Priority.NORMAL,
                           include_timestamp: bool = True) -> SlackResponse:
        """
        分析結果を送信
        
        Args:
            title: タイトル
            summary: サマリー
            fields: フィールドリスト
            priority: 優先度
            include_timestamp: タイムスタンプを含めるか
            
        Returns:
            SlackResponse: 送信結果
        """
        attachment = SlackAttachment(
            color=MessageType.ANALYSIS_RESULT.color,
            title=title,
            text=summary,
            fields=fields,
            footer="株価分析システム",
            footer_icon=":chart_with_upwards_trend:",
            timestamp=time.time() if include_timestamp else None
        )
        
        message = SlackMessage(
            text=f"{MessageType.ANALYSIS_RESULT.emoji} {title}",
            attachments=[attachment],
            message_type=MessageType.ANALYSIS_RESULT,
            priority=priority
        )
        
        return self.send_message(message)
    
    def send_error_notification(self,
                              error_message: str,
                              context: Optional[Dict[str, Any]] = None,
                              priority: Priority = Priority.HIGH) -> SlackResponse:
        """
        エラー通知を送信
        
        Args:
            error_message: エラーメッセージ
            context: エラーコンテキスト
            priority: 優先度
            
        Returns:
            SlackResponse: 送信結果
        """
        fields = []
        
        if context:
            for key, value in context.items():
                fields.append(SlackField(
                    title=key.replace('_', ' ').title(),
                    value=str(value),
                    short=True
                ))
        
        attachment = SlackAttachment(
            color=MessageType.ERROR.color,
            title="システムエラーが発生しました",
            text=error_message,
            fields=fields,
            footer="株価分析システム",
            timestamp=time.time()
        )
        
        message = SlackMessage(
            text=f"{MessageType.ERROR.emoji} システムエラー",
            attachments=[attachment],
            message_type=MessageType.ERROR,
            priority=priority
        )
        
        return self.send_message(message)
    
    def send_alert(self,
                   alert_title: str,
                   alert_message: str,
                   urgency_level: Priority = Priority.CRITICAL,
                   mention_channel: bool = True) -> SlackResponse:
        """
        アラートを送信
        
        Args:
            alert_title: アラートタイトル
            alert_message: アラートメッセージ
            urgency_level: 緊急度
            mention_channel: チャンネル全体にメンション
            
        Returns:
            SlackResponse: 送信結果
        """
        text = f"{MessageType.ALERT.emoji} **{alert_title}**"
        if mention_channel and urgency_level == Priority.CRITICAL:
            text = f"<!channel> {text}"
        
        attachment = SlackAttachment(
            color=MessageType.ALERT.color,
            title=alert_title,
            text=alert_message,
            footer="株価分析システム - 緊急アラート",
            timestamp=time.time()
        )
        
        message = SlackMessage(
            text=text,
            attachments=[attachment],
            message_type=MessageType.ALERT,
            priority=urgency_level
        )
        
        return self.send_message(message)
    
    def _apply_message_styling(self, message: SlackMessage):
        """メッセージスタイリングを適用"""
        # 優先度に応じた装飾
        if message.priority == Priority.CRITICAL:
            message.text = f":rotating_light: **{message.text}** :rotating_light:"
        elif message.priority == Priority.HIGH:
            message.text = f":warning: {message.text}"
        
        # メッセージタイプに応じた装飾
        if not message.text.startswith(message.message_type.emoji):
            message.text = f"{message.message_type.emoji} {message.text}"
    
    def _handle_rate_limiting(self):
        """レート制限対応"""
        current_time = time.time()
        time_since_last_request = current_time - self.last_request_time
        
        if time_since_last_request < self.rate_limit_delay:
            sleep_time = self.rate_limit_delay - time_since_last_request
            self.logger.debug(f"レート制限対応: {sleep_time:.2f}秒待機")
            time.sleep(sleep_time)
        
        self.last_request_time = time.time()
    
    def _send_http_request(self, message: SlackMessage) -> SlackResponse:
        """HTTP リクエストを送信"""
        try:
            payload = message.to_dict()
            
            response = self.session.post(
                self.config.webhook_url,
                json=payload,
                timeout=self.config.timeout_seconds
            )
            
            if response.status_code == 200:
                response_data = response.text
                if response_data == "ok":
                    return SlackResponse(
                        success=True,
                        status_code=response.status_code
                    )
                else:
                    # Slack APIからのエラーレスポンス
                    return SlackResponse(
                        success=False,
                        error_message=response_data,
                        status_code=response.status_code
                    )
            else:
                return SlackResponse(
                    success=False,
                    error_message=f"HTTP {response.status_code}: {response.text}",
                    status_code=response.status_code
                )
                
        except requests.exceptions.Timeout:
            return SlackResponse(
                success=False,
                error_message="リクエストタイムアウト",
                status_code=408
            )
        except requests.exceptions.ConnectionError:
            return SlackResponse(
                success=False,
                error_message="接続エラー",
                status_code=503
            )
        except requests.exceptions.RequestException as e:
            return SlackResponse(
                success=False,
                error_message=f"リクエストエラー: {str(e)}",
                status_code=500
            )
    
    def test_connection(self) -> SlackResponse:
        """接続テスト"""
        test_message = SlackMessage(
            text="株価分析システム接続テスト",
            message_type=MessageType.INFO
        )
        
        response = self.send_message(test_message)
        
        if response.success:
            self.logger.info("Slack接続テスト成功")
        else:
            self.logger.error(f"Slack接続テスト失敗: {response.error_message}")
        
        return response
    
    def get_service_status(self) -> Dict[str, Any]:
        """サービス状態を取得"""
        return {
            "service_name": "SlackService",
            "webhook_url_configured": bool(self.config.webhook_url),
            "default_channel": self.config.default_channel,
            "max_retries": self.config.max_retries,
            "timeout_seconds": self.config.timeout_seconds,
            "rate_limit_delay": self.rate_limit_delay,
            "last_request_time": self.last_request_time
        }