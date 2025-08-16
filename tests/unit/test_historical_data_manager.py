# -*- coding: utf-8 -*-
"""
履歴データ管理サービスのテスト
"""

import pytest
import tempfile
import shutil
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
from pathlib import Path

from src.services.historical_data_manager import (
    HistoricalDataManager,
    HistoricalDataset,
    PriceData,
    VolumeData,
    DataRetrievalResult,
    CacheEntry
)
from src.services.stock_data_service import (
    StockDataService, StockDataResult, Period, Interval, DataSource
)
from src.models.data_models import StockData


class TestPriceData:
    """PriceDataクラスのテスト"""
    
    def test_price_data_creation(self):
        """価格データの作成"""
        price = PriceData(
            date="2023-01-01",
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0
        )
        
        assert price.date == "2023-01-01"
        assert price.open == 100.0
        assert price.high == 105.0
        assert price.low == 99.0
        assert price.close == 104.0
        assert price.adjusted_close == 104.0  # デフォルト値
    
    def test_price_data_with_adjusted_close(self):
        """調整後終値ありの価格データ"""
        price = PriceData(
            date="2023-01-01",
            open=100.0,
            high=105.0,
            low=99.0,
            close=104.0,
            adjusted_close=103.5
        )
        
        assert price.adjusted_close == 103.5


class TestVolumeData:
    """VolumeDataクラスのテスト"""
    
    def test_volume_data_creation(self):
        """出来高データの作成"""
        volume = VolumeData(
            date="2023-01-01",
            volume=1000000
        )
        
        assert volume.date == "2023-01-01"
        assert volume.volume == 1000000
        assert volume.volume_sma_5 is None
        assert volume.volume_sma_20 is None
        assert volume.volume_change_pct is None


class TestHistoricalDataset:
    """HistoricalDatasetクラスのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.price_data = [
            PriceData("2023-01-01", 100.0, 105.0, 99.0, 104.0),
            PriceData("2023-01-02", 104.0, 106.0, 103.0, 105.0),
            PriceData("2023-01-03", 105.0, 107.0, 104.0, 106.0)
        ]
        
        self.volume_data = [
            VolumeData("2023-01-01", 1000000),
            VolumeData("2023-01-02", 1100000),
            VolumeData("2023-01-03", 1200000)
        ]
        
        self.dataset = HistoricalDataset(
            symbol="AAPL",
            name="Apple Inc.",
            currency="USD",
            exchange="NASDAQ",
            period=Period.THREE_MONTHS,
            interval=Interval.ONE_DAY,
            price_data=self.price_data,
            volume_data=self.volume_data,
            last_updated=datetime.now(),
            data_source=DataSource.YAHOO_FINANCE,
            total_records=3
        )
    
    def test_dataset_properties(self):
        """データセットプロパティ"""
        assert not self.dataset.is_empty
        assert self.dataset.total_records == 3
        
        start_date, end_date = self.dataset.date_range
        assert start_date == "2023-01-01"
        assert end_date == "2023-01-03"
    
    def test_empty_dataset(self):
        """空のデータセット"""
        empty_dataset = HistoricalDataset(
            symbol="EMPTY",
            name="Empty",
            currency="USD",
            exchange="NASDAQ",
            period=Period.ONE_MONTH,
            interval=Interval.ONE_DAY,
            price_data=[],
            volume_data=[],
            last_updated=datetime.now(),
            data_source=DataSource.YAHOO_FINANCE,
            total_records=0
        )
        
        assert empty_dataset.is_empty
        start_date, end_date = empty_dataset.date_range
        assert start_date == ""
        assert end_date == ""
    
    def test_get_price_by_date(self):
        """日付指定価格データ取得"""
        price = self.dataset.get_price_by_date("2023-01-02")
        assert price is not None
        assert price.close == 105.0
        
        # 存在しない日付
        price = self.dataset.get_price_by_date("2023-01-04")
        assert price is None
    
    def test_get_volume_by_date(self):
        """日付指定出来高データ取得"""
        volume = self.dataset.get_volume_by_date("2023-01-02")
        assert volume is not None
        assert volume.volume == 1100000
        
        # 存在しない日付
        volume = self.dataset.get_volume_by_date("2023-01-04")
        assert volume is None
    
    def test_get_latest_data(self):
        """最新データ取得"""
        latest_price = self.dataset.get_latest_price()
        assert latest_price is not None
        assert latest_price.date == "2023-01-03"
        assert latest_price.close == 106.0
        
        latest_volume = self.dataset.get_latest_volume()
        assert latest_volume is not None
        assert latest_volume.date == "2023-01-03"
        assert latest_volume.volume == 1200000
    
    def test_get_price_range(self):
        """期間指定価格データ取得"""
        prices = self.dataset.get_price_range("2023-01-01", "2023-01-02")
        assert len(prices) == 2
        assert prices[0].date == "2023-01-01"
        assert prices[1].date == "2023-01-02"
    
    def test_get_recent_prices(self):
        """直近価格データ取得"""
        recent_prices = self.dataset.get_recent_prices(2)
        assert len(recent_prices) == 2
        assert recent_prices[0].date == "2023-01-02"
        assert recent_prices[1].date == "2023-01-03"
        
        # データ数より多い日数を指定
        all_prices = self.dataset.get_recent_prices(10)
        assert len(all_prices) == 3


class TestCacheEntry:
    """CacheEntryクラスのテスト"""
    
    def test_cache_entry_not_expired(self):
        """期限内のキャッシュエントリ"""
        dataset = Mock()
        entry = CacheEntry(
            data=dataset,
            cache_time=datetime.now(),
            ttl_seconds=3600
        )
        
        assert not entry.is_expired
    
    def test_cache_entry_expired(self):
        """期限切れのキャッシュエントリ"""
        dataset = Mock()
        entry = CacheEntry(
            data=dataset,
            cache_time=datetime.now() - timedelta(seconds=7200),  # 2時間前
            ttl_seconds=3600  # 1時間TTL
        )
        
        assert entry.is_expired


class TestHistoricalDataManager:
    """HistoricalDataManagerクラスのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.temp_dir) / "cache"
        
        # モック株式データサービス
        self.mock_stock_service = Mock(spec=StockDataService)
        self.mock_stock_service.is_available = True
        
        # テスト用履歴データ
        self.mock_historical_data = [
            {
                'date': '2023-01-01',
                'open': 100.0,
                'high': 105.0,
                'low': 99.0,
                'close': 104.0,
                'volume': 1000000
            },
            {
                'date': '2023-01-02',
                'open': 104.0,
                'high': 106.0,
                'low': 103.0,
                'close': 105.0,
                'volume': 1100000
            }
        ]
        
        self.mock_stock_data = StockData(
            symbol="AAPL",
            name="Apple Inc.",
            current_price=105.0,
            previous_close=104.0,
            open_price=104.0,
            high_price=106.0,
            low_price=103.0,
            volume=1100000,
            currency="USD",
            exchange="NASDAQ",
            timestamp=datetime.now(),
            historical_data=self.mock_historical_data
        )
        
        self.manager = HistoricalDataManager(
            stock_data_service=self.mock_stock_service,
            cache_dir=str(self.cache_dir),
            enable_cache=True,
            default_cache_ttl=3600
        )
    
    def teardown_method(self):
        """テスト後のクリーンアップ"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_manager_initialization(self):
        """マネージャー初期化"""
        assert self.manager.stock_data_service == self.mock_stock_service
        assert self.manager.enable_cache is True
        assert self.manager.default_cache_ttl == 3600
        assert self.manager.cache_dir == self.cache_dir
        assert self.cache_dir.exists()
    
    def test_get_historical_data_success(self):
        """履歴データ取得成功"""
        # モックの設定
        self.mock_stock_service.get_historical_data.return_value = StockDataResult(
            success=True,
            symbol="AAPL",
            data=self.mock_stock_data,
            source=DataSource.YAHOO_FINANCE
        )
        
        result = self.manager.get_historical_data(
            symbol="AAPL",
            period=Period.THREE_MONTHS,
            use_cache=False
        )
        
        assert result.success
        assert result.dataset is not None
        assert result.dataset.symbol == "AAPL"
        assert result.dataset.total_records == 2
        assert not result.cache_hit
        assert result.source == DataSource.YAHOO_FINANCE
        
        # 価格データの確認
        prices = result.dataset.price_data
        assert len(prices) == 2
        assert prices[0].date == "2023-01-01"
        assert prices[0].close == 104.0
        
        # 出来高データの確認
        volumes = result.dataset.volume_data
        assert len(volumes) == 2
        assert volumes[0].volume == 1000000
    
    def test_get_historical_data_api_failure(self):
        """API取得失敗"""
        self.mock_stock_service.get_historical_data.return_value = StockDataResult(
            success=False,
            symbol="AAPL",
            error_message="API error"
        )
        
        result = self.manager.get_historical_data("AAPL")
        
        assert not result.success
        assert result.error_message == "API error"
        assert result.dataset is None
    
    def test_get_historical_data_invalid_symbol(self):
        """無効な銘柄コード"""
        result = self.manager.get_historical_data("")  # 空の銘柄コード
        
        assert not result.success
        assert "銘柄コード検証エラー" in result.error_message
    
    def test_cache_functionality(self):
        """キャッシュ機能"""
        # 最初の取得
        self.mock_stock_service.get_historical_data.return_value = StockDataResult(
            success=True,
            symbol="AAPL",
            data=self.mock_stock_data,
            source=DataSource.YAHOO_FINANCE
        )
        
        result1 = self.manager.get_historical_data("AAPL", use_cache=True)
        assert result1.success
        assert not result1.cache_hit
        
        # 2回目の取得（キャッシュヒット）
        result2 = self.manager.get_historical_data("AAPL", use_cache=True)
        assert result2.success
        assert result2.cache_hit
        assert result2.dataset.symbol == "AAPL"
        
        # APIは1回だけ呼ばれる
        assert self.mock_stock_service.get_historical_data.call_count == 1
    
    def test_cache_disabled(self):
        """キャッシュ無効時"""
        manager_no_cache = HistoricalDataManager(
            stock_data_service=self.mock_stock_service,
            enable_cache=False
        )
        
        self.mock_stock_service.get_historical_data.return_value = StockDataResult(
            success=True,
            symbol="AAPL",
            data=self.mock_stock_data,
            source=DataSource.YAHOO_FINANCE
        )
        
        result1 = manager_no_cache.get_historical_data("AAPL", use_cache=True)
        result2 = manager_no_cache.get_historical_data("AAPL", use_cache=True)
        
        assert result1.success and result2.success
        assert not result1.cache_hit and not result2.cache_hit
        assert self.mock_stock_service.get_historical_data.call_count == 2
    
    def test_get_batch_historical_data(self):
        """バッチ履歴データ取得"""
        symbols = ["AAPL", "MSFT", "GOOGL"]
        
        # 各銘柄に対してモックデータを返す
        def mock_get_historical_data(request):
            stock_data = StockData(
                symbol=request.symbol,
                name=f"Mock {request.symbol}",
                current_price=100.0,
                previous_close=99.0,
                open_price=99.5,
                high_price=101.0,
                low_price=98.0,
                volume=1000000,
                currency="USD",
                exchange="NASDAQ",
                timestamp=datetime.now(),
                historical_data=self.mock_historical_data
            )
            return StockDataResult(
                success=True,
                symbol=request.symbol,
                data=stock_data,
                source=DataSource.YAHOO_FINANCE
            )
        
        self.mock_stock_service.get_historical_data.side_effect = mock_get_historical_data
        
        results = self.manager.get_batch_historical_data(symbols, use_cache=False)
        
        assert len(results) == 3
        success_count = sum(1 for r in results if r.success)
        assert success_count == 3
        
        # 各結果の確認
        for i, result in enumerate(results):
            assert result.success
            assert result.dataset.symbol == symbols[i]
    
    def test_get_batch_historical_data_partial_failure(self):
        """バッチ取得の部分的失敗"""
        symbols = ["AAPL", "INVALID", "MSFT"]
        
        def mock_get_historical_data(request):
            if request.symbol == "INVALID":
                return StockDataResult(
                    success=False,
                    symbol="INVALID",
                    error_message="Invalid symbol"
                )
            else:
                stock_data = StockData(
                    symbol=request.symbol,
                    name=f"Mock {request.symbol}",
                    current_price=100.0,
                    previous_close=99.0,
                    open_price=99.5,
                    high_price=101.0,
                    low_price=98.0,
                    volume=1000000,
                    currency="USD",
                    exchange="NASDAQ",
                    timestamp=datetime.now(),
                    historical_data=self.mock_historical_data
                )
                return StockDataResult(
                    success=True,
                    symbol=request.symbol,
                    data=stock_data,
                    source=DataSource.YAHOO_FINANCE
                )
        
        self.mock_stock_service.get_historical_data.side_effect = mock_get_historical_data
        
        results = self.manager.get_batch_historical_data(symbols, use_cache=False)
        
        assert len(results) == 3
        success_count = sum(1 for r in results if r.success)
        assert success_count == 2
        
        # 失敗した結果の確認
        invalid_result = next(r for r in results if r.dataset is None)
        assert not invalid_result.success
        assert "Invalid symbol" in invalid_result.error_message
    
    def test_volume_data_enhancement(self):
        """出来高データ拡張"""
        # 長期間のテストデータ作成
        long_historical_data = []
        for i in range(25):  # 25日分
            date = (datetime(2023, 1, 1) + timedelta(days=i)).strftime('%Y-%m-%d')
            long_historical_data.append({
                'date': date,
                'open': 100.0 + i,
                'high': 105.0 + i,
                'low': 99.0 + i,
                'close': 104.0 + i,
                'volume': 1000000 + (i * 10000)
            })
        
        long_stock_data = StockData(
            symbol="AAPL",
            name="Apple Inc.",
            current_price=129.0,
            previous_close=128.0,
            open_price=128.5,
            high_price=130.0,
            low_price=127.0,
            volume=1240000,
            currency="USD",
            exchange="NASDAQ",
            timestamp=datetime.now(),
            historical_data=long_historical_data
        )
        
        self.mock_stock_service.get_historical_data.return_value = StockDataResult(
            success=True,
            symbol="AAPL",
            data=long_stock_data,
            source=DataSource.YAHOO_FINANCE
        )
        
        result = self.manager.get_historical_data("AAPL", use_cache=False)
        
        assert result.success
        volume_data = result.dataset.volume_data
        
        # 5日移動平均の確認（5日目以降）
        fifth_volume = volume_data[4]  # 5日目
        assert fifth_volume.volume_sma_5 is not None
        
        # 20日移動平均の確認（20日目以降）
        twentieth_volume = volume_data[19]  # 20日目
        assert twentieth_volume.volume_sma_20 is not None
        
        # 変化率の確認（2日目以降）
        second_volume = volume_data[1]  # 2日目
        assert second_volume.volume_change_pct is not None
    
    def test_cache_key_generation(self):
        """キャッシュキー生成"""
        key1 = self.manager._generate_cache_key("AAPL", Period.ONE_YEAR, Interval.ONE_DAY, None, None)
        key2 = self.manager._generate_cache_key("AAPL", Period.ONE_YEAR, Interval.ONE_DAY, None, None)
        key3 = self.manager._generate_cache_key("MSFT", Period.ONE_YEAR, Interval.ONE_DAY, None, None)
        
        # 同じパラメータなら同じキー
        assert key1 == key2
        # 異なるパラメータなら異なるキー
        assert key1 != key3
        
        # 日付範囲指定
        start_date = datetime(2023, 1, 1)
        end_date = datetime(2023, 12, 31)
        key4 = self.manager._generate_cache_key("AAPL", Period.ONE_YEAR, Interval.ONE_DAY, start_date, end_date)
        assert key4 != key1  # 日付範囲指定は異なるキー
    
    def test_clear_cache(self):
        """キャッシュクリア"""
        # まずキャッシュにデータを保存
        self.mock_stock_service.get_historical_data.return_value = StockDataResult(
            success=True,
            symbol="AAPL",
            data=self.mock_stock_data,
            source=DataSource.YAHOO_FINANCE
        )
        
        self.manager.get_historical_data("AAPL", use_cache=True)
        self.manager.get_historical_data("MSFT", use_cache=True)
        
        # 特定銘柄のキャッシュクリア
        self.manager.clear_cache("AAPL")
        
        # 全キャッシュクリア
        self.manager.clear_cache()
        
        cache_info = self.manager.get_cache_info()
        assert cache_info["memory_entries"] == 0
    
    def test_cleanup_expired_cache(self):
        """期限切れキャッシュクリーンアップ"""
        # 期限切れキャッシュエントリを手動で追加
        expired_entry = CacheEntry(
            data=Mock(),
            cache_time=datetime.now() - timedelta(seconds=7200),  # 2時間前
            ttl_seconds=3600  # 1時間TTL
        )
        
        self.manager._memory_cache["expired_key"] = expired_entry
        
        # 通常のキャッシュエントリも追加
        valid_entry = CacheEntry(
            data=Mock(),
            cache_time=datetime.now(),
            ttl_seconds=3600
        )
        
        self.manager._memory_cache["valid_key"] = valid_entry
        
        # クリーンアップ実行
        self.manager.cleanup_expired_cache()
        
        # 期限切れエントリは削除され、有効エントリは残る
        assert "expired_key" not in self.manager._memory_cache
        assert "valid_key" in self.manager._memory_cache
    
    def test_get_cache_info(self):
        """キャッシュ情報取得"""
        cache_info = self.manager.get_cache_info()
        
        assert "enabled" in cache_info
        assert "cache_dir" in cache_info
        assert "memory_entries" in cache_info
        assert "disk_entries" in cache_info
        assert "total_cache_size_bytes" in cache_info
        assert "default_ttl_seconds" in cache_info
        
        assert cache_info["enabled"] is True
        assert cache_info["default_ttl_seconds"] == 3600
    
    def test_get_service_status(self):
        """サービス状況取得"""
        self.mock_stock_service.get_service_status.return_value = {
            "available": True,
            "mock_mode": False
        }
        
        status = self.manager.get_service_status()
        
        assert "available" in status
        assert "cache_enabled" in status
        assert "cache_info" in status
        assert "stock_data_service_status" in status
        
        assert status["available"] is True
        assert status["cache_enabled"] is True


class TestDataRetrievalResult:
    """DataRetrievalResultクラスのテスト"""
    
    def test_result_creation(self):
        """取得結果の作成"""
        dataset = Mock()
        result = DataRetrievalResult(
            success=True,
            dataset=dataset,
            cache_hit=True,
            retrieval_time=1.5,
            source=DataSource.YAHOO_FINANCE
        )
        
        assert result.success
        assert result.dataset == dataset
        assert result.cache_hit
        assert result.retrieval_time == 1.5
        assert result.source == DataSource.YAHOO_FINANCE