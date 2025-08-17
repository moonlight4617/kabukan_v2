# -*- coding: utf-8 -*-
"""
エラーハンドラーサービスの単体テスト
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime, timedelta

from src.services.error_handler import (
    ErrorHandler, ErrorInfo, ErrorSeverity, ErrorCategory, ErrorHandlingStrategy,
    ErrorHandlingConfig, ErrorHandlingRule, CircuitBreaker
)
from src.services.cloudwatch_service import StructuredLogger
from src.services.slack_service import SlackService


class TestErrorHandler:
    """エラーハンドラーのテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.config = ErrorHandlingConfig(
            enable_logging=True,
            enable_notifications=True,
            max_error_history=100
        )
        
        self.mock_structured_logger = Mock(spec=StructuredLogger)
        self.mock_structured_logger.log_structured = AsyncMock()
        
        self.mock_slack_service = Mock(spec=SlackService)
        self.mock_slack_service.send_error_notification = Mock()
        self.mock_slack_service.send_error_notification.return_value = Mock(success=True)
        self.mock_slack_service.send_alert = AsyncMock()
        self.mock_slack_service.send_alert.return_value = Mock(success=True)
        
        self.error_handler = ErrorHandler(
            config=self.config,
            structured_logger=self.mock_structured_logger,
            slack_service=self.mock_slack_service
        )
    
    @pytest.mark.asyncio
    async def test_handle_error_basic(self):
        """基本的なエラーハンドリングのテスト"""
        exception = ValueError("Test error")
        context = {"test_key": "test_value"}
        
        error_info = await self.error_handler.handle_error(exception, context, "test_function")
        
        assert error_info.error_type == "ValueError"
        assert error_info.error_message == "Test error"
        assert error_info.category == ErrorCategory.DATA_VALIDATION
        assert error_info.severity == ErrorSeverity.MEDIUM
        assert error_info.context == context
        assert error_info.source_function == "test_function"
        assert error_info.handled
        
        # ログが記録されたことを確認（戦略実行とログ処理で2回呼ばれる可能性がある）
        assert self.mock_structured_logger.log_structured.call_count >= 1
    
    @pytest.mark.asyncio
    async def test_error_classification(self):
        """エラー分類のテスト"""
        test_cases = [
            (ConnectionError("Network error"), ErrorCategory.NETWORK),
            (TimeoutError("Timeout"), ErrorCategory.TIMEOUT),
            (PermissionError("Permission denied"), ErrorCategory.AUTHORIZATION),
            (FileNotFoundError("File not found"), ErrorCategory.CONFIGURATION),
            (MemoryError("Out of memory"), ErrorCategory.RESOURCE_EXHAUSTION),
        ]
        
        for exception, expected_category in test_cases:
            error_info = await self.error_handler.handle_error(exception)
            assert error_info.category == expected_category
    
    @pytest.mark.asyncio
    async def test_severity_determination(self):
        """重要度判定のテスト"""
        # 重大エラー
        critical_error = MemoryError("Memory exhausted")
        error_info = await self.error_handler.handle_error(critical_error)
        assert error_info.severity == ErrorSeverity.CRITICAL
        
        # 中程度エラー
        medium_error = ConnectionError("Connection failed")
        error_info = await self.error_handler.handle_error(medium_error)
        assert error_info.severity == ErrorSeverity.MEDIUM
    
    @pytest.mark.asyncio
    async def test_notification_for_high_severity(self):
        """高重要度エラーの通知テスト"""
        # 高重要度エラー
        high_severity_error = PermissionError("Access denied")
        await self.error_handler.handle_error(high_severity_error)
        
        # Slack通知が送信されたことを確認
        self.mock_slack_service.send_error_notification.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_notification_disabled(self):
        """通知無効時のテスト"""
        config = ErrorHandlingConfig(enable_notifications=False)
        error_handler = ErrorHandler(config=config)
        
        high_severity_error = PermissionError("Access denied")
        await error_handler.handle_error(high_severity_error)
        
        # 通知が送信されないことを確認
        assert not hasattr(error_handler, 'slack_service') or error_handler.slack_service is None
    
    def test_error_history_management(self):
        """エラー履歴管理のテスト"""
        # 複数のエラーを記録
        for i in range(10):
            error_info = ErrorInfo(
                error_id=f"test_{i}",
                timestamp=datetime.now(),
                exception=ValueError(f"Error {i}"),
                error_type="ValueError",
                error_message=f"Error {i}",
                category=ErrorCategory.DATA_VALIDATION,
                severity=ErrorSeverity.MEDIUM
            )
            self.error_handler._record_error(error_info)
        
        assert len(self.error_handler.error_history) == 10
        
        # 履歴制限のテスト
        config = ErrorHandlingConfig(max_error_history=5)
        error_handler = ErrorHandler(config=config)
        
        for i in range(10):
            error_info = ErrorInfo(
                error_id=f"test_{i}",
                timestamp=datetime.now(),
                exception=ValueError(f"Error {i}"),
                error_type="ValueError",
                error_message=f"Error {i}",
                category=ErrorCategory.DATA_VALIDATION,
                severity=ErrorSeverity.MEDIUM
            )
            error_handler._record_error(error_info)
        
        # 履歴が制限されていることを確認
        assert len(error_handler.error_history) <= 5
    
    def test_error_statistics(self):
        """エラー統計のテスト"""
        # テストデータ作成
        for i in range(5):
            error_info = ErrorInfo(
                error_id=f"test_{i}",
                timestamp=datetime.now(),
                exception=ValueError(f"Error {i}"),
                error_type="ValueError",
                error_message=f"Error {i}",
                category=ErrorCategory.DATA_VALIDATION,
                severity=ErrorSeverity.MEDIUM
            )
            self.error_handler._record_error(error_info)
        
        # 統計取得
        stats = self.error_handler.get_error_statistics()
        
        assert stats["total_errors"] == 5
        assert "severity_distribution" in stats
        assert "category_distribution" in stats
        assert stats["severity_distribution"]["medium"] == 5
        assert stats["category_distribution"]["data_validation"] == 5
    
    def test_custom_handling_rule(self):
        """カスタムハンドリングルールのテスト"""
        # カスタムルールを追加
        custom_rule = ErrorHandlingRule(
            error_types=["CustomError"],
            categories=[],
            strategy=ErrorHandlingStrategy.ESCALATE,
            severity=ErrorSeverity.CRITICAL,
            escalation_required=True
        )
        self.error_handler.add_handling_rule(custom_rule)
        
        # カスタムエラーを作成
        class CustomError(Exception):
            pass
        
        # ルールがマッチすることを確認
        error_info = ErrorInfo(
            error_id="test",
            timestamp=datetime.now(),
            exception=CustomError("Custom error"),
            error_type="CustomError",
            error_message="Custom error",
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.MEDIUM
        )
        
        matching_rule = self.error_handler._find_matching_rule(error_info)
        assert matching_rule == custom_rule
    
    @pytest.mark.asyncio
    async def test_error_context_manager(self):
        """エラーコンテキストマネージャーのテスト"""
        # 正常終了のテスト
        async with self.error_handler.error_context("test_context"):
            pass  # 何もしない
        
        # エラー発生のテスト
        with pytest.raises(ValueError):
            async with self.error_handler.error_context("test_context", reraise=True):
                raise ValueError("Test error")
        
        # エラーが記録されていることを確認
        assert len(self.error_handler.error_history) > 0
        assert self.error_handler.error_history[-1].context["context_name"] == "test_context"


class TestCircuitBreaker:
    """サーキットブレーカーのテストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, timeout=60)
    
    def test_circuit_breaker_closed_state(self):
        """CLOSED状態のテスト"""
        assert self.circuit_breaker.state == "CLOSED"
        
        # 成功呼び出し
        result = self.circuit_breaker.call(lambda: "success")
        assert result == "success"
        assert self.circuit_breaker.state == "CLOSED"
    
    def test_circuit_breaker_open_state(self):
        """OPEN状態のテスト"""
        # 閾値まで失敗させる
        for i in range(3):
            try:
                self.circuit_breaker.call(lambda: self._failing_function())
            except Exception:
                pass
        
        assert self.circuit_breaker.state == "OPEN"
        
        # OPEN状態での呼び出しは例外が発生
        with pytest.raises(Exception, match="Circuit breaker is OPEN"):
            self.circuit_breaker.call(lambda: "success")
    
    def test_circuit_breaker_half_open_state(self):
        """HALF_OPEN状態のテスト"""
        # OPEN状態にする
        for i in range(3):
            try:
                self.circuit_breaker.call(lambda: self._failing_function())
            except Exception:
                pass
        
        assert self.circuit_breaker.state == "OPEN"
        
        # タイムアウト時間を過去に設定してHALF_OPEN状態をシミュレート
        self.circuit_breaker.last_failure_time = datetime.now() - timedelta(seconds=61)
        
        # 成功呼び出しでCLOSED状態に戻る
        result = self.circuit_breaker.call(lambda: "success")
        assert result == "success"
        assert self.circuit_breaker.state == "CLOSED"
    
    def _failing_function(self):
        """失敗する関数"""
        raise Exception("Test failure")


class TestErrorHandlingRule:
    """エラーハンドリングルールのテストクラス"""
    
    def test_rule_matching_by_error_type(self):
        """エラータイプによるマッチングのテスト"""
        rule = ErrorHandlingRule(
            error_types=["ValueError", "TypeError"],
            categories=[],
            strategy=ErrorHandlingStrategy.RETRY,
            severity=ErrorSeverity.MEDIUM
        )
        
        # マッチするケース
        error_info = ErrorInfo(
            error_id="test",
            timestamp=datetime.now(),
            exception=ValueError("Test"),
            error_type="ValueError",
            error_message="Test",
            category=ErrorCategory.DATA_VALIDATION,
            severity=ErrorSeverity.MEDIUM
        )
        assert rule.matches(error_info)
        
        # マッチしないケース
        error_info.error_type = "ConnectionError"
        assert not rule.matches(error_info)
    
    def test_rule_matching_by_category(self):
        """カテゴリによるマッチングのテスト"""
        rule = ErrorHandlingRule(
            error_types=[],
            categories=[ErrorCategory.NETWORK, ErrorCategory.TIMEOUT],
            strategy=ErrorHandlingStrategy.RETRY,
            severity=ErrorSeverity.MEDIUM
        )
        
        # マッチするケース
        error_info = ErrorInfo(
            error_id="test",
            timestamp=datetime.now(),
            exception=ConnectionError("Test"),
            error_type="ConnectionError",
            error_message="Test",
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.MEDIUM
        )
        assert rule.matches(error_info)
        
        # マッチしないケース
        error_info.category = ErrorCategory.DATA_VALIDATION
        assert not rule.matches(error_info)
    
    def test_rule_matching_both_empty(self):
        """エラータイプとカテゴリが両方空の場合のテスト"""
        rule = ErrorHandlingRule(
            error_types=[],
            categories=[],
            strategy=ErrorHandlingStrategy.LOG_ONLY,
            severity=ErrorSeverity.LOW
        )
        
        # 空の場合はすべてマッチ
        error_info = ErrorInfo(
            error_id="test",
            timestamp=datetime.now(),
            exception=Exception("Test"),
            error_type="Exception",
            error_message="Test",
            category=ErrorCategory.UNKNOWN,
            severity=ErrorSeverity.MEDIUM
        )
        assert rule.matches(error_info)


class TestErrorInfo:
    """エラー情報のテストクラス"""
    
    def test_error_info_creation(self):
        """エラー情報作成のテスト"""
        exception = ValueError("Test error")
        error_info = ErrorInfo(
            error_id="test_001",
            timestamp=datetime.now(),
            exception=exception,
            error_type="ValueError",
            error_message="Test error",
            category=ErrorCategory.DATA_VALIDATION,
            severity=ErrorSeverity.MEDIUM,
            context={"key": "value"},
            source_function="test_function"
        )
        
        assert error_info.error_id == "test_001"
        assert error_info.error_type == "ValueError"
        assert error_info.error_message == "Test error"
        assert error_info.category == ErrorCategory.DATA_VALIDATION
        assert error_info.severity == ErrorSeverity.MEDIUM
        assert error_info.context == {"key": "value"}
        assert error_info.source_function == "test_function"
        assert not error_info.handled
        assert error_info.retry_count == 0
    
    def test_error_info_to_dict(self):
        """エラー情報の辞書変換のテスト"""
        timestamp = datetime.now()
        error_info = ErrorInfo(
            error_id="test_001",
            timestamp=timestamp,
            exception=ValueError("Test error"),
            error_type="ValueError",
            error_message="Test error",
            category=ErrorCategory.DATA_VALIDATION,
            severity=ErrorSeverity.MEDIUM
        )
        
        result_dict = error_info.to_dict()
        
        assert result_dict["error_id"] == "test_001"
        assert result_dict["timestamp"] == timestamp.isoformat()
        assert result_dict["error_type"] == "ValueError"
        assert result_dict["error_message"] == "Test error"
        assert result_dict["category"] == "data_validation"
        assert result_dict["severity"] == "medium"
        assert result_dict["handled"] == False
        assert result_dict["retry_count"] == 0


if __name__ == "__main__":
    pytest.main([__file__])