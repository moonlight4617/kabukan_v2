"""
CloudWatch統合サービスのテスト
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from botocore.exceptions import ClientError, NoCredentialsError

from src.services.cloudwatch_service import (
    CloudWatchService,
    StructuredLogger,
    LogLevel,
    MetricUnit,
    LogEvent,
    MetricDatum
)


class TestLogEvent:
    """LogEventクラスのテスト"""
    
    def test_log_event_creation(self):
        """ログイベントの作成"""
        timestamp = datetime.now()
        event = LogEvent(
            timestamp=timestamp,
            level=LogLevel.INFO,
            message="テストメッセージ",
            logger_name="test_logger",
            context={"key": "value"}
        )
        
        assert event.timestamp == timestamp
        assert event.level == LogLevel.INFO
        assert event.message == "テストメッセージ"
        assert event.logger_name == "test_logger"
        assert event.context == {"key": "value"}
    
    def test_log_event_to_dict(self):
        """ログイベントの辞書変換"""
        timestamp = datetime(2023, 1, 1, 12, 0, 0)
        event = LogEvent(
            timestamp=timestamp,
            level=LogLevel.ERROR,
            message="エラーメッセージ",
            logger_name="error_logger",
            context={"error_code": 500}
        )
        
        result = event.to_dict()
        
        assert result["timestamp"] == "2023-01-01T12:00:00"
        assert result["level"] == "ERROR"
        assert result["message"] == "エラーメッセージ"
        assert result["logger"] == "error_logger"
        assert result["context"] == {"error_code": 500}


class TestMetricDatum:
    """MetricDatumクラスのテスト"""
    
    def test_metric_datum_creation(self):
        """メトリクスデータの作成"""
        metric = MetricDatum(
            name="TestMetric",
            value=100.0,
            unit=MetricUnit.COUNT,
            dimensions={"Environment": "Test"}
        )
        
        assert metric.name == "TestMetric"
        assert metric.value == 100.0
        assert metric.unit == MetricUnit.COUNT
        assert metric.dimensions == {"Environment": "Test"}
        assert metric.timestamp is not None
    
    def test_metric_datum_auto_timestamp(self):
        """自動タイムスタンプ設定"""
        before = datetime.utcnow()
        metric = MetricDatum(name="TestMetric", value=50.0)
        after = datetime.utcnow()
        
        assert before <= metric.timestamp <= after


class TestCloudWatchService:
    """CloudWatchServiceクラスのテスト"""
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_initialization_success(self, mock_boto3):
        """正常な初期化"""
        mock_session = Mock()
        mock_credentials = Mock()
        mock_session.get_credentials.return_value = mock_credentials
        mock_boto3.Session.return_value = mock_session
        
        mock_logs_client = Mock()
        mock_cloudwatch_client = Mock()
        mock_boto3.client.side_effect = [mock_logs_client, mock_cloudwatch_client]
        
        # ロググループとストリームの設定
        mock_logs_client.describe_log_groups.return_value = {'logGroups': []}
        mock_logs_client.create_log_group.return_value = {}
        mock_logs_client.describe_log_streams.return_value = {'logStreams': []}
        mock_logs_client.create_log_stream.return_value = {}
        
        service = CloudWatchService()
        
        assert service.is_available
        assert mock_boto3.client.call_count == 2
        mock_logs_client.create_log_group.assert_called_once()
        mock_logs_client.create_log_stream.assert_called_once()
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_initialization_no_credentials(self, mock_boto3):
        """認証情報なしの初期化"""
        mock_session = Mock()
        mock_session.get_credentials.return_value = None
        mock_boto3.Session.return_value = mock_session
        
        with pytest.raises(NoCredentialsError):
            CloudWatchService()
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', False)
    def test_initialization_no_boto3(self):
        """boto3なしの初期化"""
        service = CloudWatchService()
        assert not service.is_available
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_send_log_success(self, mock_boto3):
        """ログ送信成功"""
        mock_logs_client, _ = self._setup_mock_clients(mock_boto3)
        mock_logs_client.put_log_events.return_value = {'nextSequenceToken': 'token123'}
        
        service = CloudWatchService()
        result = service.send_log(
            LogLevel.INFO,
            "テストログ",
            {"key": "value"},
            "test_logger"
        )
        
        assert result is True
        mock_logs_client.put_log_events.assert_called_once()
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_send_log_sequence_token_error(self, mock_boto3):
        """シーケンストークンエラーのリトライ"""
        mock_logs_client, _ = self._setup_mock_clients(mock_boto3)
        
        # 最初の呼び出しでシーケンストークンエラー、2回目で成功
        mock_logs_client.put_log_events.side_effect = [
            ClientError(
                {'Error': {'Code': 'InvalidSequenceTokenException'}},
                'PutLogEvents'
            ),
            {'nextSequenceToken': 'new_token'}
        ]
        
        # シーケンストークン再取得のモック
        mock_logs_client.describe_log_streams.return_value = {
            'logStreams': [
                {
                    'logStreamName': service._generate_log_stream_name(),
                    'uploadSequenceToken': 'refreshed_token'
                }
            ]
        }
        
        service = CloudWatchService()
        result = service.send_log(LogLevel.INFO, "テストログ")
        
        assert result is True
        assert mock_logs_client.put_log_events.call_count == 2
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_send_metric_success(self, mock_boto3):
        """メトリクス送信成功"""
        _, mock_cloudwatch_client = self._setup_mock_clients(mock_boto3)
        mock_cloudwatch_client.put_metric_data.return_value = {}
        
        service = CloudWatchService()
        metric = MetricDatum(
            name="TestMetric",
            value=100.0,
            unit=MetricUnit.COUNT,
            dimensions={"Environment": "Test"}
        )
        
        result = service.send_metric(metric)
        
        assert result is True
        mock_cloudwatch_client.put_metric_data.assert_called_once()
        
        # 呼び出し引数の検証
        call_args = mock_cloudwatch_client.put_metric_data.call_args
        assert call_args[1]['Namespace'] == 'StockAnalysis'
        metric_data = call_args[1]['MetricData'][0]
        assert metric_data['MetricName'] == 'TestMetric'
        assert metric_data['Value'] == 100.0
        assert metric_data['Unit'] == 'Count'
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_send_metrics_batch(self, mock_boto3):
        """メトリクスバッチ送信"""
        _, mock_cloudwatch_client = self._setup_mock_clients(mock_boto3)
        mock_cloudwatch_client.put_metric_data.return_value = {}
        
        service = CloudWatchService()
        metrics = [
            MetricDatum(name=f"Metric{i}", value=float(i))
            for i in range(25)  # 25個のメトリクス（20個ずつバッチ処理）
        ]
        
        success_count = service.send_metrics(metrics)
        
        assert success_count == 25
        assert mock_cloudwatch_client.put_metric_data.call_count == 2  # 2バッチ
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_log_analysis_workflow(self, mock_boto3):
        """分析ワークフローログ"""
        mock_logs_client, mock_cloudwatch_client = self._setup_mock_clients(mock_boto3)
        mock_logs_client.put_log_events.return_value = {'nextSequenceToken': 'token'}
        mock_cloudwatch_client.put_metric_data.return_value = {}
        
        service = CloudWatchService()
        
        # 分析開始ログ
        result1 = service.log_analysis_start("daily", ["7203", "AAPL"])
        assert result1 is True
        
        # 分析完了ログ
        result2 = service.log_analysis_completion("daily", 2.5, 3, True)
        assert result2 is True
        
        # パフォーマンスメトリクス
        result3 = service.send_performance_metrics("daily", 2.5, 3, 10)
        assert result3 is True
        
        assert mock_logs_client.put_log_events.call_count == 2
        assert mock_cloudwatch_client.put_metric_data.call_count == 1
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_api_call_logging(self, mock_boto3):
        """API呼び出しログ"""
        mock_logs_client, _ = self._setup_mock_clients(mock_boto3)
        mock_logs_client.put_log_events.return_value = {'nextSequenceToken': 'token'}
        
        service = CloudWatchService()
        
        # 成功ログ
        result1 = service.log_api_call("GeminiAPI", "analyze", 1.2, True)
        assert result1 is True
        
        # 失敗ログ
        result2 = service.log_api_call("GoogleSheets", "read", 0.8, False, "Rate limit exceeded")
        assert result2 is True
        
        assert mock_logs_client.put_log_events.call_count == 2
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_error_metric(self, mock_boto3):
        """エラーメトリクス"""
        _, mock_cloudwatch_client = self._setup_mock_clients(mock_boto3)
        mock_cloudwatch_client.put_metric_data.return_value = {}
        
        service = CloudWatchService()
        result = service.send_error_metric("ApiTimeout", "GeminiAPI")
        
        assert result is True
        
        call_args = mock_cloudwatch_client.put_metric_data.call_args
        metric_data = call_args[1]['MetricData'][0]
        assert metric_data['MetricName'] == 'Errors'
        assert metric_data['Value'] == 1
        assert metric_data['Dimensions'] == [
            {'Name': 'ErrorType', 'Value': 'ApiTimeout'},
            {'Name': 'Component', 'Value': 'GeminiAPI'}
        ]
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_validate_connection_success(self, mock_boto3):
        """接続検証成功"""
        mock_logs_client, mock_cloudwatch_client = self._setup_mock_clients(mock_boto3)
        mock_logs_client.describe_log_groups.return_value = {'logGroups': []}
        mock_cloudwatch_client.list_metrics.return_value = {'Metrics': []}
        
        service = CloudWatchService()
        result = service.validate_connection()
        
        assert result is True
    
    @patch('src.services.cloudwatch_service.AWS_AVAILABLE', True)
    @patch('src.services.cloudwatch_service.boto3')
    def test_validate_connection_failure(self, mock_boto3):
        """接続検証失敗"""
        mock_logs_client, mock_cloudwatch_client = self._setup_mock_clients(mock_boto3)
        mock_logs_client.describe_log_groups.side_effect = ClientError(
            {'Error': {'Code': 'AccessDenied'}}, 'DescribeLogGroups'
        )
        
        service = CloudWatchService()
        result = service.validate_connection()
        
        assert result is False
    
    def test_service_not_available(self):
        """サービス利用不可時の動作"""
        service = CloudWatchService()
        service._logs_client = None
        service._cloudwatch_client = None
        
        # ログ送信はローカルにフォールバック
        result1 = service.send_log(LogLevel.INFO, "テスト")
        assert result1 is False
        
        # メトリクス送信は警告ログ
        metric = MetricDatum(name="TestMetric", value=1.0)
        result2 = service.send_metric(metric)
        assert result2 is False
        
        # 接続検証は失敗
        result3 = service.validate_connection()
        assert result3 is False
    
    def test_get_service_status(self):
        """サービス状況取得"""
        service = CloudWatchService()
        status = service.get_service_status()
        
        assert "available" in status
        assert "log_group_name" in status
        assert "log_stream_name" in status
        assert "namespace" in status
        assert "region" in status
        assert "connection_valid" in status
    
    def _setup_mock_clients(self, mock_boto3):
        """モッククライアントのセットアップ"""
        mock_session = Mock()
        mock_credentials = Mock()
        mock_session.get_credentials.return_value = mock_credentials
        mock_boto3.Session.return_value = mock_session
        
        mock_logs_client = Mock()
        mock_cloudwatch_client = Mock()
        mock_boto3.client.side_effect = [mock_logs_client, mock_cloudwatch_client]
        
        # デフォルトの正常レスポンス
        mock_logs_client.describe_log_groups.return_value = {'logGroups': []}
        mock_logs_client.create_log_group.return_value = {}
        mock_logs_client.describe_log_streams.return_value = {'logStreams': []}
        mock_logs_client.create_log_stream.return_value = {}
        
        return mock_logs_client, mock_cloudwatch_client


class TestStructuredLogger:
    """StructuredLoggerクラスのテスト"""
    
    def test_logger_methods(self):
        """ロガーメソッドの動作"""
        mock_cloudwatch = Mock()
        mock_cloudwatch.send_log.return_value = True
        
        logger = StructuredLogger(mock_cloudwatch, "test_logger")
        
        # 各レベルのログメソッドをテスト
        logger.debug("デバッグメッセージ", debug_info="test")
        logger.info("情報メッセージ", user_id=123)
        logger.warning("警告メッセージ", warning_code="W001")
        logger.error("エラーメッセージ", error_code="E001")
        logger.critical("クリティカルメッセージ", severity="high")
        
        # CloudWatchサービスが5回呼ばれることを確認
        assert mock_cloudwatch.send_log.call_count == 5
        
        # 呼び出し引数の検証
        calls = mock_cloudwatch.send_log.call_args_list
        assert calls[0][0][0] == LogLevel.DEBUG
        assert calls[1][0][0] == LogLevel.INFO
        assert calls[2][0][0] == LogLevel.WARNING
        assert calls[3][0][0] == LogLevel.ERROR
        assert calls[4][0][0] == LogLevel.CRITICAL
    
    def test_logger_context_passing(self):
        """コンテキスト情報の引き渡し"""
        mock_cloudwatch = Mock()
        mock_cloudwatch.send_log.return_value = True
        
        logger = StructuredLogger(mock_cloudwatch, "context_logger")
        logger.info("テストメッセージ", user_id=456, action="login", ip="192.168.1.1")
        
        call_args = mock_cloudwatch.send_log.call_args
        context = call_args[0][2]  # 3番目の引数がコンテキスト
        
        assert context["user_id"] == 456
        assert context["action"] == "login"
        assert context["ip"] == "192.168.1.1"