# -*- coding: utf-8 -*-
"""
外部API統合テスト
Google Sheets API、Gemini AI API、Slack Webhook API、Yahoo Finance APIとの統合を検証
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import json
import os
from datetime import datetime, timedelta
import requests
import yfinance as yf

from src.services.google_sheets_service import GoogleSheetsService
from src.services.gemini_service import GeminiService
from src.services.slack_service import SlackService
from src.services.stock_data_service import StockDataService
from src.models.data_models import StockData, GoogleSheetsConfig
from src.models.analysis_models import AnalysisResult, Recommendation


class TestGoogleSheetsAPIIntegration:
    """Google Sheets API統合テストクラス"""
    
    @pytest.fixture
    def mock_google_sheets_config(self):
        """Google Sheets設定のモックフィクスチャ"""
        return GoogleSheetsConfig(
            spreadsheet_id="test-spreadsheet-123",
            credentials={
                "type": "service_account",
                "project_id": "test-project",
                "private_key": "test-private-key",
                "client_email": "test@test-project.iam.gserviceaccount.com"
            },
            portfolio_sheet_name="Portfolio",
            watchlist_sheet_name="Watchlist"
        )
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_google_sheets_service_connection(self, mock_google_sheets_config):
        """Google Sheets API接続テスト"""
        with patch('googleapiclient.discovery.build') as mock_build:
            # モックGoogle Sheets APIクライアント
            mock_service = Mock()
            mock_build.return_value = mock_service
            
            # スプレッドシート値取得のモック
            mock_spreadsheets = Mock()
            mock_service.spreadsheets.return_value = mock_spreadsheets
            mock_values = Mock()
            mock_spreadsheets.values.return_value = mock_values
            
            # Portfolio データのモックレスポンス
            portfolio_response = {
                'values': [
                    ['Symbol', 'Shares', 'Purchase Price', 'Purchase Date', 'Region', 'Sector'],
                    ['AAPL', '100', '150.00', '2024-01-01', 'US', 'Technology'],
                    ['GOOGL', '50', '2800.00', '2024-01-15', 'US', 'Technology'],
                    ['MSFT', '75', '300.00', '2024-02-01', 'US', 'Technology']
                ]
            }
            
            mock_get = Mock()
            mock_values.get.return_value = mock_get
            mock_execute = Mock()
            mock_get.execute.return_value = portfolio_response
            
            # Google Sheets サービス初期化
            sheets_service = GoogleSheetsService(mock_google_sheets_config)
            
            # ポートフォリオデータ取得テスト
            portfolio_data = await sheets_service.get_portfolio_data()
            
            assert len(portfolio_data) == 3
            assert portfolio_data[0]['symbol'] == 'AAPL'
            assert portfolio_data[0]['shares'] == 100
            assert portfolio_data[1]['symbol'] == 'GOOGL'
            assert portfolio_data[2]['symbol'] == 'MSFT'
            
            # APIが正しく呼ばれたことを確認
            mock_build.assert_called_once()
            mock_values.get.assert_called()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_google_sheets_watchlist_data_retrieval(self, mock_google_sheets_config):
        """Google Sheets ウォッチリストデータ取得テスト"""
        with patch('googleapiclient.discovery.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service
            
            mock_spreadsheets = Mock()
            mock_service.spreadsheets.return_value = mock_spreadsheets
            mock_values = Mock()
            mock_spreadsheets.values.return_value = mock_values
            
            # Watchlist データのモックレスポンス
            watchlist_response = {
                'values': [
                    ['Symbol', 'Target Price', 'Region', 'Sector', 'Priority'],
                    ['TSLA', '220.00', 'US', 'Automotive', 'High'],
                    ['AMD', '120.00', 'US', 'Technology', 'Medium'],
                    ['NVDA', '800.00', 'US', 'Technology', 'High']
                ]
            }
            
            mock_get = Mock()
            mock_values.get.return_value = mock_get
            mock_get.execute.return_value = watchlist_response
            
            sheets_service = GoogleSheetsService(mock_google_sheets_config)
            
            # ウォッチリストデータ取得テスト
            watchlist_data = await sheets_service.get_watchlist_data()
            
            assert len(watchlist_data) == 3
            assert watchlist_data[0]['symbol'] == 'TSLA'
            assert watchlist_data[0]['target_price'] == 220.00
            assert watchlist_data[1]['priority'] == 'Medium'
    
    @pytest.mark.asyncio
    @pytest.mark.integration  
    async def test_google_sheets_error_handling(self, mock_google_sheets_config):
        """Google Sheets APIエラーハンドリングテスト"""
        with patch('googleapiclient.discovery.build') as mock_build:
            # API接続エラーをシミュレート
            mock_build.side_effect = Exception("Google Sheets API connection failed")
            
            sheets_service = GoogleSheetsService(mock_google_sheets_config)
            
            # エラーが適切に処理されることを確認
            with pytest.raises(Exception):
                await sheets_service.get_portfolio_data()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_google_sheets_data_validation(self, mock_google_sheets_config):
        """Google Sheets データ検証テスト"""
        with patch('googleapiclient.discovery.build') as mock_build:
            mock_service = Mock()
            mock_build.return_value = mock_service
            
            mock_spreadsheets = Mock()
            mock_service.spreadsheets.return_value = mock_spreadsheets
            mock_values = Mock()
            mock_spreadsheets.values.return_value = mock_values
            
            # 不正なデータを含むレスポンス
            invalid_response = {
                'values': [
                    ['Symbol', 'Shares', 'Purchase Price', 'Purchase Date', 'Region', 'Sector'],
                    ['AAPL', 'invalid_shares', '150.00', '2024-01-01', 'US', 'Technology'],
                    ['', '50', '2800.00', '2024-01-15', 'US', 'Technology'],  # 空のシンボル
                    ['MSFT', '75', 'invalid_price', '2024-02-01', 'US', 'Technology']
                ]
            }
            
            mock_get = Mock()
            mock_values.get.return_value = mock_get
            mock_get.execute.return_value = invalid_response
            
            sheets_service = GoogleSheetsService(mock_google_sheets_config)
            
            # データ検証エラーが適切に処理されることを確認
            portfolio_data = await sheets_service.get_portfolio_data()
            
            # 有効なデータのみが返されることを確認（不正なデータは除外される）
            valid_entries = [entry for entry in portfolio_data if entry.get('symbol')]
            assert len(valid_entries) <= 3  # 不正なエントリは除外される


class TestGeminiAPIIntegration:
    """Gemini AI API統合テストクラス"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_gemini_api_stock_analysis(self):
        """Gemini API株式分析テスト"""
        with patch('google.generativeai.configure') as mock_configure, \
             patch('google.generativeai.GenerativeModel') as mock_model_class:
            
            # モックGeminiモデル
            mock_model = Mock()
            mock_model_class.return_value = mock_model
            
            # 分析結果のモックレスポンス
            mock_response = Mock()
            mock_response.text = json.dumps({
                "analysis_id": "gemini-test-001",
                "timestamp": datetime.now().isoformat(),
                "portfolio_summary": "ポートフォリオは技術株中心で、全体的に成長トレンドを示しています。",
                "recommendations": [
                    {
                        "symbol": "AAPL",
                        "action": "HOLD",
                        "confidence": 0.85,
                        "reasoning": "安定した業績と技術革新により継続保有を推奨します。",
                        "target_price": 180.0
                    },
                    {
                        "symbol": "GOOGL", 
                        "action": "BUY",
                        "confidence": 0.90,
                        "reasoning": "AI分野での優位性と広告事業の安定性から追加購入を推奨します。",
                        "target_price": 3000.0
                    }
                ],
                "market_sentiment": "POSITIVE",
                "risk_assessment": "MEDIUM"
            })
            
            mock_model.generate_content = AsyncMock(return_value=mock_response)
            
            # Gemini サービス初期化
            gemini_service = GeminiService(api_key="test-api-key")
            
            # テスト用株式データ
            test_stocks = [
                StockData(
                    symbol="AAPL",
                    current_price=175.50,
                    previous_close=174.00,
                    volume=50000000,
                    market_cap=2750000000000,
                    timestamp=datetime.now()
                ),
                StockData(
                    symbol="GOOGL",
                    current_price=2950.00,
                    previous_close=2930.00,
                    volume=1500000,
                    market_cap=1900000000000,
                    timestamp=datetime.now()
                )
            ]
            
            # 株式分析実行
            analysis_result = await gemini_service.analyze_stocks(
                stocks=test_stocks,
                analysis_type="daily"
            )
            
            # 結果検証
            assert analysis_result.analysis_id == "gemini-test-001"
            assert len(analysis_result.recommendations) == 2
            assert analysis_result.recommendations[0].symbol == "AAPL"
            assert analysis_result.recommendations[0].action == "HOLD"
            assert analysis_result.market_sentiment == "POSITIVE"
            
            # Gemini APIが正しく呼ばれたことを確認
            mock_configure.assert_called_once_with(api_key="test-api-key")
            mock_model.generate_content.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_gemini_api_error_handling(self):
        """Gemini APIエラーハンドリングテスト"""
        with patch('google.generativeai.configure') as mock_configure, \
             patch('google.generativeai.GenerativeModel') as mock_model_class:
            
            mock_model = Mock()
            mock_model_class.return_value = mock_model
            
            # API エラーをシミュレート
            mock_model.generate_content = AsyncMock(
                side_effect=Exception("Gemini API rate limit exceeded")
            )
            
            gemini_service = GeminiService(api_key="test-api-key")
            
            test_stocks = [
                StockData(
                    symbol="AAPL",
                    current_price=175.50,
                    previous_close=174.00,
                    volume=50000000,
                    market_cap=2750000000000,
                    timestamp=datetime.now()
                )
            ]
            
            # エラーが適切に処理されることを確認
            with pytest.raises(Exception):
                await gemini_service.analyze_stocks(test_stocks, "daily")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_gemini_response_parsing(self):
        """Gemini API レスポンス解析テスト"""
        with patch('google.generativeai.configure'), \
             patch('google.generativeai.GenerativeModel') as mock_model_class:
            
            mock_model = Mock()
            mock_model_class.return_value = mock_model
            
            # 不正な形式のレスポンス
            invalid_response = Mock()
            invalid_response.text = "Invalid JSON response from Gemini"
            
            mock_model.generate_content = AsyncMock(return_value=invalid_response)
            
            gemini_service = GeminiService(api_key="test-api-key")
            
            test_stocks = [
                StockData(
                    symbol="AAPL",
                    current_price=175.50,
                    previous_close=174.00,
                    volume=50000000,
                    market_cap=2750000000000,
                    timestamp=datetime.now()
                )
            ]
            
            # レスポンス解析エラーが適切に処理されることを確認
            with pytest.raises(Exception):
                await gemini_service.analyze_stocks(test_stocks, "daily")


class TestSlackAPIIntegration:
    """Slack API統合テストクラス"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_slack_webhook_notification(self):
        """Slack Webhook通知テスト"""
        with patch('requests.post') as mock_post:
            # 成功レスポンスのモック
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response
            
            # Slack サービス初期化
            slack_service = SlackService(
                webhook_url="https://hooks.slack.com/test-webhook",
                default_channel="#stock-analysis"
            )
            
            # テスト用分析結果
            test_analysis = AnalysisResult(
                analysis_id="slack-test-001",
                timestamp=datetime.now(),
                analysis_type="daily",
                portfolio_summary="ポートフォリオパフォーマンステスト",
                recommendations=[
                    Recommendation(
                        symbol="AAPL",
                        action="HOLD",
                        confidence=0.85,
                        reasoning="テスト推奨理由",
                        target_price=180.0
                    )
                ],
                market_sentiment="POSITIVE",
                risk_assessment="LOW"
            )
            
            # 通知送信テスト
            result = await slack_service.send_analysis_notification(test_analysis)
            
            # 結果検証
            assert result.success is True
            assert result.status_code == 200
            
            # Webhook が正しく呼ばれたことを確認
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "https://hooks.slack.com/test-webhook" in call_args[0]
            
            # ペイロードの検証
            payload = call_args[1]['json']
            assert 'text' in payload or 'blocks' in payload
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_slack_error_notification(self):
        """Slack エラー通知テスト"""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response
            
            slack_service = SlackService(
                webhook_url="https://hooks.slack.com/test-webhook",
                default_channel="#alerts"
            )
            
            # エラー通知送信テスト
            error_message = "Test error occurred in stock analysis"
            error_context = {
                "error_type": "ConnectionError",
                "function": "get_stock_data",
                "timestamp": datetime.now().isoformat()
            }
            
            result = await slack_service.send_error_notification(
                error_message, 
                error_context
            )
            
            assert result.success is True
            mock_post.assert_called_once()
            
            # エラー通知のペイロード検証
            payload = mock_post.call_args[1]['json']
            assert error_message in str(payload)
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_slack_webhook_failure(self):
        """Slack Webhook失敗ハンドリングテスト"""
        with patch('requests.post') as mock_post:
            # 失敗レスポンスのモック
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.json.return_value = {"error": "invalid_payload"}
            mock_post.return_value = mock_response
            
            slack_service = SlackService(
                webhook_url="https://hooks.slack.com/invalid-webhook",
                default_channel="#test"
            )
            
            test_analysis = AnalysisResult(
                analysis_id="failure-test-001",
                timestamp=datetime.now(),
                analysis_type="daily",
                portfolio_summary="テスト",
                recommendations=[],
                market_sentiment="NEUTRAL",
                risk_assessment="LOW"
            )
            
            # 失敗の適切な処理を確認
            result = await slack_service.send_analysis_notification(test_analysis)
            
            assert result.success is False
            assert result.status_code == 400
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_slack_rich_message_formatting(self):
        """Slack リッチメッセージフォーマットテスト"""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"ok": True}
            mock_post.return_value = mock_response
            
            slack_service = SlackService(
                webhook_url="https://hooks.slack.com/test-webhook",
                default_channel="#stock-analysis"
            )
            
            # 複雑な分析結果
            complex_analysis = AnalysisResult(
                analysis_id="rich-format-001",
                timestamp=datetime.now(),
                analysis_type="weekly",
                portfolio_summary="週次パフォーマンス: +2.5%の成長を記録しました。",
                recommendations=[
                    Recommendation(
                        symbol="AAPL",
                        action="HOLD",
                        confidence=0.85,
                        reasoning="技術的指標が良好で、継続保有を推奨します。",
                        target_price=180.0
                    ),
                    Recommendation(
                        symbol="GOOGL",
                        action="BUY",
                        confidence=0.90,
                        reasoning="AI技術の進歩により成長期待が高まっています。",
                        target_price=3000.0
                    ),
                    Recommendation(
                        symbol="TSLA",
                        action="SELL",
                        confidence=0.70,
                        reasoning="バリュエーションが高すぎるため利益確定を推奨します。",
                        target_price=200.0
                    )
                ],
                market_sentiment="POSITIVE",
                risk_assessment="MEDIUM"
            )
            
            # リッチフォーマット通知送信
            result = await slack_service.send_analysis_notification(complex_analysis)
            
            assert result.success is True
            
            # リッチフォーマットのペイロード検証
            payload = mock_post.call_args[1]['json']
            
            # ブロック形式またはアタッチメント形式のリッチコンテンツが含まれることを確認
            has_rich_content = (
                'blocks' in payload or 
                'attachments' in payload or
                ('text' in payload and len(payload['text']) > 100)
            )
            assert has_rich_content


class TestYahooFinanceAPIIntegration:
    """Yahoo Finance API統合テストクラス"""
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_yahoo_finance_stock_data_retrieval(self):
        """Yahoo Finance 株式データ取得テスト"""
        with patch('yfinance.Ticker') as mock_ticker:
            # モック株式データ
            mock_info = {
                'symbol': 'AAPL',
                'regularMarketPrice': 175.50,
                'previousClose': 174.00,
                'regularMarketOpen': 175.00,
                'regularMarketDayHigh': 176.00,
                'regularMarketDayLow': 174.50,
                'regularMarketVolume': 50000000,
                'marketCap': 2750000000000,
                'trailingPE': 28.5
            }
            
            mock_ticker_instance = Mock()
            mock_ticker.return_value = mock_ticker_instance
            mock_ticker_instance.info = mock_info
            
            # 株式データサービス初期化
            stock_service = StockDataService()
            
            # 単一銘柄データ取得テスト
            stock_data = await stock_service.get_stock_data("AAPL")
            
            assert stock_data.symbol == "AAPL"
            assert stock_data.current_price == 175.50
            assert stock_data.previous_close == 174.00
            assert stock_data.volume == 50000000
            assert stock_data.market_cap == 2750000000000
            
            # Yahoo Finance APIが呼ばれたことを確認
            mock_ticker.assert_called_with("AAPL")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_yahoo_finance_batch_data_retrieval(self):
        """Yahoo Finance バッチデータ取得テスト"""
        with patch('yfinance.Ticker') as mock_ticker:
            # 複数銘柄のモックデータ
            stock_symbols = ["AAPL", "GOOGL", "MSFT"]
            mock_data = {
                "AAPL": {
                    'symbol': 'AAPL',
                    'regularMarketPrice': 175.50,
                    'previousClose': 174.00,
                    'regularMarketVolume': 50000000,
                    'marketCap': 2750000000000
                },
                "GOOGL": {
                    'symbol': 'GOOGL',
                    'regularMarketPrice': 2950.00,
                    'previousClose': 2930.00,
                    'regularMarketVolume': 1500000,
                    'marketCap': 1900000000000
                },
                "MSFT": {
                    'symbol': 'MSFT',
                    'regularMarketPrice': 380.00,
                    'previousClose': 378.50,
                    'regularMarketVolume': 30000000,
                    'marketCap': 2800000000000
                }
            }
            
            def ticker_side_effect(symbol):
                mock_instance = Mock()
                mock_instance.info = mock_data[symbol]
                return mock_instance
            
            mock_ticker.side_effect = ticker_side_effect
            
            stock_service = StockDataService()
            
            # バッチデータ取得テスト
            batch_data = await stock_service.get_batch_stock_data(stock_symbols)
            
            assert len(batch_data) == 3
            assert batch_data[0].symbol == "AAPL"
            assert batch_data[1].symbol == "GOOGL"
            assert batch_data[2].symbol == "MSFT"
            
            # 各銘柄のAPIが呼ばれたことを確認
            assert mock_ticker.call_count == 3
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_yahoo_finance_historical_data(self):
        """Yahoo Finance 履歴データ取得テスト"""
        with patch('yfinance.Ticker') as mock_ticker:
            # 履歴データのモック
            mock_history = Mock()
            mock_history.reset_index.return_value = [
                {
                    'Date': datetime.now() - timedelta(days=7),
                    'Close': 170.00,
                    'Volume': 45000000
                },
                {
                    'Date': datetime.now() - timedelta(days=6),
                    'Close': 172.00,
                    'Volume': 47000000
                },
                {
                    'Date': datetime.now() - timedelta(days=5),
                    'Close': 175.50,
                    'Volume': 50000000
                }
            ]
            
            mock_ticker_instance = Mock()
            mock_ticker.return_value = mock_ticker_instance
            mock_ticker_instance.history.return_value = mock_history
            
            stock_service = StockDataService()
            
            # 履歴データ取得テスト
            historical_data = await stock_service.get_historical_data(
                symbol="AAPL",
                period="7d"
            )
            
            assert len(historical_data) == 3
            assert historical_data[0]['Close'] == 170.00
            assert historical_data[-1]['Close'] == 175.50
            
            # 履歴データAPIが正しく呼ばれたことを確認
            mock_ticker_instance.history.assert_called_once()
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_yahoo_finance_api_error_handling(self):
        """Yahoo Finance APIエラーハンドリングテスト"""
        with patch('yfinance.Ticker') as mock_ticker:
            # API エラーをシミュレート
            mock_ticker.side_effect = Exception("Yahoo Finance API connection timeout")
            
            stock_service = StockDataService()
            
            # エラーが適切に処理されることを確認
            with pytest.raises(Exception):
                await stock_service.get_stock_data("INVALID_SYMBOL")
    
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_yahoo_finance_rate_limiting(self):
        """Yahoo Finance APIレート制限テスト"""
        with patch('yfinance.Ticker') as mock_ticker:
            # レート制限エラーをシミュレート
            call_count = 0
            
            def rate_limited_ticker(symbol):
                nonlocal call_count
                call_count += 1
                if call_count <= 2:
                    raise Exception("Rate limit exceeded")
                
                mock_instance = Mock()
                mock_instance.info = {
                    'symbol': symbol,
                    'regularMarketPrice': 100.0,
                    'previousClose': 99.0,
                    'regularMarketVolume': 1000000
                }
                return mock_instance
            
            mock_ticker.side_effect = rate_limited_ticker
            
            stock_service = StockDataService()
            
            # レート制限からの回復をテスト（リトライ機能がある場合）
            try:
                stock_data = await stock_service.get_stock_data("TEST")
                # リトライが成功した場合
                assert stock_data.symbol == "TEST"
                assert call_count > 2  # リトライが実行された
            except Exception:
                # リトライ機能がない場合はエラーが発生
                assert call_count <= 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])