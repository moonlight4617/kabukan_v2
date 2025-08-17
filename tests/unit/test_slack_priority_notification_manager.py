# -*- coding: utf-8 -*-
"""
Slack優先度通知マネージャーの単体テスト
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.services.slack_priority_notification_manager import (
    SlackPriorityNotificationManager, UrgencyLevel, AlertType, UrgencyRule,
    NotificationSchedule, EscalationRule, NotificationMetrics
)
from src.services.slack_service import SlackService, SlackResponse


class TestUrgencyLevel:
    """緊急度レベルのテストクラス"""
    
    def test_urgency_level_values(self):
        """緊急度レベル値のテスト"""
        assert UrgencyLevel.LOW.value == "low"
        assert UrgencyLevel.MEDIUM.value == "medium"
        assert UrgencyLevel.HIGH.value == "high"
        assert UrgencyLevel.CRITICAL.value == "critical"
    
    def test_urgency_level_display_names(self):
        """緊急度レベル表示名のテスト"""
        assert UrgencyLevel.LOW.display_name == "低"
        assert UrgencyLevel.MEDIUM.display_name == "中"
        assert UrgencyLevel.HIGH.display_name == "高"
        assert UrgencyLevel.CRITICAL.display_name == "緊急"


class TestAlertType:
    """アラートタイプのテストクラス"""
    
    def test_alert_type_values(self):
        """アラートタイプ値のテスト"""
        assert AlertType.ERROR.value == "error"
        assert AlertType.WARNING.value == "warning"
        assert AlertType.INFO.value == "info"
        assert AlertType.PERFORMANCE.value == "performance"
    
    def test_alert_type_display_names(self):
        """アラートタイプ表示名のテスト"""
        assert AlertType.ERROR.display_name == "エラー"
        assert AlertType.WARNING.display_name == "警告"
        assert AlertType.INFO.display_name == "情報"
        assert AlertType.PERFORMANCE.display_name == "パフォーマンス"


class TestUrgencyRule:
    """緊急度ルールのテストクラス"""
    
    def test_urgency_rule_creation(self):
        """緊急度ルール作成のテスト"""
        rule = UrgencyRule(
            alert_types=[AlertType.ERROR],
            keywords=["critical", "urgent"],
            urgency_level=UrgencyLevel.CRITICAL,
            immediate_notification=True,
            escalation_required=True,
            escalation_delay_minutes=30
        )
        
        assert rule.alert_types == [AlertType.ERROR]
        assert rule.keywords == ["critical", "urgent"]
        assert rule.urgency_level == UrgencyLevel.CRITICAL
        assert rule.immediate_notification is True
        assert rule.escalation_required is True
        assert rule.escalation_delay_minutes == 30
    
    def test_urgency_rule_matches_alert_type(self):
        """アラートタイプマッチングのテスト"""
        rule = UrgencyRule(
            alert_types=[AlertType.ERROR, AlertType.WARNING],
            urgency_level=UrgencyLevel.HIGH
        )
        
        assert rule.matches(AlertType.ERROR, "test message")
        assert rule.matches(AlertType.WARNING, "test message")
        assert not rule.matches(AlertType.INFO, "test message")
    
    def test_urgency_rule_matches_keywords(self):
        """キーワードマッチングのテスト"""
        rule = UrgencyRule(
            alert_types=[],
            keywords=["error", "failed", "critical"],
            urgency_level=UrgencyLevel.HIGH
        )
        
        assert rule.matches(AlertType.INFO, "System error occurred")
        assert rule.matches(AlertType.INFO, "Operation failed")
        assert rule.matches(AlertType.INFO, "Critical issue")
        assert not rule.matches(AlertType.INFO, "Normal operation")
        assert not rule.matches(AlertType.INFO, "Success")
    
    def test_urgency_rule_matches_both_conditions(self):
        """アラートタイプとキーワード両方のマッチングテスト"""
        rule = UrgencyRule(
            alert_types=[AlertType.ERROR],
            keywords=["database"],
            urgency_level=UrgencyLevel.CRITICAL
        )
        
        # アラートタイプのみマッチ
        assert rule.matches(AlertType.ERROR, "General error")
        
        # キーワードのみマッチ
        assert rule.matches(AlertType.INFO, "Database connection issue")
        
        # 両方マッチ
        assert rule.matches(AlertType.ERROR, "Database error occurred")
        
        # どちらもマッチしない
        assert not rule.matches(AlertType.INFO, "Normal operation")


class TestNotificationSchedule:
    """通知スケジュールのテストクラス"""
    
    def test_notification_schedule_creation(self):
        """通知スケジュール作成のテスト"""
        schedule = NotificationSchedule(
            urgency_level=UrgencyLevel.HIGH,
            initial_delay_seconds=0,
            retry_intervals=[60, 300, 900],
            max_retries=3,
            escalation_after_failures=2
        )
        
        assert schedule.urgency_level == UrgencyLevel.HIGH
        assert schedule.initial_delay_seconds == 0
        assert schedule.retry_intervals == [60, 300, 900]
        assert schedule.max_retries == 3
        assert schedule.escalation_after_failures == 2
    
    def test_notification_schedule_get_retry_delay(self):
        """リトライ遅延取得のテスト"""
        schedule = NotificationSchedule(
            urgency_level=UrgencyLevel.MEDIUM,
            retry_intervals=[30, 60, 120]
        )
        
        assert schedule.get_retry_delay(0) == 30
        assert schedule.get_retry_delay(1) == 60
        assert schedule.get_retry_delay(2) == 120
        assert schedule.get_retry_delay(3) == 120  # 最後の値を使用


class TestEscalationRule:
    """エスカレーションルールのテストクラス"""
    
    def test_escalation_rule_creation(self):
        """エスカレーションルール作成のテスト"""
        rule = EscalationRule(
            trigger_conditions=["consecutive_failures", "high_error_rate"],
            escalation_channels=["#alerts", "#management"],
            escalation_mentions=["@admin", "@manager"],
            escalation_delay_minutes=15,
            max_escalations=2
        )
        
        assert rule.trigger_conditions == ["consecutive_failures", "high_error_rate"]
        assert rule.escalation_channels == ["#alerts", "#management"]
        assert rule.escalation_mentions == ["@admin", "@manager"]
        assert rule.escalation_delay_minutes == 15
        assert rule.max_escalations == 2


class TestNotificationMetrics:
    """通知メトリクスのテストクラス"""
    
    def test_notification_metrics_creation(self):
        """通知メトリクス作成のテスト"""
        metrics = NotificationMetrics()
        
        assert metrics.total_notifications == 0
        assert metrics.successful_notifications == 0
        assert metrics.failed_notifications == 0
        assert metrics.escalated_notifications == 0
        assert len(metrics.urgency_distribution) == 0
        assert len(metrics.alert_type_distribution) == 0
    
    def test_notification_metrics_update(self):
        """メトリクス更新のテスト"""
        metrics = NotificationMetrics()
        
        # 成功通知を記録
        metrics.record_notification(
            urgency_level=UrgencyLevel.HIGH,
            alert_type=AlertType.ERROR,
            success=True,
            escalated=False
        )
        
        assert metrics.total_notifications == 1
        assert metrics.successful_notifications == 1
        assert metrics.failed_notifications == 0
        assert metrics.success_rate == 1.0
        assert metrics.urgency_distribution[UrgencyLevel.HIGH.value] == 1
        assert metrics.alert_type_distribution[AlertType.ERROR.value] == 1
        
        # 失敗通知を記録
        metrics.record_notification(
            urgency_level=UrgencyLevel.MEDIUM,
            alert_type=AlertType.WARNING,
            success=False,
            escalated=True
        )
        
        assert metrics.total_notifications == 2
        assert metrics.successful_notifications == 1
        assert metrics.failed_notifications == 1
        assert metrics.escalated_notifications == 1
        assert metrics.success_rate == 0.5
    
    def test_notification_metrics_to_dict(self):
        """メトリクス辞書変換のテスト"""
        metrics = NotificationMetrics()
        metrics.record_notification(UrgencyLevel.HIGH, AlertType.ERROR, True, False)
        
        result = metrics.to_dict()
        
        assert result["total_notifications"] == 1
        assert result["successful_notifications"] == 1
        assert result["success_rate"] == 1.0
        assert "urgency_distribution" in result
        assert "alert_type_distribution" in result


class TestSlackPriorityNotificationManager:
    """Slack優先度通知マネージャーのテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.mock_slack_service = Mock(spec=SlackService)
        self.mock_slack_service.send_notification = AsyncMock()
        self.mock_slack_service.send_alert = AsyncMock()
        
        self.manager = SlackPriorityNotificationManager(
            slack_service=self.mock_slack_service
        )
    
    def test_manager_initialization(self):
        """マネージャー初期化のテスト"""
        assert self.manager.slack_service == self.mock_slack_service
        assert len(self.manager.urgency_rules) > 0
        assert len(self.manager.notification_schedules) > 0
        assert isinstance(self.manager.metrics, NotificationMetrics)
    
    def test_add_urgency_rule(self):
        """緊急度ルール追加のテスト"""
        initial_count = len(self.manager.urgency_rules)
        
        custom_rule = UrgencyRule(
            alert_types=[AlertType.PERFORMANCE],
            keywords=["slow", "timeout"],
            urgency_level=UrgencyLevel.MEDIUM
        )
        
        self.manager.add_urgency_rule(custom_rule)
        assert len(self.manager.urgency_rules) == initial_count + 1
    
    def test_determine_urgency_level_by_alert_type(self):
        """アラートタイプによる緊急度判定のテスト"""
        urgency = self.manager._determine_urgency_level(
            AlertType.ERROR,
            "Database connection failed"
        )
        
        # ERROR タイプは HIGH 以上の緊急度になるはず
        assert urgency in [UrgencyLevel.HIGH, UrgencyLevel.CRITICAL]
    
    def test_determine_urgency_level_by_keywords(self):
        """キーワードによる緊急度判定のテスト"""
        urgency = self.manager._determine_urgency_level(
            AlertType.INFO,
            "Critical system failure detected"
        )
        
        # "Critical" キーワードで高い緊急度になるはず
        assert urgency in [UrgencyLevel.HIGH, UrgencyLevel.CRITICAL]
    
    def test_determine_urgency_level_default(self):
        """デフォルト緊急度判定のテスト"""
        urgency = self.manager._determine_urgency_level(
            AlertType.INFO,
            "Normal operation message"
        )
        
        # マッチするルールがない場合は MEDIUM
        assert urgency == UrgencyLevel.MEDIUM
    
    @pytest.mark.asyncio
    async def test_send_notification_success(self):
        """通知送信成功のテスト"""
        self.mock_slack_service.send_notification.return_value = SlackResponse(
            success=True,
            status_code=200,
            message="OK"
        )
        
        result = await self.manager.send_notification(
            message="Test notification",
            alert_type=AlertType.INFO,
            context={"key": "value"}
        )
        
        assert result.success is True
        assert self.manager.metrics.total_notifications == 1
        assert self.manager.metrics.successful_notifications == 1
        
        # Slack サービスが呼ばれたことを確認
        self.mock_slack_service.send_notification.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_send_notification_failure(self):
        """通知送信失敗のテスト"""
        self.mock_slack_service.send_notification.return_value = SlackResponse(
            success=False,
            status_code=400,
            error_message="Bad Request"
        )
        
        result = await self.manager.send_notification(
            message="Test notification",
            alert_type=AlertType.ERROR
        )
        
        assert result.success is False
        assert self.manager.metrics.total_notifications == 1
        assert self.manager.metrics.failed_notifications == 1
    
    @pytest.mark.asyncio
    async def test_send_urgent_notification(self):
        """緊急通知送信のテスト"""
        self.mock_slack_service.send_alert.return_value = SlackResponse(
            success=True,
            status_code=200,
            message="OK"
        )
        
        result = await self.manager.send_urgent_notification(
            message="Critical system error",
            alert_type=AlertType.ERROR,
            context={"severity": "critical"},
            mention_channel=True,
            mention_users=["@admin"]
        )
        
        assert result.success is True
        
        # send_alert が呼ばれたことを確認
        self.mock_slack_service.send_alert.assert_called_once()
        call_args = self.mock_slack_service.send_alert.call_args
        assert "Critical system error" in call_args[0][1]  # message
        assert call_args[1]["mention_channel"] is True
    
    @pytest.mark.asyncio
    async def test_send_batch_notifications(self):
        """バッチ通知送信のテスト"""
        self.mock_slack_service.send_notification.return_value = SlackResponse(
            success=True,
            status_code=200,
            message="OK"
        )
        
        notifications = [
            {
                "message": "Error 1",
                "alert_type": AlertType.ERROR,
                "context": {"id": 1}
            },
            {
                "message": "Warning 1",
                "alert_type": AlertType.WARNING,
                "context": {"id": 2}
            },
            {
                "message": "Info 1",
                "alert_type": AlertType.INFO,
                "context": {"id": 3}
            }
        ]
        
        results = await self.manager.send_batch_notifications(notifications)
        
        assert len(results) == 3
        assert all(result.success for result in results)
        assert self.manager.metrics.total_notifications == 3
        assert self.manager.metrics.successful_notifications == 3
    
    def test_get_notification_schedule(self):
        """通知スケジュール取得のテスト"""
        schedule = self.manager._get_notification_schedule(UrgencyLevel.CRITICAL)
        assert schedule is not None
        assert schedule.urgency_level == UrgencyLevel.CRITICAL
        
        schedule = self.manager._get_notification_schedule(UrgencyLevel.LOW)
        assert schedule is not None
        assert schedule.urgency_level == UrgencyLevel.LOW
    
    def test_should_escalate(self):
        """エスカレーション判定のテスト"""
        # 連続失敗のエスカレーション
        should_escalate = self.manager._should_escalate(
            urgency_level=UrgencyLevel.HIGH,
            consecutive_failures=3,
            error_rate=0.1
        )
        assert should_escalate is True
        
        # 高いエラー率のエスカレーション
        should_escalate = self.manager._should_escalate(
            urgency_level=UrgencyLevel.MEDIUM,
            consecutive_failures=1,
            error_rate=0.9
        )
        assert should_escalate is True
        
        # エスカレーション不要
        should_escalate = self.manager._should_escalate(
            urgency_level=UrgencyLevel.LOW,
            consecutive_failures=1,
            error_rate=0.1
        )
        assert should_escalate is False
    
    @pytest.mark.asyncio
    async def test_escalate_notification(self):
        """通知エスカレーションのテスト"""
        self.mock_slack_service.send_alert.return_value = SlackResponse(
            success=True,
            status_code=200,
            message="OK"
        )
        
        original_message = "Critical error occurred"
        context = {"error_id": "ERR_001"}
        
        result = await self.manager._escalate_notification(
            original_message,
            AlertType.ERROR,
            UrgencyLevel.CRITICAL,
            context
        )
        
        assert result.success is True
        assert self.manager.metrics.escalated_notifications == 1
        
        # エスカレーション用の send_alert が呼ばれたことを確認
        self.mock_slack_service.send_alert.assert_called_once()
    
    def test_get_metrics_summary(self):
        """メトリクス概要取得のテスト"""
        # テストデータを追加
        self.manager.metrics.record_notification(
            UrgencyLevel.HIGH, AlertType.ERROR, True, False
        )
        self.manager.metrics.record_notification(
            UrgencyLevel.MEDIUM, AlertType.WARNING, False, True
        )
        
        summary = self.manager.get_metrics_summary()
        
        assert summary["total_notifications"] == 2
        assert summary["success_rate"] == 0.5
        assert summary["escalation_rate"] == 0.5
        assert UrgencyLevel.HIGH.value in summary["urgency_distribution"]
        assert AlertType.ERROR.value in summary["alert_type_distribution"]
    
    def test_reset_metrics(self):
        """メトリクスリセットのテスト"""
        # テストデータを追加
        self.manager.metrics.record_notification(
            UrgencyLevel.HIGH, AlertType.ERROR, True, False
        )
        
        assert self.manager.metrics.total_notifications == 1
        
        # リセット
        self.manager.reset_metrics()
        
        assert self.manager.metrics.total_notifications == 0
        assert self.manager.metrics.successful_notifications == 0
        assert len(self.manager.metrics.urgency_distribution) == 0
    
    def test_update_notification_schedule(self):
        """通知スケジュール更新のテスト"""
        new_schedule = NotificationSchedule(
            urgency_level=UrgencyLevel.CUSTOM,
            initial_delay_seconds=5,
            retry_intervals=[10, 30, 60],
            max_retries=3
        )
        
        self.manager.update_notification_schedule(new_schedule)
        
        # カスタムスケジュールが追加されたことを確認
        schedule = self.manager._get_notification_schedule(UrgencyLevel.CUSTOM)
        assert schedule is not None
        assert schedule.initial_delay_seconds == 5
        assert schedule.retry_intervals == [10, 30, 60]


if __name__ == "__main__":
    pytest.main([__file__])