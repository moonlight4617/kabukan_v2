# -*- coding: utf-8 -*-
"""
グローバルテスト設定とフィクスチャ
"""

import pytest
import asyncio
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
from typing import Dict, Any, Generator

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from tests.config.test_settings import TestConfig, load_test_config_from_env
from tests.mocks.mock_apis import MockAPIFactory
from tests.fixtures.test_data import TestDataFactory, TestDataSet


# pytest設定
def pytest_configure(config):
    """pytest設定"""
    # カスタムマーカーを登録
    markers = [
        "unit: Unit tests",
        "integration: Integration tests", 
        "performance: Performance tests",
        "slow: Slow running tests (> 5 seconds)",
        "external_api: Tests that require external API access",
        "aws: Tests that require AWS services",
        "google_sheets: Tests that require Google Sheets API",
        "slack: Tests that require Slack API",
        "gemini: Tests that require Gemini AI API",
        "yahoo_finance: Tests that require Yahoo Finance API",
        "smoke: Smoke tests (basic functionality)",
        "regression: Regression tests",
        "security: Security-related tests"
    ]
    
    for marker in markers:
        config.addinivalue_line("markers", marker)


def pytest_collection_modifyitems(config, items):
    """テスト収集時の修正"""
    # 統合テストマーカーを自動追加
    for item in items:
        # ファイルパスベースでマーカーを自動追加
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "unit" in str(item.fspath):
            item.add_marker(pytest.mark.unit)
        elif "performance" in str(item.fspath):
            item.add_marker(pytest.mark.performance)
        
        # 実行時間ベースでslowマーカーを追加
        if hasattr(item, "get_closest_marker"):
            if item.get_closest_marker("slow") is None:
                # テスト名に"slow"が含まれている場合は自動でslowマーカーを追加
                if "slow" in item.name.lower():
                    item.add_marker(pytest.mark.slow)


# セッションスコープのフィクスチャ
@pytest.fixture(scope="session")
def event_loop():
    """セッションスコープのイベントループ"""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    yield loop
    
    # クリーンアップ
    try:
        loop.close()
    except Exception:
        pass


@pytest.fixture(scope="session")
def test_config() -> TestConfig:
    """テスト設定（セッションスコープ）"""
    return load_test_config_from_env()


@pytest.fixture(scope="session") 
def mock_apis(test_config) -> Dict[str, Any]:
    """モックAPI（セッションスコープ）"""
    return MockAPIFactory.create_all_mocks(test_config.config)


# 関数スコープのフィクスチャ
@pytest.fixture
def clean_environment():
    """クリーンな環境変数（各テスト前にリセット）"""
    # テスト前の環境変数を保存
    original_env = os.environ.copy()
    
    # テスト用環境変数を設定
    test_env = {
        "ENVIRONMENT": "test",
        "LOG_LEVEL": "DEBUG",
        "AWS_DEFAULT_REGION": "us-east-1",
        "AWS_ACCESS_KEY_ID": "test-access-key",
        "AWS_SECRET_ACCESS_KEY": "test-secret-key",
        "DISABLE_MOCKS": "false"
    }
    
    os.environ.update(test_env)
    
    yield
    
    # テスト後に環境変数を復元
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def mock_aws_services():
    """AWS サービスのモック"""
    with patch('boto3.client') as mock_client, \
         patch('boto3.resource') as mock_resource:
        
        # Parameter Store モック
        mock_ssm = Mock()
        mock_ssm.get_parameter.return_value = {
            'Parameter': {'Value': 'test-value'}
        }
        mock_ssm.get_parameters_by_path.return_value = {
            'Parameters': [
                {'Name': '/test/param1', 'Value': 'value1'},
                {'Name': '/test/param2', 'Value': 'value2'}
            ]
        }
        
        # CloudWatch モック
        mock_cloudwatch = Mock()
        mock_cloudwatch.put_metric_data.return_value = {}
        
        # Lambda モック
        mock_lambda = Mock()
        mock_lambda.invoke.return_value = {
            'StatusCode': 200,
            'Payload': Mock()
        }
        
        # サービス別にモックを返す
        def get_mock_client(service_name, **kwargs):
            mocks = {
                'ssm': mock_ssm,
                'cloudwatch': mock_cloudwatch,
                'lambda': mock_lambda
            }
            return mocks.get(service_name, Mock())
        
        mock_client.side_effect = get_mock_client
        mock_resource.return_value = Mock()
        
        yield {
            'ssm': mock_ssm,
            'cloudwatch': mock_cloudwatch,
            'lambda': mock_lambda
        }


@pytest.fixture
def lambda_context():
    """Lambda コンテキストのモック"""
    context = Mock()
    context.aws_request_id = "test-request-id"
    context.function_name = "stock-analysis-function"
    context.function_version = "1"
    context.invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:stock-analysis-function"
    context.memory_limit_in_mb = 256
    context.remaining_time_in_millis = lambda: 300000  # 5分
    context.log_group_name = "/aws/lambda/stock-analysis"
    context.log_stream_name = f"2024/01/01/[1]{context.aws_request_id}"
    return context


@pytest.fixture
def sample_events():
    """サンプルイベントデータ"""
    return {
        "daily": {
            "version": "0",
            "id": "test-daily-event",
            "detail-type": "Scheduled Event",
            "source": "aws.events",
            "account": "123456789012",
            "time": datetime.now().isoformat(),
            "region": "us-east-1",
            "detail": {
                "analysis_type": "daily",
                "triggered_by": "eventbridge"
            }
        },
        "weekly": {
            "version": "0", 
            "id": "test-weekly-event",
            "detail-type": "Scheduled Event",
            "source": "aws.events",
            "account": "123456789012",
            "time": datetime.now().isoformat(),
            "region": "us-east-1",
            "detail": {
                "analysis_type": "weekly",
                "triggered_by": "eventbridge"
            }
        },
        "monthly": {
            "version": "0",
            "id": "test-monthly-event", 
            "detail-type": "Scheduled Event",
            "source": "aws.events",
            "account": "123456789012",
            "time": datetime.now().isoformat(),
            "region": "us-east-1",
            "detail": {
                "analysis_type": "monthly",
                "triggered_by": "eventbridge"
            }
        }
    }


# テストデータフィクスチャ
@pytest.fixture
def standard_test_data() -> TestDataSet:
    """標準テストデータセット"""
    return TestDataFactory.get_dataset("standard")


@pytest.fixture
def large_portfolio_test_data() -> TestDataSet:
    """大規模ポートフォリオテストデータセット"""
    return TestDataFactory.get_dataset("large_portfolio")


@pytest.fixture
def volatile_market_test_data() -> TestDataSet:
    """ボラティル市場テストデータセット"""
    return TestDataFactory.get_dataset("volatile_market")


@pytest.fixture
def error_scenario_test_data() -> TestDataSet:
    """エラーシナリオテストデータセット"""
    return TestDataFactory.get_dataset("error_scenario")


# パフォーマンステスト用フィクスチャ
@pytest.fixture
def performance_timer():
    """パフォーマンス測定用タイマー"""
    times = {}
    
    def start_timer(name: str):
        times[name] = {"start": datetime.now()}
    
    def end_timer(name: str) -> float:
        if name in times and "start" in times[name]:
            end_time = datetime.now()
            duration = (end_time - times[name]["start"]).total_seconds()
            times[name]["end"] = end_time
            times[name]["duration"] = duration
            return duration
        return 0.0
    
    def get_times() -> Dict[str, Any]:
        return times.copy()
    
    timer = Mock()
    timer.start = start_timer
    timer.end = end_timer
    timer.get_times = get_times
    
    return timer


# デバッグ用フィクスチャ
@pytest.fixture
def debug_mode():
    """デバッグモード設定"""
    original_debug = os.environ.get("TEST_DEBUG", "false")
    os.environ["TEST_DEBUG"] = "true"
    
    yield True
    
    os.environ["TEST_DEBUG"] = original_debug


# テスト後のクリーンアップ
@pytest.fixture(autouse=True)
def cleanup_after_test(mock_apis):
    """各テスト後の自動クリーンアップ"""
    yield
    
    # モックAPIの履歴をクリア
    try:
        if "slack" in mock_apis:
            mock_apis["slack"].clear_message_history()
        if "cloudwatch" in mock_apis:
            mock_apis["cloudwatch"].clear_logs()
    except Exception as e:
        # クリーンアップエラーは無視（テスト失敗を防ぐため）
        print(f"Cleanup warning: {e}")


# カスタムアサーション関数
def assert_stock_data_valid(stock_data):
    """株式データの妥当性をアサート"""
    assert stock_data.symbol, "Symbol should not be empty"
    assert stock_data.current_price > 0, "Current price should be positive"
    assert stock_data.previous_close > 0, "Previous close should be positive"
    assert stock_data.volume >= 0, "Volume should be non-negative"
    assert isinstance(stock_data.timestamp, datetime), "Timestamp should be datetime"


def assert_analysis_result_valid(analysis_result):
    """分析結果の妥当性をアサート"""
    assert analysis_result.analysis_id, "Analysis ID should not be empty"
    assert analysis_result.analysis_type in ["daily", "weekly", "monthly"], "Invalid analysis type"
    assert analysis_result.portfolio_summary, "Portfolio summary should not be empty"
    assert analysis_result.market_sentiment in ["POSITIVE", "NEGATIVE", "NEUTRAL"], "Invalid market sentiment"
    assert analysis_result.risk_assessment in ["LOW", "MEDIUM", "HIGH"], "Invalid risk assessment"


# カスタムマーカー用のskip条件
def pytest_runtest_setup(item):
    """テスト実行前のセットアップ"""
    # 外部APIテストのスキップ判定
    if item.get_closest_marker("external_api"):
        if os.environ.get("DISABLE_EXTERNAL_API_TESTS", "false").lower() == "true":
            pytest.skip("External API tests are disabled")
    
    # AWS依存テストのスキップ判定
    if item.get_closest_marker("aws"):
        if os.environ.get("DISABLE_AWS_TESTS", "false").lower() == "true":
            pytest.skip("AWS tests are disabled")
    
    # スローテストのスキップ判定
    if item.get_closest_marker("slow"):
        if os.environ.get("SKIP_SLOW_TESTS", "false").lower() == "true":
            pytest.skip("Slow tests are disabled")


# テストレポート用の情報収集
@pytest.fixture(scope="session", autouse=True)
def test_session_info():
    """テストセッション情報の収集"""
    session_info = {
        "start_time": datetime.now(),
        "python_version": sys.version,
        "pytest_version": pytest.__version__,
        "test_environment": os.environ.get("ENVIRONMENT", "unknown"),
        "test_config": {}
    }
    
    yield session_info
    
    session_info["end_time"] = datetime.now()
    session_info["duration"] = (session_info["end_time"] - session_info["start_time"]).total_seconds()
    
    # テストセッション情報をファイルに保存（CI/CD用）
    if os.environ.get("CI"):
        import json
        report_path = Path("tests/reports/session_info.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)
        
        # datetime オブジェクトを文字列に変換
        serializable_info = session_info.copy()
        for key, value in serializable_info.items():
            if isinstance(value, datetime):
                serializable_info[key] = value.isoformat()
        
        with open(report_path, 'w') as f:
            json.dump(serializable_info, f, indent=2)