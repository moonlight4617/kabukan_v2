# -*- coding: utf-8 -*-
"""
Slack緊急度別通知管理サービス
重要な分析結果の特別フォーマット、通知の優先度管理機能を提供
"""

import logging
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import asyncio

from src.models.analysis_models import AnalysisResult, RiskLevel
from src.services.daily_analysis_service import DailyAnalysisResult, HoldingAction, WatchlistAction
from src.services.weekly_analysis_service import WeeklyAnalysisResult, PerformanceCategory
from src.services.monthly_analysis_service import MonthlyAnalysisResult
from src.services.slack_service import SlackService, SlackMessage, SlackAttachment, SlackField, MessageType, Priority
from src.services.slack_notification_formatter import SlackNotificationFormatter, NotificationContext, NotificationTemplate
from src.services.slack_notification_error_handler import SlackNotificationErrorHandler


logger = logging.getLogger(__name__)


class UrgencyLevel(Enum):
    """緊急度レベル"""
    ROUTINE = "routine"        # 定期通知
    ATTENTION = "attention"    # 注意喚起
    URGENT = "urgent"         # 緊急
    CRITICAL = "critical"     # 重大

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            UrgencyLevel.ROUTINE: "定期",
            UrgencyLevel.ATTENTION: "注意",
            UrgencyLevel.URGENT: "緊急",
            UrgencyLevel.CRITICAL: "重大"
        }[self]

    @property
    def priority(self) -> Priority:
        """対応するSlack優先度"""
        return {
            UrgencyLevel.ROUTINE: Priority.LOW,
            UrgencyLevel.ATTENTION: Priority.NORMAL,
            UrgencyLevel.URGENT: Priority.HIGH,
            UrgencyLevel.CRITICAL: Priority.CRITICAL
        }[self]

    @property
    def emoji(self) -> str:
        """緊急度絵文字"""
        return {
            UrgencyLevel.ROUTINE: ":information_source:",
            UrgencyLevel.ATTENTION: ":warning:",
            UrgencyLevel.URGENT: ":exclamation:",
            UrgencyLevel.CRITICAL: ":rotating_light:"
        }[self]


class AlertType(Enum):
    """アラートタイプ"""
    PORTFOLIO_LOSS = "portfolio_loss"
    RISK_SPIKE = "risk_spike"
    PERFORMANCE_DECLINE = "performance_decline"
    SYSTEM_ERROR = "system_error"
    MARKET_VOLATILITY = "market_volatility"
    CONCENTRATION_RISK = "concentration_risk"
    TECHNICAL_SIGNAL = "technical_signal"

    @property
    def display_name(self) -> str:
        """表示名"""
        return {
            AlertType.PORTFOLIO_LOSS: "ポートフォリオ損失",
            AlertType.RISK_SPIKE: "リスク急上昇",
            AlertType.PERFORMANCE_DECLINE: "パフォーマンス低下",
            AlertType.SYSTEM_ERROR: "システムエラー",
            AlertType.MARKET_VOLATILITY: "市場ボラティリティ",
            AlertType.CONCENTRATION_RISK: "集中リスク",
            AlertType.TECHNICAL_SIGNAL: "テクニカルシグナル"
        }[self]


@dataclass
class UrgencyRule:
    """緊急度判定ルール"""
    alert_type: AlertType
    conditions: Dict[str, Any]
    urgency_level: UrgencyLevel
    message_template: str
    escalation_required: bool = False
    
    def matches(self, context: Dict[str, Any]) -> bool:
        """条件にマッチするか判定"""
        for key, expected_value in self.conditions.items():
            if key not in context:
                return False
            
            actual_value = context[key]
            
            # 数値比較
            if isinstance(expected_value, dict) and 'operator' in expected_value:
                operator = expected_value['operator']
                threshold = expected_value['value']
                
                if operator == 'gt' and actual_value <= threshold:
                    return False
                elif operator == 'lt' and actual_value >= threshold:
                    return False
                elif operator == 'gte' and actual_value < threshold:
                    return False
                elif operator == 'lte' and actual_value > threshold:
                    return False
                elif operator == 'eq' and actual_value != threshold:
                    return False
            else:
                # 直接比較
                if actual_value != expected_value:
                    return False
        
        return True


@dataclass
class NotificationSchedule:
    """通知スケジュール"""
    urgency_level: UrgencyLevel
    immediate: bool = True
    delay_minutes: int = 0
    suppress_duplicates: bool = True
    suppress_duration_hours: int = 1
    
    @property
    def should_send_immediately(self) -> bool:
        """即座に送信すべきか"""
        return self.immediate and self.delay_minutes == 0


@dataclass
class EscalationRule:
    """エスカレーションルール"""
    urgency_level: UrgencyLevel
    escalation_channels: List[str]
    escalation_users: List[str]
    escalation_delay_minutes: int = 0
    repeat_interval_hours: int = 24


@dataclass
class NotificationMetrics:
    """通知メトリクス"""
    total_notifications: int = 0
    urgent_notifications: int = 0
    critical_notifications: int = 0
    escalations: int = 0
    suppressed_notifications: int = 0
    last_notification: Optional[datetime] = None
    alert_type_counts: Dict[str, int] = field(default_factory=dict)


class SlackPriorityNotificationManager:
    """Slack緊急度別通知管理サービス"""
    
    def __init__(self,
                 slack_service: SlackService,
                 formatter: SlackNotificationFormatter,
                 error_handler: SlackNotificationErrorHandler):
        """
        Args:
            slack_service: Slackサービス
            formatter: 通知フォーマッター
            error_handler: エラーハンドラー
        """
        self.slack_service = slack_service
        self.formatter = formatter
        self.error_handler = error_handler
        self.logger = logging.getLogger(__name__)
        
        # 設定
        self.urgency_rules = self._initialize_urgency_rules()
        self.notification_schedules = self._initialize_notification_schedules()
        self.escalation_rules = self._initialize_escalation_rules()
        
        # 状態管理
        self.recent_notifications: Dict[str, datetime] = {}
        self.metrics = NotificationMetrics()
        
        # チャンネル設定
        self.channel_mapping = {
            UrgencyLevel.ROUTINE: "#stock-analysis",
            UrgencyLevel.ATTENTION: "#stock-alerts",
            UrgencyLevel.URGENT: "#urgent-alerts",
            UrgencyLevel.CRITICAL: "#critical-alerts"
        }
        
        # ユーザーメンション設定
        self.mention_mapping = {
            UrgencyLevel.URGENT: ["@here"],
            UrgencyLevel.CRITICAL: ["@channel"]
        }
    
    def _initialize_urgency_rules(self) -> List[UrgencyRule]:
        """緊急度ルールを初期化"""
        return [
            # ポートフォリオ損失
            UrgencyRule(
                alert_type=AlertType.PORTFOLIO_LOSS,
                conditions={
                    "portfolio_loss_percent": {"operator": "gt", "value": 10.0}
                },
                urgency_level=UrgencyLevel.CRITICAL,
                message_template="ポートフォリオが{portfolio_loss_percent:.1f}%の大幅損失",
                escalation_required=True
            ),
            UrgencyRule(
                alert_type=AlertType.PORTFOLIO_LOSS,
                conditions={
                    "portfolio_loss_percent": {"operator": "gt", "value": 5.0}
                },
                urgency_level=UrgencyLevel.URGENT,
                message_template="ポートフォリオが{portfolio_loss_percent:.1f}%の損失"
            ),
            
            # リスク急上昇
            UrgencyRule(
                alert_type=AlertType.RISK_SPIKE,
                conditions={
                    "risk_level": RiskLevel.CRITICAL
                },
                urgency_level=UrgencyLevel.CRITICAL,
                message_template="リスクレベルが重大に上昇",
                escalation_required=True
            ),
            UrgencyRule(
                alert_type=AlertType.RISK_SPIKE,
                conditions={
                    "risk_level": RiskLevel.HIGH
                },
                urgency_level=UrgencyLevel.URGENT,
                message_template="リスクレベルが高に上昇"
            ),
            
            # パフォーマンス低下
            UrgencyRule(
                alert_type=AlertType.PERFORMANCE_DECLINE,
                conditions={
                    "performance_category": PerformanceCategory.VERY_POOR,
                    "duration_days": {"operator": "gte", "value": 3}
                },
                urgency_level=UrgencyLevel.URGENT,
                message_template="連続{duration_days}日間の非常に悪いパフォーマンス"
            ),
            
            # システムエラー
            UrgencyRule(
                alert_type=AlertType.SYSTEM_ERROR,
                conditions={
                    "error_severity": "critical"
                },
                urgency_level=UrgencyLevel.CRITICAL,
                message_template="重大なシステムエラーが発生",
                escalation_required=True
            ),
            
            # 市場ボラティリティ
            UrgencyRule(
                alert_type=AlertType.MARKET_VOLATILITY,
                conditions={
                    "volatility_percent": {"operator": "gt", "value": 30.0}
                },
                urgency_level=UrgencyLevel.URGENT,
                message_template="市場ボラティリティが{volatility_percent:.1f}%に急上昇"
            ),
            
            # 集中リスク
            UrgencyRule(
                alert_type=AlertType.CONCENTRATION_RISK,
                conditions={
                    "concentration_ratio": {"operator": "gt", "value": 0.5}
                },
                urgency_level=UrgencyLevel.ATTENTION,
                message_template="ポートフォリオの集中度が{concentration_ratio:.1%}に上昇"
            )
        ]
    
    def _initialize_notification_schedules(self) -> Dict[UrgencyLevel, NotificationSchedule]:
        """通知スケジュールを初期化"""
        return {
            UrgencyLevel.ROUTINE: NotificationSchedule(
                urgency_level=UrgencyLevel.ROUTINE,
                immediate=True,
                suppress_duplicates=True,
                suppress_duration_hours=24
            ),
            UrgencyLevel.ATTENTION: NotificationSchedule(
                urgency_level=UrgencyLevel.ATTENTION,
                immediate=True,
                suppress_duplicates=True,
                suppress_duration_hours=6
            ),
            UrgencyLevel.URGENT: NotificationSchedule(
                urgency_level=UrgencyLevel.URGENT,
                immediate=True,
                suppress_duplicates=True,
                suppress_duration_hours=1
            ),
            UrgencyLevel.CRITICAL: NotificationSchedule(
                urgency_level=UrgencyLevel.CRITICAL,
                immediate=True,
                suppress_duplicates=False
            )
        }
    
    def _initialize_escalation_rules(self) -> Dict[UrgencyLevel, EscalationRule]:
        """エスカレーションルールを初期化"""
        return {
            UrgencyLevel.URGENT: EscalationRule(
                urgency_level=UrgencyLevel.URGENT,
                escalation_channels=["#management"],
                escalation_users=["@manager"],
                escalation_delay_minutes=30
            ),
            UrgencyLevel.CRITICAL: EscalationRule(
                urgency_level=UrgencyLevel.CRITICAL,
                escalation_channels=["#management", "#executives"],
                escalation_users=["@manager", "@cto"],
                escalation_delay_minutes=5,
                repeat_interval_hours=2
            )
        }
    
    async def send_analysis_notification(self, 
                                       analysis_result: Any,
                                       forced_urgency: Optional[UrgencyLevel] = None) -> bool:
        """
        分析結果通知を送信
        
        Args:
            analysis_result: 分析結果
            forced_urgency: 強制的に指定する緊急度
            
        Returns:
            bool: 送信成功したか
        """
        try:
            # 緊急度判定
            urgency = forced_urgency or self._determine_urgency(analysis_result)
            
            # 通知抑制チェック
            if self._should_suppress_notification(analysis_result, urgency):
                self.metrics.suppressed_notifications += 1
                self.logger.info(f"通知抑制: {urgency.display_name}レベル")
                return True
            
            # 通知メッセージ作成
            message = await self._create_notification_message(analysis_result, urgency)
            
            # 通知送信
            result = await self.error_handler.send_notification_with_error_handling(message)
            
            # メトリクス更新
            self._update_metrics(urgency, analysis_result, result.success)
            
            # エスカレーション処理
            if result.success and urgency in [UrgencyLevel.URGENT, UrgencyLevel.CRITICAL]:
                await self._handle_escalation(analysis_result, urgency)
            
            return result.success
            
        except Exception as e:
            self.logger.error(f"分析結果通知送信エラー: {e}")
            return False
    
    async def send_alert(self,
                        alert_type: AlertType,
                        context: Dict[str, Any],
                        custom_message: Optional[str] = None) -> bool:
        """
        アラートを送信
        
        Args:
            alert_type: アラートタイプ
            context: アラートコンテキスト
            custom_message: カスタムメッセージ
            
        Returns:
            bool: 送信成功したか
        """
        try:
            # 緊急度判定
            urgency = self._determine_alert_urgency(alert_type, context)
            
            # アラートメッセージ作成
            message = self._create_alert_message(alert_type, context, urgency, custom_message)
            
            # 通知送信
            result = await self.error_handler.send_notification_with_error_handling(message)
            
            # メトリクス更新
            self._update_alert_metrics(alert_type, urgency, result.success)
            
            # エスカレーション処理
            if result.success and urgency in [UrgencyLevel.URGENT, UrgencyLevel.CRITICAL]:
                await self._handle_alert_escalation(alert_type, context, urgency)
            
            return result.success
            
        except Exception as e:
            self.logger.error(f"アラート送信エラー: {e}")
            return False
    
    def _determine_urgency(self, analysis_result: Any) -> UrgencyLevel:
        """分析結果から緊急度を判定"""
        context = self._extract_analysis_context(analysis_result)
        
        # 最も高い緊急度を返す
        max_urgency = UrgencyLevel.ROUTINE
        
        for rule in self.urgency_rules:
            if rule.matches(context):
                if rule.urgency_level.value > max_urgency.value:
                    max_urgency = rule.urgency_level
        
        return max_urgency
    
    def _determine_alert_urgency(self, alert_type: AlertType, context: Dict[str, Any]) -> UrgencyLevel:
        """アラートから緊急度を判定"""
        for rule in self.urgency_rules:
            if rule.alert_type == alert_type and rule.matches(context):
                return rule.urgency_level
        
        return UrgencyLevel.ATTENTION
    
    def _extract_analysis_context(self, analysis_result: Any) -> Dict[str, Any]:
        """分析結果からコンテキストを抽出"""
        context = {}
        
        if isinstance(analysis_result, DailyAnalysisResult):
            # 保有銘柄の売却アクション数をカウント
            sell_actions = sum(1 for rec in analysis_result.holding_recommendations 
                             if rec.action in [HoldingAction.SELL_PARTIAL, HoldingAction.SELL_ALL])
            context.update({
                "sell_action_count": sell_actions,
                "total_holdings": len(analysis_result.holding_recommendations)
            })
            
        elif isinstance(analysis_result, WeeklyAnalysisResult):
            portfolio = analysis_result.portfolio_performance
            context.update({
                "portfolio_loss_percent": abs(portfolio.weekly_return_pct) if portfolio.weekly_return_pct < 0 else 0,
                "volatility_percent": portfolio.weekly_volatility,
                "performance_category": analysis_result.bottom_performers[0].performance_category if analysis_result.bottom_performers else None
            })
            
        elif isinstance(analysis_result, MonthlyAnalysisResult):
            diversification = analysis_result.diversification_metrics
            context.update({
                "diversification_score": diversification.overall_score,
                "concentration_ratio": diversification.concentration_risk_score / 100.0
            })
        
        return context
    
    def _should_suppress_notification(self, analysis_result: Any, urgency: UrgencyLevel) -> bool:
        """通知を抑制すべきか判定"""
        schedule = self.notification_schedules.get(urgency)
        if not schedule or not schedule.suppress_duplicates:
            return False
        
        # 重複通知の抑制
        notification_key = f"{type(analysis_result).__name__}_{urgency.value}"
        last_sent = self.recent_notifications.get(notification_key)
        
        if last_sent:
            time_diff = datetime.now() - last_sent
            if time_diff < timedelta(hours=schedule.suppress_duration_hours):
                return True
        
        return False
    
    async def _create_notification_message(self, analysis_result: Any, urgency: UrgencyLevel) -> SlackMessage:
        """通知メッセージを作成"""
        context = NotificationContext(
            template=self._get_notification_template(analysis_result),
            priority=urgency.priority,
            include_details=urgency in [UrgencyLevel.URGENT, UrgencyLevel.CRITICAL],
            mention_users=self.mention_mapping.get(urgency, [])
        )
        
        # 分析結果タイプ別のフォーマット
        if isinstance(analysis_result, DailyAnalysisResult):
            message = self.formatter.format_daily_analysis_notification(analysis_result, context)
        elif isinstance(analysis_result, WeeklyAnalysisResult):
            message = self.formatter.format_weekly_analysis_notification(analysis_result, context)
        elif isinstance(analysis_result, MonthlyAnalysisResult):
            message = self.formatter.format_monthly_analysis_notification(analysis_result, context)
        else:
            # 一般的な分析結果
            message = SlackMessage(
                text=f"{urgency.emoji} 分析結果通知",
                message_type=MessageType.ANALYSIS_RESULT,
                priority=urgency.priority
            )
        
        # チャンネル設定
        if urgency in self.channel_mapping:
            message.channel = self.channel_mapping[urgency]
        
        # 緊急度表示を追加
        if urgency in [UrgencyLevel.URGENT, UrgencyLevel.CRITICAL]:
            message.text = f"【{urgency.display_name}】{message.text}"
        
        return message
    
    def _create_alert_message(self,
                            alert_type: AlertType,
                            context: Dict[str, Any],
                            urgency: UrgencyLevel,
                            custom_message: Optional[str] = None) -> SlackMessage:
        """アラートメッセージを作成"""
        # 該当するルールを検索
        matching_rule = None
        for rule in self.urgency_rules:
            if rule.alert_type == alert_type and rule.matches(context):
                matching_rule = rule
                break
        
        # メッセージテキスト作成
        if custom_message:
            alert_text = custom_message
        elif matching_rule:
            alert_text = matching_rule.message_template.format(**context)
        else:
            alert_text = f"{alert_type.display_name}が発生しました"
        
        # 緊急度による装飾
        decorated_text = f"{urgency.emoji} 【{urgency.display_name}アラート】{alert_text}"
        
        # メンション追加
        mentions = self.mention_mapping.get(urgency, [])
        if mentions:
            mention_text = " ".join(mentions)
            decorated_text = f"{mention_text} {decorated_text}"
        
        # Slackメッセージ作成
        message = SlackMessage(
            text=decorated_text,
            message_type=MessageType.ALERT,
            priority=urgency.priority,
            channel=self.channel_mapping.get(urgency)
        )
        
        # 詳細情報の添付ファイル
        if context and urgency in [UrgencyLevel.URGENT, UrgencyLevel.CRITICAL]:
            fields = []
            for key, value in context.items():
                fields.append(SlackField(
                    title=key.replace('_', ' ').title(),
                    value=str(value),
                    short=True
                ))
            
            attachment = SlackAttachment(
                color="#ff0000" if urgency == UrgencyLevel.CRITICAL else "#ff9500",
                title="アラート詳細",
                fields=fields,
                footer="アラートシステム",
                timestamp=datetime.now().timestamp()
            )
            message.attachments = [attachment]
        
        return message
    
    def _get_notification_template(self, analysis_result: Any) -> NotificationTemplate:
        """分析結果に対応する通知テンプレートを取得"""
        if isinstance(analysis_result, DailyAnalysisResult):
            return NotificationTemplate.DAILY_ANALYSIS
        elif isinstance(analysis_result, WeeklyAnalysisResult):
            return NotificationTemplate.WEEKLY_ANALYSIS
        elif isinstance(analysis_result, MonthlyAnalysisResult):
            return NotificationTemplate.MONTHLY_ANALYSIS
        else:
            return NotificationTemplate.SYSTEM_STATUS
    
    async def _handle_escalation(self, analysis_result: Any, urgency: UrgencyLevel):
        """エスカレーション処理"""
        escalation_rule = self.escalation_rules.get(urgency)
        if not escalation_rule:
            return
        
        # エスカレーション遅延
        if escalation_rule.escalation_delay_minutes > 0:
            await asyncio.sleep(escalation_rule.escalation_delay_minutes * 60)
        
        # エスカレーション通知作成
        escalation_text = f"⚠️ {urgency.display_name}レベルの分析結果がエスカレーションされました"
        
        escalation_message = SlackMessage(
            text=escalation_text,
            message_type=MessageType.ALERT,
            priority=Priority.CRITICAL
        )
        
        # エスカレーションチャンネルに送信
        for channel in escalation_rule.escalation_channels:
            escalation_message.channel = channel
            try:
                await self.error_handler.send_notification_with_error_handling(escalation_message)
                self.metrics.escalations += 1
            except Exception as e:
                self.logger.error(f"エスカレーション送信失敗 ({channel}): {e}")
    
    async def _handle_alert_escalation(self, alert_type: AlertType, context: Dict[str, Any], urgency: UrgencyLevel):
        """アラートエスカレーション処理"""
        # _handle_escalationと同様の処理をアラート用にカスタマイズ
        escalation_rule = self.escalation_rules.get(urgency)
        if not escalation_rule:
            return
        
        escalation_text = f"🚨 {alert_type.display_name}アラートがエスカレーションされました"
        
        escalation_message = SlackMessage(
            text=escalation_text,
            message_type=MessageType.ALERT,
            priority=Priority.CRITICAL
        )
        
        for channel in escalation_rule.escalation_channels:
            escalation_message.channel = channel
            try:
                await self.error_handler.send_notification_with_error_handling(escalation_message)
                self.metrics.escalations += 1
            except Exception as e:
                self.logger.error(f"アラートエスカレーション送信失敗 ({channel}): {e}")
    
    def _update_metrics(self, urgency: UrgencyLevel, analysis_result: Any, success: bool):
        """メトリクスを更新"""
        if success:
            self.metrics.total_notifications += 1
            self.metrics.last_notification = datetime.now()
            
            if urgency == UrgencyLevel.URGENT:
                self.metrics.urgent_notifications += 1
            elif urgency == UrgencyLevel.CRITICAL:
                self.metrics.critical_notifications += 1
            
            # 重複抑制用の記録
            notification_key = f"{type(analysis_result).__name__}_{urgency.value}"
            self.recent_notifications[notification_key] = datetime.now()
    
    def _update_alert_metrics(self, alert_type: AlertType, urgency: UrgencyLevel, success: bool):
        """アラートメトリクスを更新"""
        if success:
            alert_key = alert_type.value
            self.metrics.alert_type_counts[alert_key] = self.metrics.alert_type_counts.get(alert_key, 0) + 1
    
    def get_notification_metrics(self) -> Dict[str, Any]:
        """通知メトリクスを取得"""
        return {
            "total_notifications": self.metrics.total_notifications,
            "urgent_notifications": self.metrics.urgent_notifications,
            "critical_notifications": self.metrics.critical_notifications,
            "escalations": self.metrics.escalations,
            "suppressed_notifications": self.metrics.suppressed_notifications,
            "last_notification": self.metrics.last_notification.isoformat() if self.metrics.last_notification else None,
            "alert_type_counts": self.metrics.alert_type_counts,
            "recent_notifications_count": len(self.recent_notifications)
        }
    
    def configure_channels(self, channel_mapping: Dict[UrgencyLevel, str]):
        """チャンネルマッピングを設定"""
        self.channel_mapping.update(channel_mapping)
        self.logger.info(f"チャンネルマッピングを更新: {channel_mapping}")
    
    def configure_mentions(self, mention_mapping: Dict[UrgencyLevel, List[str]]):
        """メンションマッピングを設定"""
        self.mention_mapping.update(mention_mapping)
        self.logger.info(f"メンションマッピングを更新: {mention_mapping}")