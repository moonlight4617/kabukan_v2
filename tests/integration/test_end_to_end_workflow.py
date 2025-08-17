# -*- coding: utf-8 -*-
"""
エンドツーエンドワークフロー統合テスト
システム全体の処理フローを検証
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import json
import os

from src.handlers.lambda_handler import handler
from src.models.data_models import StockData, Portfolio, WatchlistStock
from src.models.analysis_models import AnalysisResult, Recommendation, TechnicalIndicators
from src.services.google_sheets_service import GoogleSheetsService
from src.services.stock_data_service import StockDataService
from src.services.gemini_service import GeminiService
from src.services.slack_service import SlackService
from src.services.error_handler import ErrorHandler


class TestEndToEndWorkflow:
    """エンドツーエンドワークフロー統合テストクラス"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.test_portfolio_data = [
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
            }
        ]
        
        self.test_watchlist_data = [
            {
                "symbol": "MSFT",
                "target_price": 350.0,
                "region": "US",
                "sector": "Technology",
                "priority": "high"
            },
            {
                "symbol": "TSLA",
                "target_price": 200.0,
                "region": "US", 
                "sector": "Automotive",
                "priority": "medium"
            }
        ]
        
        self.test_stock_data = {
            "AAPL": StockData(
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
            "GOOGL": StockData(
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
            "MSFT": StockData(
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
            ),
            "TSLA": StockData(
                symbol="TSLA",
                current_price=220.00,
                previous_close=215.00,
                open_price=218.00,
                high_price=225.00,
                low_price=216.00,
                volume=80000000,
                market_cap=700000000000,
                pe_ratio=65.5,
                timestamp=datetime.now()
            )
        }
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_daily_analysis_complete_workflow(self):
        """日次分析の完全ワークフローテスト"""
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
        context.aws_request_id = "test-request-id"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 300000
        
        # モックサービスのセットアップ
        with patch('src.handlers.lambda_handler.GoogleSheetsService') as mock_sheets_service, \
             patch('src.handlers.lambda_handler.StockDataService') as mock_stock_service, \
             patch('src.handlers.lambda_handler.GeminiService') as mock_gemini_service, \
             patch('src.handlers.lambda_handler.SlackService') as mock_slack_service:
            
            # Google Sheets サービスモック
            mock_sheets_instance = Mock()
            mock_sheets_service.return_value = mock_sheets_instance
            mock_sheets_instance.get_portfolio_data = AsyncMock(return_value=self.test_portfolio_data)
            mock_sheets_instance.get_watchlist_data = AsyncMock(return_value=self.test_watchlist_data)
            
            # 株式データサービスモック
            mock_stock_instance = Mock()
            mock_stock_service.return_value = mock_stock_instance
            mock_stock_instance.get_batch_stock_data = AsyncMock(
                return_value=list(self.test_stock_data.values())
            )
            
            # Gemini サービスモック
            mock_gemini_instance = Mock()
            mock_gemini_service.return_value = mock_gemini_instance
            mock_analysis_result = AnalysisResult(
                analysis_id="test-analysis-001",
                timestamp=datetime.now(),
                analysis_type="daily",
                portfolio_summary="ポートフォリオは全体的に良好なパフォーマンスを示しています。",
                recommendations=[
                    Recommendation(
                        symbol="AAPL",
                        action="HOLD",
                        confidence=0.85,
                        reasoning="技術的指標が安定しており、継続保有を推奨します。",
                        target_price=180.0
                    ),
                    Recommendation(
                        symbol="MSFT",
                        action="BUY",
                        confidence=0.90,
                        reasoning="強い業績と成長見通しから購入を推奨します。",
                        target_price=400.0
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
            mock_gemini_instance.analyze_stocks = AsyncMock(return_value=mock_analysis_result)
            
            # Slack サービスモック
            mock_slack_instance = Mock()
            mock_slack_service.return_value = mock_slack_instance
            mock_slack_instance.send_analysis_notification = AsyncMock(
                return_value=Mock(success=True, message_id="test-msg-123")
            )
            
            # ワークフロー実行
            result = await handler(event, context)
            
            # 結果検証
            assert result["statusCode"] == 200
            response_body = json.loads(result["body"])
            assert response_body["success"] is True
            assert "analysis_id" in response_body
            assert response_body["analysis_type"] == "daily"
            
            # サービス呼び出し検証
            mock_sheets_instance.get_portfolio_data.assert_called_once()
            mock_sheets_instance.get_watchlist_data.assert_called_once()
            mock_stock_instance.get_batch_stock_data.assert_called_once()
            mock_gemini_instance.analyze_stocks.assert_called_once()
            mock_slack_instance.send_analysis_notification.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_weekly_analysis_complete_workflow(self):
        """週次分析の完全ワークフローテスト"""
        event = {
            "source": "aws.events",
            "detail-type": "Scheduled Event", 
            "detail": {
                "analysis_type": "weekly"
            },
            "time": datetime.now().isoformat()
        }
        
        context = Mock()
        context.aws_request_id = "test-weekly-request"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 300000
        
        with patch('src.handlers.lambda_handler.GoogleSheetsService') as mock_sheets_service, \
             patch('src.handlers.lambda_handler.StockDataService') as mock_stock_service, \
             patch('src.handlers.lambda_handler.GeminiService') as mock_gemini_service, \
             patch('src.handlers.lambda_handler.SlackService') as mock_slack_service:
            
            # モックサービスのセットアップ
            mock_sheets_instance = Mock()
            mock_sheets_service.return_value = mock_sheets_instance
            mock_sheets_instance.get_portfolio_data = AsyncMock(return_value=self.test_portfolio_data)
            
            mock_stock_instance = Mock()
            mock_stock_service.return_value = mock_stock_instance
            mock_stock_instance.get_batch_stock_data = AsyncMock(
                return_value=list(self.test_stock_data.values())
            )
            mock_stock_instance.get_historical_data = AsyncMock(
                return_value=[
                    Mock(price=170.0, timestamp=datetime.now() - timedelta(days=7)),
                    Mock(price=172.0, timestamp=datetime.now() - timedelta(days=6)),
                    Mock(price=175.5, timestamp=datetime.now())
                ]
            )
            
            mock_gemini_instance = Mock() 
            mock_gemini_service.return_value = mock_gemini_instance
            mock_weekly_analysis = AnalysisResult(
                analysis_id="test-weekly-001",
                timestamp=datetime.now(),
                analysis_type="weekly",
                portfolio_summary="週次パフォーマンス: +3.2%の上昇を記録しました。",
                recommendations=[
                    Recommendation(
                        symbol="AAPL",
                        action="HOLD",
                        confidence=0.80,
                        reasoning="週次トレンドは上昇傾向を維持しています。",
                        target_price=180.0
                    )
                ],
                market_sentiment="POSITIVE",
                risk_assessment="LOW"
            )
            mock_gemini_instance.analyze_weekly_performance = AsyncMock(
                return_value=mock_weekly_analysis
            )
            
            mock_slack_instance = Mock()
            mock_slack_service.return_value = mock_slack_instance
            mock_slack_instance.send_analysis_notification = AsyncMock(
                return_value=Mock(success=True, message_id="test-weekly-msg")
            )
            
            # ワークフロー実行
            result = await handler(event, context)
            
            # 結果検証
            assert result["statusCode"] == 200
            response_body = json.loads(result["body"])
            assert response_body["success"] is True
            assert response_body["analysis_type"] == "weekly"
            
            # 週次固有の処理が呼ばれたことを確認
            mock_stock_instance.get_historical_data.assert_called()
            mock_gemini_instance.analyze_weekly_performance.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_monthly_analysis_complete_workflow(self):
        """月次分析の完全ワークフローテスト"""
        event = {
            "source": "aws.events",
            "detail-type": "Scheduled Event",
            "detail": {
                "analysis_type": "monthly"
            },
            "time": datetime.now().isoformat()
        }
        
        context = Mock()
        context.aws_request_id = "test-monthly-request"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 300000
        
        with patch('src.handlers.lambda_handler.GoogleSheetsService') as mock_sheets_service, \
             patch('src.handlers.lambda_handler.StockDataService') as mock_stock_service, \
             patch('src.handlers.lambda_handler.GeminiService') as mock_gemini_service, \
             patch('src.handlers.lambda_handler.SlackService') as mock_slack_service:
            
            # モックサービスのセットアップ
            mock_sheets_instance = Mock()
            mock_sheets_service.return_value = mock_sheets_instance
            mock_sheets_instance.get_portfolio_data = AsyncMock(return_value=self.test_portfolio_data)
            
            mock_stock_instance = Mock()
            mock_stock_service.return_value = mock_stock_instance
            mock_stock_instance.get_batch_stock_data = AsyncMock(
                return_value=list(self.test_stock_data.values())
            )
            
            # 月次データ（30日分の履歴）
            historical_data = []
            for i in range(30):
                historical_data.append(
                    Mock(
                        price=170.0 + (i * 0.2),
                        timestamp=datetime.now() - timedelta(days=30-i)
                    )
                )
            mock_stock_instance.get_historical_data = AsyncMock(return_value=historical_data)
            
            mock_gemini_instance = Mock()
            mock_gemini_service.return_value = mock_gemini_instance
            mock_monthly_analysis = AnalysisResult(
                analysis_id="test-monthly-001",
                timestamp=datetime.now(),
                analysis_type="monthly",
                portfolio_summary="月次パフォーマンス: +5.8%の成長。セクター別では技術株が好調。",
                recommendations=[
                    Recommendation(
                        symbol="Portfolio",
                        action="REBALANCE",
                        confidence=0.75,
                        reasoning="技術株の比重が高すぎるため、分散投資を検討してください。",
                        target_price=None
                    )
                ],
                market_sentiment="POSITIVE",
                risk_assessment="MEDIUM"
            )
            mock_gemini_instance.analyze_monthly_performance = AsyncMock(
                return_value=mock_monthly_analysis
            )
            
            mock_slack_instance = Mock()
            mock_slack_service.return_value = mock_slack_instance
            mock_slack_instance.send_analysis_notification = AsyncMock(
                return_value=Mock(success=True, message_id="test-monthly-msg")
            )
            
            # ワークフロー実行
            result = await handler(event, context)
            
            # 結果検証
            assert result["statusCode"] == 200
            response_body = json.loads(result["body"])
            assert response_body["success"] is True
            assert response_body["analysis_type"] == "monthly"
            
            # 月次固有の処理が呼ばれたことを確認
            mock_gemini_instance.analyze_monthly_performance.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_error_handling_workflow(self):
        """エラーハンドリングワークフローテスト"""
        event = {
            "source": "aws.events",
            "detail-type": "Scheduled Event",
            "detail": {
                "analysis_type": "daily"
            },
            "time": datetime.now().isoformat()
        }
        
        context = Mock()
        context.aws_request_id = "test-error-request"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 300000
        
        # Google Sheets サービスでエラーが発生するシナリオ
        with patch('src.handlers.lambda_handler.GoogleSheetsService') as mock_sheets_service, \
             patch('src.handlers.lambda_handler.SlackService') as mock_slack_service:
            
            mock_sheets_instance = Mock()
            mock_sheets_service.return_value = mock_sheets_instance
            # Google Sheets からのデータ取得でエラーが発生
            mock_sheets_instance.get_portfolio_data = AsyncMock(
                side_effect=ConnectionError("Google Sheets API connection failed")
            )
            
            mock_slack_instance = Mock()
            mock_slack_service.return_value = mock_slack_instance
            mock_slack_instance.send_error_notification = AsyncMock(
                return_value=Mock(success=True, message_id="error-notification")
            )
            
            # ワークフロー実行（エラーが予想される）
            result = await handler(event, context)
            
            # エラーハンドリングの検証
            assert result["statusCode"] == 500
            response_body = json.loads(result["body"])
            assert response_body["success"] is False
            assert "error" in response_body
            
            # エラー通知が送信されたことを確認
            mock_slack_instance.send_error_notification.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_invalid_event_handling(self):
        """無効なイベント処理テスト"""
        # 不正なイベント形式
        invalid_event = {
            "source": "invalid.source",
            "detail-type": "Invalid Event",
            "detail": {}
        }
        
        context = Mock()
        context.aws_request_id = "test-invalid-request"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 300000
        
        result = await handler(invalid_event, context)
        
        # 無効なイベントの適切な処理を確認
        assert result["statusCode"] == 400
        response_body = json.loads(result["body"])
        assert response_body["success"] is False
        assert "Invalid event" in response_body["error"] or "analysis_type" in response_body["error"]
    
    @pytest.mark.asyncio 
    @pytest.mark.integration
    async def test_timeout_handling(self):
        """タイムアウト処理テスト"""
        event = {
            "source": "aws.events",
            "detail-type": "Scheduled Event",
            "detail": {
                "analysis_type": "daily"
            },
            "time": datetime.now().isoformat()
        }
        
        context = Mock()
        context.aws_request_id = "test-timeout-request"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 1000  # 1秒でタイムアウト
        
        with patch('src.handlers.lambda_handler.GoogleSheetsService') as mock_sheets_service:
            mock_sheets_instance = Mock()
            mock_sheets_service.return_value = mock_sheets_instance
            # 長時間かかる処理をシミュレート
            async def slow_operation():
                await asyncio.sleep(2)  # 2秒待機
                return self.test_portfolio_data
            
            mock_sheets_instance.get_portfolio_data = slow_operation
            
            # タイムアウトが発生することを確認
            result = await handler(event, context)
            
            # タイムアウトエラーの適切な処理を確認
            assert result["statusCode"] in [408, 500]  # タイムアウトまたはサーバーエラー
            response_body = json.loads(result["body"])
            assert response_body["success"] is False
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_performance_metrics_collection(self):
        """パフォーマンスメトリクス収集テスト"""
        event = {
            "source": "aws.events",
            "detail-type": "Scheduled Event",
            "detail": {
                "analysis_type": "daily"
            },
            "time": datetime.now().isoformat()
        }
        
        context = Mock()
        context.aws_request_id = "test-metrics-request"
        context.function_name = "stock-analysis-function"
        context.remaining_time_in_millis = lambda: 300000
        
        with patch('src.handlers.lambda_handler.GoogleSheetsService') as mock_sheets_service, \
             patch('src.handlers.lambda_handler.StockDataService') as mock_stock_service, \
             patch('src.handlers.lambda_handler.GeminiService') as mock_gemini_service, \
             patch('src.handlers.lambda_handler.SlackService') as mock_slack_service:
            
            # 高速なモックサービスのセットアップ
            mock_sheets_instance = Mock()
            mock_sheets_service.return_value = mock_sheets_instance
            mock_sheets_instance.get_portfolio_data = AsyncMock(return_value=self.test_portfolio_data)
            mock_sheets_instance.get_watchlist_data = AsyncMock(return_value=self.test_watchlist_data)
            
            mock_stock_instance = Mock()
            mock_stock_service.return_value = mock_stock_instance
            mock_stock_instance.get_batch_stock_data = AsyncMock(
                return_value=list(self.test_stock_data.values())
            )
            
            mock_gemini_instance = Mock()
            mock_gemini_service.return_value = mock_gemini_instance
            mock_analysis_result = AnalysisResult(
                analysis_id="test-metrics-001",
                timestamp=datetime.now(),
                analysis_type="daily",
                portfolio_summary="テストポートフォリオ分析",
                recommendations=[],
                market_sentiment="NEUTRAL",
                risk_assessment="LOW"
            )
            mock_gemini_instance.analyze_stocks = AsyncMock(return_value=mock_analysis_result)
            
            mock_slack_instance = Mock()
            mock_slack_service.return_value = mock_slack_instance
            mock_slack_instance.send_analysis_notification = AsyncMock(
                return_value=Mock(success=True)
            )
            
            # 実行時間測定
            start_time = datetime.now()
            result = await handler(event, context)
            end_time = datetime.now()
            
            execution_time = (end_time - start_time).total_seconds()
            
            # パフォーマンス検証
            assert result["statusCode"] == 200
            assert execution_time < 30.0  # 30秒以内で完了することを確認
            
            response_body = json.loads(result["body"])
            # メトリクス情報が含まれていることを確認
            assert "execution_time" in response_body or "metrics" in response_body


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])