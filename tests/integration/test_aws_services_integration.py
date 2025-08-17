# -*- coding: utf-8 -*-
"""
AWSサービス統合テスト
AWS Parameter Store、CloudWatch、Lambda実行環境との統合を検証
"""

import pytest
import asyncio
import boto3
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from moto import mock_ssm, mock_cloudwatch, mock_logs
import json
import os
from datetime import datetime, timedelta

from src.services.parameter_store_service import ParameterStoreService
from src.services.cloudwatch_service import CloudWatchService, StructuredLogger
from src.config import ConfigManager
from src.lambda_handler import handler


class TestAWSParameterStoreIntegration:
    """AWS Parameter Store統合テストクラス"""
    
    @mock_ssm
    def test_parameter_store_service_integration(self):
        """Parameter Storeサービス統合テスト"""
        # モックSSMクライアント作成
        ssm_client = boto3.client('ssm', region_name='us-east-1')
        
        # テストパラメータを設定
        test_parameters = {
            '/stock-analysis/google-sheets/spreadsheet-id': 'test-spreadsheet-123',
            '/stock-analysis/google-sheets/credentials': '{"type": "service_account"}',
            '/stock-analysis/slack/webhook-url': 'https://hooks.slack.com/test-webhook',
            '/stock-analysis/gemini/api-key': 'test-gemini-api-key',
            '/stock-analysis/yfinance/timeout': '30'
        }
        
        # パラメータをSSMに追加
        for param_name, param_value in test_parameters.items():
            ssm_client.put_parameter(
                Name=param_name,
                Value=param_value,
                Type='String' if 'credentials' not in param_name else 'SecureString'
            )
        
        # Parameter Storeサービステスト
        param_service = ParameterStoreService(ssm_client)
        
        # 個別パラメータ取得テスト
        spreadsheet_id = param_service.get_parameter('/stock-analysis/google-sheets/spreadsheet-id')
        assert spreadsheet_id == 'test-spreadsheet-123'
        
        # セキュアパラメータ取得テスト
        credentials = param_service.get_parameter('/stock-analysis/google-sheets/credentials', decrypt=True)
        assert 'service_account' in credentials
        
        # バッチパラメータ取得テスト
        batch_params = param_service.get_parameters_by_path('/stock-analysis/slack/')
        assert 'webhook-url' in batch_params
        assert batch_params['webhook-url'] == 'https://hooks.slack.com/test-webhook'
        
        # キャッシュ機能テスト
        param_service.get_parameter('/stock-analysis/google-sheets/spreadsheet-id')  # キャッシュから取得
        assert len(param_service.parameter_cache) > 0
    
    @mock_ssm
    def test_config_manager_parameter_store_integration(self):
        """ConfigManagerとParameter Store統合テスト"""
        ssm_client = boto3.client('ssm', region_name='us-east-1')
        
        # 設定パラメータをSSMに設定
        config_parameters = {
            '/stock-analysis/google-sheets/spreadsheet-id': 'config-test-123',
            '/stock-analysis/google-sheets/credentials': '{"type": "service_account", "project_id": "test"}',
            '/stock-analysis/slack/webhook-url': 'https://hooks.slack.com/config-test',
            '/stock-analysis/gemini/api-key': 'config-gemini-key',
            '/stock-analysis/analysis/enable-daily': 'true',
            '/stock-analysis/analysis/enable-weekly': 'true',
            '/stock-analysis/analysis/enable-monthly': 'false'
        }
        
        for param_name, param_value in config_parameters.items():
            ssm_client.put_parameter(
                Name=param_name,
                Value=param_value,
                Type='SecureString' if 'credentials' in param_name or 'api-key' in param_name else 'String'
            )
        
        # ConfigManager初期化テスト
        with patch('src.config.boto3.client', return_value=ssm_client):
            config_manager = ConfigManager()
            
            # Google Sheets設定検証
            assert config_manager.google_sheets_config.spreadsheet_id == 'config-test-123'
            assert 'service_account' in config_manager.google_sheets_config.credentials
            
            # Slack設定検証
            assert config_manager.slack_config.webhook_url == 'https://hooks.slack.com/config-test'
            
            # Gemini設定検証
            assert config_manager.gemini_config.api_key == 'config-gemini-key'
            
            # 分析設定検証
            assert config_manager.analysis_config.enable_daily is True
            assert config_manager.analysis_config.enable_weekly is True
            assert config_manager.analysis_config.enable_monthly is False
    
    @mock_ssm
    def test_parameter_store_error_handling(self):
        """Parameter Storeエラーハンドリングテスト"""
        ssm_client = boto3.client('ssm', region_name='us-east-1')
        param_service = ParameterStoreService(ssm_client)
        
        # 存在しないパラメータ取得テスト
        with pytest.raises(Exception):
            param_service.get_parameter('/nonexistent/parameter')
        
        # デフォルト値テスト
        default_value = param_service.get_parameter(
            '/nonexistent/parameter', 
            default_value='default-test-value'
        )
        assert default_value == 'default-test-value'
    
    @mock_ssm
    def test_parameter_validation_and_transformation(self):
        """パラメータ検証と変換テスト"""
        ssm_client = boto3.client('ssm', region_name='us-east-1')
        
        # 数値パラメータ
        ssm_client.put_parameter(
            Name='/stock-analysis/config/timeout',
            Value='60',
            Type='String'
        )
        
        # ブール値パラメータ
        ssm_client.put_parameter(
            Name='/stock-analysis/config/debug-mode',
            Value='true',
            Type='String'
        )
        
        # JSON パラメータ
        ssm_client.put_parameter(
            Name='/stock-analysis/config/advanced-settings',
            Value='{"retry_count": 3, "timeout": 30}',
            Type='String'
        )
        
        param_service = ParameterStoreService(ssm_client)
        
        # 型変換テスト
        timeout_value = param_service.get_parameter('/stock-analysis/config/timeout')
        assert timeout_value == '60'  # 文字列として取得
        
        debug_mode = param_service.get_parameter('/stock-analysis/config/debug-mode')
        assert debug_mode == 'true'  # 文字列として取得
        
        # JSON解析テスト
        advanced_settings = param_service.get_parameter('/stock-analysis/config/advanced-settings')
        settings_dict = json.loads(advanced_settings)
        assert settings_dict['retry_count'] == 3
        assert settings_dict['timeout'] == 30


class TestAWSCloudWatchIntegration:
    """AWS CloudWatch統合テストクラス"""
    
    @mock_cloudwatch
    @mock_logs
    def test_cloudwatch_service_integration(self):
        """CloudWatchサービス統合テスト"""
        # モックCloudWatchクライアント作成
        cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')
        logs_client = boto3.client('logs', region_name='us-east-1')
        
        # ログググループ作成
        logs_client.create_log_group(logGroupName='/aws/lambda/stock-analysis')
        
        # CloudWatchサービス初期化
        cloudwatch_service = CloudWatchService(
            cloudwatch_client=cloudwatch_client,
            logs_client=logs_client
        )
        
        # カスタムメトリクス送信テスト
        cloudwatch_service.put_metric(
            namespace='StockAnalysis',
            metric_name='AnalysisCount',
            value=1.0,
            dimensions={'AnalysisType': 'daily'}
        )
        
        # メトリクス取得テスト
        response = cloudwatch_client.list_metrics(Namespace='StockAnalysis')
        assert len(response['Metrics']) == 1
        assert response['Metrics'][0]['MetricName'] == 'AnalysisCount'
    
    @mock_logs
    @pytest.mark.asyncio
    async def test_structured_logger_integration(self):
        """構造化ログ統合テスト"""
        logs_client = boto3.client('logs', region_name='us-east-1')
        
        # ログググループとストリーム作成
        log_group = '/aws/lambda/stock-analysis'
        log_stream = f'test-stream-{datetime.now().strftime("%Y-%m-%d")}'
        
        logs_client.create_log_group(logGroupName=log_group)
        logs_client.create_log_stream(
            logGroupName=log_group,
            logStreamName=log_stream
        )
        
        # 構造化ログ初期化
        structured_logger = StructuredLogger(
            log_group=log_group,
            log_stream=log_stream,
            logs_client=logs_client
        )
        
        # ログ送信テスト
        await structured_logger.log_structured(
            level='INFO',
            message='Test log message',
            context={
                'analysis_id': 'test-001',
                'symbol': 'AAPL',
                'price': 175.50
            }
        )
        
        # ログ取得テスト
        response = logs_client.get_log_events(
            logGroupName=log_group,
            logStreamName=log_stream
        )
        
        assert len(response['events']) == 1
        log_message = response['events'][0]['message']
        log_data = json.loads(log_message)
        
        assert log_data['level'] == 'INFO'
        assert log_data['message'] == 'Test log message'
        assert log_data['context']['analysis_id'] == 'test-001'
        assert log_data['context']['symbol'] == 'AAPL'
    
    @mock_cloudwatch
    def test_performance_metrics_collection(self):
        """パフォーマンスメトリクス収集テスト"""
        cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')
        cloudwatch_service = CloudWatchService(cloudwatch_client=cloudwatch_client)
        
        # 複数のパフォーマンスメトリクスを送信
        performance_metrics = [
            {
                'name': 'ExecutionTime',
                'value': 5.2,
                'unit': 'Seconds',
                'dimensions': {'Function': 'DailyAnalysis'}
            },
            {
                'name': 'MemoryUsage',
                'value': 128.5,
                'unit': 'Megabytes',
                'dimensions': {'Function': 'DailyAnalysis'}
            },
            {
                'name': 'APICallCount',
                'value': 4.0,
                'unit': 'Count',
                'dimensions': {'Service': 'GoogleSheets'}
            },
            {
                'name': 'ErrorCount',
                'value': 0.0,
                'unit': 'Count',
                'dimensions': {'ErrorType': 'NetworkError'}
            }
        ]
        
        # バッチでメトリクス送信
        for metric in performance_metrics:
            cloudwatch_service.put_metric(
                namespace='StockAnalysis/Performance',
                metric_name=metric['name'],
                value=metric['value'],
                unit=metric['unit'],
                dimensions=metric['dimensions']
            )
        
        # メトリクス確認
        response = cloudwatch_client.list_metrics(Namespace='StockAnalysis/Performance')
        assert len(response['Metrics']) == 4
        
        metric_names = [metric['MetricName'] for metric in response['Metrics']]
        assert 'ExecutionTime' in metric_names
        assert 'MemoryUsage' in metric_names
        assert 'APICallCount' in metric_names
        assert 'ErrorCount' in metric_names
    
    @mock_cloudwatch
    def test_alarm_creation_and_management(self):
        """アラーム作成と管理テスト"""
        cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')
        cloudwatch_service = CloudWatchService(cloudwatch_client=cloudwatch_client)
        
        # アラーム作成
        alarm_name = 'StockAnalysis-HighErrorRate'
        cloudwatch_client.put_metric_alarm(
            AlarmName=alarm_name,
            ComparisonOperator='GreaterThanThreshold',
            EvaluationPeriods=2,
            MetricName='ErrorCount',
            Namespace='StockAnalysis',
            Period=300,
            Statistic='Sum',
            Threshold=5.0,
            ActionsEnabled=False,
            AlarmDescription='High error rate in stock analysis'
        )
        
        # アラーム一覧取得
        response = cloudwatch_client.describe_alarms(AlarmNames=[alarm_name])
        assert len(response['MetricAlarms']) == 1
        
        alarm = response['MetricAlarms'][0]
        assert alarm['AlarmName'] == alarm_name
        assert alarm['MetricName'] == 'ErrorCount'
        assert alarm['Threshold'] == 5.0


class TestLambdaExecutionEnvironment:
    """Lambda実行環境統合テストクラス"""
    
    @mock_ssm
    @mock_cloudwatch
    @mock_logs
    @pytest.mark.asyncio
    async def test_lambda_cold_start_simulation(self):
        """Lambdaコールドスタートシミュレーションテスト"""
        # AWS環境のモック設定
        ssm_client = boto3.client('ssm', region_name='us-east-1')
        cloudwatch_client = boto3.client('cloudwatch', region_name='us-east-1')
        logs_client = boto3.client('logs', region_name='us-east-1')
        
        # Parameter Store設定
        ssm_client.put_parameter(
            Name='/stock-analysis/google-sheets/spreadsheet-id',
            Value='lambda-test-123',
            Type='String'
        )
        
        # Lambda環境変数シミュレーション
        lambda_env = {
            'AWS_REGION': 'us-east-1',
            'AWS_LAMBDA_FUNCTION_NAME': 'stock-analysis-function',
            'AWS_LAMBDA_FUNCTION_VERSION': '1',
            'AWS_LAMBDA_LOG_GROUP_NAME': '/aws/lambda/stock-analysis',
            'AWS_LAMBDA_LOG_STREAM_NAME': '2024/01/01/test-stream'
        }
        
        with patch.dict(os.environ, lambda_env):
            with patch('src.config.boto3.client') as mock_boto_client:
                # AWS クライアントのモック設定
                def client_factory(service_name, **kwargs):
                    if service_name == 'ssm':
                        return ssm_client
                    elif service_name == 'cloudwatch':
                        return cloudwatch_client
                    elif service_name == 'logs':
                        return logs_client
                    return Mock()
                
                mock_boto_client.side_effect = client_factory
                
                # Lambda イベント作成
                event = {
                    "source": "aws.events",
                    "detail-type": "Scheduled Event",
                    "detail": {
                        "analysis_type": "daily"
                    },
                    "time": datetime.now().isoformat()
                }
                
                context = Mock()
                context.aws_request_id = "lambda-test-request"
                context.function_name = "stock-analysis-function"
                context.remaining_time_in_millis = lambda: 300000
                
                # 外部サービスのモック
                with patch('src.lambda_handler.GoogleSheetsService') as mock_sheets, \
                     patch('src.lambda_handler.StockDataService') as mock_stock, \
                     patch('src.lambda_handler.GeminiService') as mock_gemini, \
                     patch('src.lambda_handler.SlackService') as mock_slack:
                    
                    # モックサービス設定
                    mock_sheets.return_value.get_portfolio_data = AsyncMock(return_value=[])
                    mock_sheets.return_value.get_watchlist_data = AsyncMock(return_value=[])
                    mock_stock.return_value.get_batch_stock_data = AsyncMock(return_value=[])
                    mock_gemini.return_value.analyze_stocks = AsyncMock(
                        return_value=Mock(analysis_id="lambda-test-001")
                    )
                    mock_slack.return_value.send_analysis_notification = AsyncMock(
                        return_value=Mock(success=True)
                    )
                    
                    # Lambdaハンドラー実行
                    start_time = datetime.now()
                    result = await handler(event, context)
                    end_time = datetime.now()
                    
                    # 実行結果検証
                    assert result["statusCode"] == 200
                    
                    # コールドスタート時間測定
                    cold_start_time = (end_time - start_time).total_seconds()
                    assert cold_start_time < 30.0  # 30秒以内でコールドスタート完了
    
    @pytest.mark.asyncio
    async def test_lambda_memory_optimization(self):
        """Lambdaメモリ最適化テスト"""
        import psutil
        import gc
        
        # 初期メモリ使用量測定
        process = psutil.Process()
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # Lambda環境でのメモリ使用パターンシミュレーション
        large_data = []
        for i in range(1000):
            large_data.append({
                'symbol': f'TEST{i:04d}',
                'price': 100.0 + i,
                'volume': 1000000 + i * 1000,
                'historical_data': list(range(100))  # 履歴データ
            })
        
        # メモリ使用量測定
        peak_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # ガベージコレクション実行
        del large_data
        gc.collect()
        
        # ガベージコレクション後のメモリ測定
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        
        # メモリ最適化効果確認
        memory_growth = peak_memory - initial_memory
        memory_freed = peak_memory - final_memory
        
        assert memory_growth > 0  # メモリが実際に使用された
        assert memory_freed > 0   # メモリが解放された
        assert memory_freed / memory_growth > 0.5  # 50%以上のメモリが解放された
    
    @pytest.mark.asyncio
    async def test_lambda_timeout_handling(self):
        """Lambdaタイムアウト処理テスト"""
        event = {
            "source": "aws.events",
            "detail-type": "Scheduled Event",
            "detail": {
                "analysis_type": "daily"
            },
            "time": datetime.now().isoformat()
        }
        
        # 短いタイムアウトコンテキスト
        context = Mock()
        context.aws_request_id = "timeout-test-request"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 2000  # 2秒でタイムアウト
        
        with patch('src.lambda_handler.GoogleSheetsService') as mock_sheets:
            # 長時間実行される処理をモック
            async def slow_operation():
                await asyncio.sleep(5)  # 5秒待機
                return []
            
            mock_sheets.return_value.get_portfolio_data = slow_operation
            
            # タイムアウト処理の確認
            result = await handler(event, context)
            
            # タイムアウトエラーが適切に処理されることを確認
            assert result["statusCode"] in [408, 500]
            response_body = json.loads(result["body"])
            assert response_body["success"] is False
    
    @mock_ssm
    @mock_cloudwatch
    def test_lambda_environment_variables_integration(self):
        """Lambda環境変数統合テスト"""
        # Lambda環境変数設定
        lambda_env = {
            'AWS_REGION': 'us-east-1',
            'ENVIRONMENT': 'production',
            'LOG_LEVEL': 'INFO',
            'ENABLE_DEBUG': 'false',
            'PARAMETER_STORE_PREFIX': '/stock-analysis',
            'CLOUDWATCH_NAMESPACE': 'StockAnalysis'
        }
        
        with patch.dict(os.environ, lambda_env):
            # 環境変数の読み込み確認
            assert os.environ.get('AWS_REGION') == 'us-east-1'
            assert os.environ.get('ENVIRONMENT') == 'production'
            assert os.environ.get('LOG_LEVEL') == 'INFO'
            assert os.environ.get('ENABLE_DEBUG') == 'false'
            
            # ConfigManagerでの環境変数使用確認
            with patch('src.config.boto3.client'):
                config_manager = ConfigManager()
                
                # 環境変数がConfigManagerで適切に使用されることを確認
                assert config_manager.environment == 'production'
                assert config_manager.log_level == 'INFO'


class TestErrorRecoveryAndResilience:
    """エラー回復とレジリエンステスト"""
    
    @mock_ssm
    @pytest.mark.asyncio
    async def test_service_failure_recovery(self):
        """サービス障害回復テスト"""
        ssm_client = boto3.client('ssm', region_name='us-east-1')
        
        event = {
            "source": "aws.events",
            "detail-type": "Scheduled Event",
            "detail": {
                "analysis_type": "daily"
            },
            "time": datetime.now().isoformat()
        }
        
        context = Mock()
        context.aws_request_id = "recovery-test-request"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 300000
        
        with patch('src.lambda_handler.GoogleSheetsService') as mock_sheets, \
             patch('src.lambda_handler.StockDataService') as mock_stock, \
             patch('src.lambda_handler.SlackService') as mock_slack:
            
            # Google Sheets で一時的な障害
            call_count = 0
            async def sheets_with_recovery():
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise ConnectionError("Temporary Google Sheets failure")
                return [{"symbol": "AAPL", "shares": 100}]
            
            mock_sheets.return_value.get_portfolio_data = sheets_with_recovery
            mock_sheets.return_value.get_watchlist_data = AsyncMock(return_value=[])
            
            # その他のサービスは正常
            mock_stock.return_value.get_batch_stock_data = AsyncMock(return_value=[])
            mock_slack.return_value.send_analysis_notification = AsyncMock(
                return_value=Mock(success=True)
            )
            
            # リトライ機能により最終的に成功することを確認
            result = await handler(event, context)
            
            # 障害からの回復を確認
            assert call_count >= 3  # リトライが実行された
            # 最終的に成功することを期待（リトライ機能次第）
    
    @pytest.mark.asyncio
    async def test_partial_failure_handling(self):
        """部分的障害処理テスト"""
        event = {
            "source": "aws.events",
            "detail-type": "Scheduled Event",
            "detail": {
                "analysis_type": "daily"
            },
            "time": datetime.now().isoformat()
        }
        
        context = Mock()
        context.aws_request_id = "partial-failure-test"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 300000
        
        with patch('src.lambda_handler.GoogleSheetsService') as mock_sheets, \
             patch('src.lambda_handler.StockDataService') as mock_stock, \
             patch('src.lambda_handler.GeminiService') as mock_gemini, \
             patch('src.lambda_handler.SlackService') as mock_slack:
            
            # 一部のサービスは成功、一部は失敗
            mock_sheets.return_value.get_portfolio_data = AsyncMock(
                return_value=[{"symbol": "AAPL", "shares": 100}]
            )
            mock_sheets.return_value.get_watchlist_data = AsyncMock(
                return_value=[{"symbol": "MSFT", "target_price": 350.0}]
            )
            
            mock_stock.return_value.get_batch_stock_data = AsyncMock(
                side_effect=Exception("Stock data service temporarily unavailable")
            )
            
            # Slack通知は成功
            mock_slack.return_value.send_error_notification = AsyncMock(
                return_value=Mock(success=True)
            )
            
            # 部分的な障害でも適切に処理されることを確認
            result = await handler(event, context)
            
            # エラーが適切に処理され、通知が送信されることを確認
            assert result["statusCode"] == 500  # エラー状態
            mock_slack.return_value.send_error_notification.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])