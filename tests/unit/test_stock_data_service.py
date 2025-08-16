# -*- coding: utf-8 -*-
"""
株式データサービスのテスト
"""

import pytest
import time
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import pandas as pd

from src.services.stock_data_service import (
    StockDataService,
    HistoricalDataRequest,
    StockDataResult,
    BatchDataResult,
    DataSource,
    Period,
    Interval,
    RateLimiter,
    RetryPolicy
)
from src.models.data_models import StockData


class TestRateLimiter:
    """RateLimiterクラスのテスト"""
    
    def test_rate_limiter_no_wait(self):
        """レート制限なしでの動作"""
        limiter = RateLimiter(requests_per_minute=60, burst_limit=10)
        
        # 最初のリクエストは即座に通る
        start_time = time.time()
        limiter.wait_if_needed()
        elapsed = time.time() - start_time
        
        assert elapsed < 0.1  # 100ms以内
    
    def test_rate_limiter_burst_limit(self):
        """バースト制限のテスト"""
        limiter = RateLimiter(requests_per_minute=60, burst_limit=2)
        
        # 最初の2回は即座に通る
        limiter.wait_if_needed()
        limiter.wait_if_needed()
        
        # 3回目は待機が必要
        start_time = time.time()
        limiter.wait_if_needed()
        elapsed = time.time() - start_time
        
        assert elapsed > 0  # 待機が発生


class TestRetryPolicy:
    """RetryPolicyクラスのテスト"""
    
    def test_retry_delay_calculation(self):
        """リトライ遅延の計算"""
        policy = RetryPolicy(max_retries=3, base_delay=1.0, max_delay=10.0)
        
        # 1回目のリトライ
        delay1 = policy.get_delay(1)
        assert 1.0 <= delay1 <= 2.0  # 1秒 + ジッター
        
        # 2回目のリトライ
        delay2 = policy.get_delay(2)
        assert 2.0 <= delay2 <= 3.0  # 2秒 + ジッター
        
        # 遅延なし
        delay0 = policy.get_delay(0)
        assert delay0 == 0


class TestHistoricalDataRequest:
    """HistoricalDataRequestクラスのテスト"""
    
    def test_request_with_period(self):
        """期間指定でのリクエスト"""
        request = HistoricalDataRequest(
            symbol="AAPL",
            period=Period.ONE_YEAR,
            interval=Interval.ONE_DAY
        )
        
        assert request.symbol == "AAPL"
        assert request.period == Period.ONE_YEAR
        assert request.interval == Interval.ONE_DAY
        assert request.start_date is None
        assert request.end_date is None
    
    def test_request_with_date_range(self):
        """日付範囲指定でのリクエスト"""
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)
        
        request = HistoricalDataRequest(
            symbol="7203",
            start_date=start_date,
            end_date=end_date
        )
        
        assert request.symbol == "7203"
        assert request.start_date == start_date
        assert request.end_date == end_date
        assert request.period is None  # 日付範囲指定時はNone


class TestStockDataService:
    """StockDataServiceクラスのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.mock_historical_data = pd.DataFrame({
            'Open': [100.0, 101.0, 102.0],
            'High': [105.0, 106.0, 107.0],
            'Low': [99.0, 100.0, 101.0],
            'Close': [104.0, 105.0, 106.0],
            'Volume': [1000000, 1100000, 1200000]
        }, index=pd.date_range('2023-01-01', periods=3, freq='D'))
        
        self.mock_info = {
            'longName': 'Apple Inc.',
            'previousClose': 103.0,
            'marketCap': 2500000000000,
            'currency': 'USD',
            'exchange': 'NASDAQ'
        }
    
    def test_service_initialization(self):
        """サービス初期化"""
        service = StockDataService(mock_mode=True)
        assert service.is_available
        assert service.mock_mode
        assert service.data_source == DataSource.YAHOO_FINANCE
    
    @patch('src.services.stock_data_service.YFINANCE_AVAILABLE', False)
    def test_service_yfinance_unavailable(self):
        """yfinance利用不可時"""
        service = StockDataService(mock_mode=False)
        assert not service.is_available
    
    def test_get_current_data_mock_mode(self):
        """モックモードでの現在データ取得"""
        service = StockDataService(mock_mode=True)
        result = service.get_current_data("AAPL")
        
        assert result.success
        assert result.symbol == "AAPL"
        assert result.data is not None
        assert result.data.symbol == "AAPL"
        assert result.data.current_price > 0
        assert result.source == DataSource.MOCK
    
    @patch('src.services.stock_data_service.YFINANCE_AVAILABLE', True)
    @patch('src.services.stock_data_service.yf')
    def test_get_current_data_success(self, mock_yf):
        """現在データ取得成功"""
        # yfinanceのモック設定
        mock_ticker = Mock()
        mock_ticker.info = self.mock_info
        mock_ticker.history.return_value = self.mock_historical_data
        mock_yf.Ticker.return_value = mock_ticker
        
        service = StockDataService(mock_mode=False)
        result = service.get_current_data("AAPL")
        
        assert result.success
        assert result.symbol == "AAPL"
        assert result.data is not None
        assert result.data.symbol == "AAPL"
        assert result.data.name == "Apple Inc."
        assert result.data.current_price == 106.0
        assert result.data.previous_close == 103.0
    
    @patch('src.services.stock_data_service.YFINANCE_AVAILABLE', True)
    @patch('src.services.stock_data_service.yf')
    def test_get_current_data_no_data(self, mock_yf):
        """データなしの場合"""
        mock_ticker = Mock()
        mock_ticker.history.return_value = pd.DataFrame()  # 空のDataFrame
        mock_yf.Ticker.return_value = mock_ticker
        
        service = StockDataService(mock_mode=False)
        result = service.get_current_data("INVALID")
        
        assert not result.success
        assert "株式データが見つかりません" in result.error_message
    
    def test_get_current_data_invalid_symbol(self):
        """無効な銘柄コード"""
        service = StockDataService(mock_mode=True)
        result = service.get_current_data("")  # 空の銘柄コード
        
        assert not result.success
        assert "銘柄コード検証エラー" in result.error_message
    
    @patch('src.services.stock_data_service.YFINANCE_AVAILABLE', True)
    @patch('src.services.stock_data_service.yf')
    def test_get_current_data_with_retry(self, mock_yf):
        """リトライ機能のテスト"""
        mock_ticker = Mock()
        # 最初の2回は失敗、3回目で成功
        mock_ticker.history.side_effect = [
            Exception("Network error"),
            Exception("Timeout"),
            self.mock_historical_data
        ]
        mock_ticker.info = self.mock_info
        mock_yf.Ticker.return_value = mock_ticker
        
        retry_policy = RetryPolicy(max_retries=3, base_delay=0.01)  # 高速テスト
        service = StockDataService(retry_policy=retry_policy, mock_mode=False)
        
        result = service.get_current_data("AAPL")
        
        assert result.success
        assert mock_ticker.history.call_count == 3
    
    def test_get_historical_data_mock_mode(self):
        """モックモードでの履歴データ取得"""
        service = StockDataService(mock_mode=True)
        request = HistoricalDataRequest(
            symbol="7203",
            period=Period.THREE_MONTHS
        )
        
        result = service.get_historical_data(request)
        
        assert result.success
        assert result.symbol == "7203"
        assert result.data is not None
        assert result.data.historical_data is not None
        assert len(result.data.historical_data) > 0
        assert result.source == DataSource.MOCK
    
    @patch('src.services.stock_data_service.YFINANCE_AVAILABLE', True)
    @patch('src.services.stock_data_service.yf')
    def test_get_historical_data_success(self, mock_yf):
        """履歴データ取得成功"""
        mock_ticker = Mock()
        mock_ticker.info = self.mock_info
        mock_ticker.history.return_value = self.mock_historical_data
        mock_yf.Ticker.return_value = mock_ticker
        
        service = StockDataService(mock_mode=False)
        request = HistoricalDataRequest(
            symbol="AAPL",
            period=Period.ONE_MONTH
        )
        
        result = service.get_historical_data(request)
        
        assert result.success
        assert result.data.historical_data is not None
        assert len(result.data.historical_data) == 3
        
        # 履歴データの内容確認
        hist_data = result.data.historical_data[0]
        assert 'date' in hist_data
        assert 'open' in hist_data
        assert 'high' in hist_data
        assert 'low' in hist_data
        assert 'close' in hist_data
        assert 'volume' in hist_data
    
    def test_get_batch_data_success(self):
        """バッチデータ取得成功"""
        service = StockDataService(mock_mode=True)
        symbols = ["AAPL", "MSFT", "7203"]
        
        result = service.get_batch_data(symbols)
        
        assert result.success_count == 3
        assert result.total_count == 3
        assert result.success_rate == 1.0
        assert len(result.results) == 3
        assert len(result.errors) == 0
        assert result.execution_time > 0
    
    def test_get_batch_data_empty_list(self):
        """空リストでのバッチ取得"""
        service = StockDataService(mock_mode=True)
        result = service.get_batch_data([])
        
        assert result.success_count == 0
        assert result.total_count == 0
        assert len(result.errors) == 1
        assert "銘柄リストが空です" in result.errors[0]
    
    def test_get_batch_data_with_duplicates(self):
        """重複ありのバッチ取得"""
        service = StockDataService(mock_mode=True)
        symbols = ["AAPL", "AAPL", "MSFT"]  # AAPLが重複
        
        result = service.get_batch_data(symbols)
        
        assert result.total_count == 2  # 重複除去後
        assert len(result.warnings) > 0
        assert "重複する銘柄を除去" in result.warnings[0]
    
    @patch('src.services.stock_data_service.YFINANCE_AVAILABLE', True)
    @patch('src.services.stock_data_service.yf')
    def test_get_batch_data_partial_failure(self, mock_yf):
        """部分的失敗のバッチ取得"""
        def mock_ticker_side_effect(symbol):
            mock_ticker = Mock()
            if symbol == "INVALID":
                mock_ticker.history.return_value = pd.DataFrame()  # 空データ
            else:
                mock_ticker.history.return_value = self.mock_historical_data
                mock_ticker.info = self.mock_info
            return mock_ticker
        
        mock_yf.Ticker.side_effect = mock_ticker_side_effect
        
        service = StockDataService(mock_mode=False)
        result = service.get_batch_data(["AAPL", "INVALID", "MSFT"])
        
        assert result.success_count == 2
        assert result.total_count == 3
        assert result.success_rate == 2/3
        assert len(result.errors) == 1
        assert "INVALID" in result.errors[0]
    
    def test_validate_connection_mock_mode(self):
        """モックモードでの接続検証"""
        service = StockDataService(mock_mode=True)
        assert service.validate_connection() is True
    
    @patch('src.services.stock_data_service.YFINANCE_AVAILABLE', True)
    @patch('src.services.stock_data_service.yf')
    def test_validate_connection_success(self, mock_yf):
        """接続検証成功"""
        mock_ticker = Mock()
        mock_ticker.info = {'symbol': 'AAPL', 'shortName': 'Apple'}
        mock_yf.Ticker.return_value = mock_ticker
        
        service = StockDataService(mock_mode=False)
        assert service.validate_connection() is True
    
    @patch('src.services.stock_data_service.YFINANCE_AVAILABLE', True)
    @patch('src.services.stock_data_service.yf')
    def test_validate_connection_failure(self, mock_yf):
        """接続検証失敗"""
        mock_ticker = Mock()
        mock_ticker.info = {}  # 必要なキーがない
        mock_yf.Ticker.return_value = mock_ticker
        
        service = StockDataService(mock_mode=False)
        assert service.validate_connection() is False
    
    @patch('src.services.stock_data_service.YFINANCE_AVAILABLE', False)
    def test_validate_connection_unavailable(self):
        """サービス利用不可時の接続検証"""
        service = StockDataService(mock_mode=False)
        assert service.validate_connection() is False
    
    def test_get_service_status(self):
        """サービス状況取得"""
        service = StockDataService(mock_mode=True)
        status = service.get_service_status()
        
        assert "available" in status
        assert "yfinance_installed" in status
        assert "data_source" in status
        assert "mock_mode" in status
        assert "rate_limit" in status
        assert "retry_policy" in status
        assert "connection_valid" in status
        
        assert status["mock_mode"] is True
        assert status["data_source"] == "yahoo_finance"
    
    def test_service_unavailable_responses(self):
        """サービス利用不可時のレスポンス"""
        service = StockDataService(mock_mode=False)
        service._StockDataService__dict__['is_available'] = False  # 強制的に利用不可に
        
        # 現在データ取得
        current_result = service.get_current_data("AAPL")
        assert not current_result.success
        assert "サービスが利用できません" in current_result.error_message
        
        # 履歴データ取得
        request = HistoricalDataRequest("AAPL")
        historical_result = service.get_historical_data(request)
        assert not historical_result.success
        assert "サービスが利用できません" in historical_result.error_message


class TestStockDataResult:
    """StockDataResultクラスのテスト"""
    
    def test_result_creation(self):
        """結果オブジェクトの作成"""
        stock_data = StockData(
            symbol="AAPL",
            name="Apple Inc.",
            current_price=150.0,
            previous_close=149.0,
            open_price=148.0,
            high_price=151.0,
            low_price=147.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        result = StockDataResult(
            success=True,
            symbol="AAPL",
            data=stock_data,
            source=DataSource.YAHOO_FINANCE
        )
        
        assert result.success
        assert result.symbol == "AAPL"
        assert result.data == stock_data
        assert result.source == DataSource.YAHOO_FINANCE
        assert result.timestamp is not None


class TestBatchDataResult:
    """BatchDataResultクラスのテスト"""
    
    def test_batch_result_success_rate(self):
        """バッチ結果の成功率計算"""
        result = BatchDataResult(
            success_count=7,
            total_count=10,
            results=[],
            errors=[],
            warnings=[],
            execution_time=2.5
        )
        
        assert result.success_rate == 0.7
        assert result.execution_time == 2.5
    
    def test_batch_result_zero_total(self):
        """総数0の場合の成功率"""
        result = BatchDataResult(
            success_count=0,
            total_count=0,
            results=[],
            errors=[],
            warnings=[],
            execution_time=0.0
        )
        
        assert result.success_rate == 0.0