# -*- coding: utf-8 -*-
"""
統合テスト用設定とフィクスチャ
"""

import pytest
import asyncio
import os
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

from src.models.data_models import StockData, GoogleSheetsConfig
from src.models.analysis_models import AnalysisResult, Recommendation, TechnicalIndicators


@pytest.fixture(scope="session")
def event_loop():
    """セッションスコープのイベントループ"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_aws_environment():
    """AWS環境変数のモック"""
    aws_env = {
        'AWS_REGION': 'us-east-1',
        'AWS_LAMBDA_FUNCTION_NAME': 'stock-analysis-function',
        'AWS_LAMBDA_FUNCTION_VERSION': '1',
        'AWS_LAMBDA_LOG_GROUP_NAME': '/aws/lambda/stock-analysis',
        'AWS_LAMBDA_LOG_STREAM_NAME': '2024/01/01/test-stream',
        'ENVIRONMENT': 'test',
        'LOG_LEVEL': 'DEBUG'
    }
    
    with patch.dict(os.environ, aws_env):
        yield aws_env


@pytest.fixture
def sample_stock_data():
    """サンプル株式データ"""
    return [
        StockData(
            symbol="AAPL",
            current_price=175.50,
            previous_close=174.00,
            open_price=175.00,
            high_price=176.00,
            low_price=174.50,
            volume=50000000,
            market_cap=2750000000000,
            pe_ratio=28.5,
            timestamp=datetime.now()
        ),
        StockData(
            symbol="GOOGL",
            current_price=2950.00,
            previous_close=2930.00,
            open_price=2940.00,
            high_price=2960.00,
            low_price=2920.00,
            volume=1500000,
            market_cap=1900000000000,
            pe_ratio=25.2,
            timestamp=datetime.now()
        ),
        StockData(
            symbol="MSFT",
            current_price=380.00,
            previous_close=378.50,
            open_price=379.00,
            high_price=382.00,
            low_price=377.00,
            volume=30000000,
            market_cap=2800000000000,
            pe_ratio=32.1,
            timestamp=datetime.now()
        )
    ]


@pytest.fixture
def sample_portfolio_data():
    """サンプルポートフォリオデータ"""
    return [
        {
            "symbol": "AAPL",
            "shares": 100,
            "purchase_price": 150.0,
            "purchase_date": "2024-01-01",
            "region": "US",
            "sector": "Technology"
        },
        {
            "symbol": "GOOGL",
            "shares": 50,
            "purchase_price": 2800.0,
            "purchase_date": "2024-01-15",
            "region": "US",
            "sector": "Technology"
        },
        {
            "symbol": "MSFT",
            "shares": 75,
            "purchase_price": 300.0,
            "purchase_date": "2024-02-01",
            "region": "US",
            "sector": "Technology"
        }
    ]


@pytest.fixture
def sample_watchlist_data():
    """サンプルウォッチリストデータ"""
    return [
        {
            "symbol": "TSLA",
            "target_price": 220.0,
            "region": "US",
            "sector": "Automotive",
            "priority": "high"
        },
        {
            "symbol": "AMD",
            "target_price": 120.0,
            "region": "US",
            "sector": "Technology",
            "priority": "medium"
        },
        {
            "symbol": "NVDA",
            "target_price": 800.0,
            "region": "US",
            "sector": "Technology",
            "priority": "high"
        }
    ]


@pytest.fixture
def sample_analysis_result():
    """サンプル分析結果"""
    return AnalysisResult(
        analysis_id="test-analysis-001",
        timestamp=datetime.now(),
        analysis_type="daily",
        portfolio_summary="ポートフォリオは全体的に良好なパフォーマンスを示しています。技術株が市場をリードしており、継続的な成長が期待されます。",
        recommendations=[
            Recommendation(
                symbol="AAPL",
                action="HOLD",
                confidence=0.85,
                reasoning="技術的指標が安定しており、強固なファンダメンタルズを背景に継続保有を推奨します。",
                target_price=180.0
            ),
            Recommendation(
                symbol="GOOGL",
                action="BUY",
                confidence=0.90,
                reasoning="AI技術への投資拡大と広告事業の安定性から、追加購入の好機です。",
                target_price=3000.0
            ),
            Recommendation(
                symbol="TSLA",
                action="BUY",
                confidence=0.75,
                reasoning="電気自動車市場の成長と技術革新により、新規購入を推奨します。",
                target_price=250.0
            )
        ],
        technical_analysis=TechnicalIndicators(
            rsi=65.5,
            macd_signal="BULLISH",
            moving_average_20=172.5,
            moving_average_50=168.0,
            support_level=170.0,
            resistance_level=180.0
        ),
        market_sentiment="POSITIVE",
        risk_assessment="MEDIUM"
    )


@pytest.fixture
def google_sheets_config():
    """Google Sheets設定"""
    return GoogleSheetsConfig(
        spreadsheet_id="test-spreadsheet-123",
        credentials={
            "type": "service_account",
            "project_id": "test-project",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest-private-key\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        },
        portfolio_sheet_name="Portfolio",
        watchlist_sheet_name="Watchlist"
    )


@pytest.fixture
def slack_config():
    """Slack設定"""
    return {
        "webhook_url": "https://hooks.slack.com/services/test/webhook/url",
        "default_channel": "#stock-analysis",
        "error_channel": "#alerts",
        "username": "Stock Analysis Bot",
        "icon_emoji": ":chart_with_upwards_trend:"
    }


@pytest.fixture
def gemini_config():
    """Gemini設定"""
    return {
        "api_key": "test-gemini-api-key",
        "model_name": "gemini-pro",
        "temperature": 0.7,
        "max_tokens": 2048,
        "safety_settings": {
            "HARM_CATEGORY_HARASSMENT": "BLOCK_NONE",
            "HARM_CATEGORY_HATE_SPEECH": "BLOCK_NONE",
            "HARM_CATEGORY_SEXUALLY_EXPLICIT": "BLOCK_NONE",
            "HARM_CATEGORY_DANGEROUS_CONTENT": "BLOCK_NONE"
        }
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
    context.log_stream_name = "2024/01/01/test-stream"
    return context


@pytest.fixture
def daily_event():
    """日次分析イベント"""
    return {
        "version": "0",
        "id": "test-event-id",
        "detail-type": "Scheduled Event",
        "source": "aws.events",
        "account": "123456789012",
        "time": datetime.now().isoformat(),
        "region": "us-east-1",
        "detail": {
            "analysis_type": "daily",
            "triggered_by": "eventbridge"
        }
    }


@pytest.fixture
def weekly_event():
    """週次分析イベント"""
    return {
        "version": "0",
        "id": "test-weekly-event-id",
        "detail-type": "Scheduled Event",
        "source": "aws.events",
        "account": "123456789012",
        "time": datetime.now().isoformat(),
        "region": "us-east-1",
        "detail": {
            "analysis_type": "weekly",
            "triggered_by": "eventbridge"
        }
    }


@pytest.fixture
def monthly_event():
    """月次分析イベント"""
    return {
        "version": "0",
        "id": "test-monthly-event-id",
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


@pytest.fixture
def historical_price_data():
    """履歴価格データ"""
    base_date = datetime.now() - timedelta(days=30)
    historical_data = []
    
    for i in range(30):
        date = base_date + timedelta(days=i)
        price = 170.0 + (i * 0.2) + ((-1) ** i * 2)  # トレンドとノイズを追加
        volume = 45000000 + (i * 100000)
        
        historical_data.append({
            'Date': date,
            'Open': price - 1.0,
            'High': price + 2.0,
            'Low': price - 2.0,
            'Close': price,
            'Volume': volume
        })
    
    return historical_data


class TestDataGenerator:
    """テストデータ生成ヘルパークラス"""
    
    @staticmethod
    def generate_stock_data(symbol: str, base_price: float = 100.0) -> StockData:
        """株式データを生成"""
        return StockData(
            symbol=symbol,
            current_price=base_price,
            previous_close=base_price * 0.99,
            open_price=base_price * 0.995,
            high_price=base_price * 1.02,
            low_price=base_price * 0.98,
            volume=1000000,
            market_cap=int(base_price * 1000000000),
            pe_ratio=25.0,
            timestamp=datetime.now()
        )
    
    @staticmethod
    def generate_portfolio_entry(symbol: str, shares: int = 100, purchase_price: float = 100.0) -> dict:
        """ポートフォリオエントリを生成"""
        return {
            "symbol": symbol,
            "shares": shares,
            "purchase_price": purchase_price,
            "purchase_date": "2024-01-01",
            "region": "US",
            "sector": "Technology"
        }
    
    @staticmethod
    def generate_recommendation(symbol: str, action: str = "HOLD", confidence: float = 0.8) -> Recommendation:
        """推奨を生成"""
        return Recommendation(
            symbol=symbol,
            action=action,
            confidence=confidence,
            reasoning=f"{action} recommendation for {symbol} based on technical analysis.",
            target_price=150.0
        )


@pytest.fixture
def test_data_generator():
    """テストデータ生成ヘルパー"""
    return TestDataGenerator()


# 統合テスト用のマーカー設定
def pytest_configure(config):
    """pytest設定"""
    config.addinivalue_line("markers", "integration: 統合テストとしてマーク")
    config.addinivalue_line("markers", "slow: 実行時間が長いテストとしてマーク")
    config.addinivalue_line("markers", "external_api: 外部APIを使用するテストとしてマーク")


# テスト実行時のフィルタリング
def pytest_collection_modifyitems(config, items):
    """テスト収集時の修正"""
    # 統合テストマーカーを自動追加
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)