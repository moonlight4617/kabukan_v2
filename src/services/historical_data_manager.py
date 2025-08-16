# -*- coding: utf-8 -*-
"""
履歴データ管理サービス
テクニカル分析用の価格履歴と出来高履歴の管理機能を提供
"""

import os
import json
import logging
import pickle
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
import hashlib

from src.services.stock_data_service import (
    StockDataService, HistoricalDataRequest, Period, Interval, DataSource
)
from src.models.data_models import StockData
from src.utils.validators import StockValidator, ValidationError


logger = logging.getLogger(__name__)


@dataclass
class PriceData:
    """価格データ"""
    date: str
    open: float
    high: float
    low: float
    close: float
    adjusted_close: Optional[float] = None
    
    def __post_init__(self):
        if self.adjusted_close is None:
            self.adjusted_close = self.close


@dataclass
class VolumeData:
    """出来高データ"""
    date: str
    volume: int
    volume_sma_5: Optional[float] = None
    volume_sma_20: Optional[float] = None
    volume_change_pct: Optional[float] = None


@dataclass
class HistoricalDataset:
    """履歴データセット"""
    symbol: str
    name: str
    currency: str
    exchange: str
    period: Period
    interval: Interval
    price_data: List[PriceData]
    volume_data: List[VolumeData]
    last_updated: datetime
    data_source: DataSource
    total_records: int
    
    @property
    def is_empty(self) -> bool:
        """データが空かチェック"""
        return len(self.price_data) == 0 or len(self.volume_data) == 0
    
    @property
    def date_range(self) -> Tuple[str, str]:
        """データの日付範囲を取得"""
        if self.is_empty:
            return ("", "")
        return (self.price_data[0].date, self.price_data[-1].date)
    
    def get_price_by_date(self, date: str) -> Optional[PriceData]:
        """指定日の価格データを取得"""
        for price in self.price_data:
            if price.date == date:
                return price
        return None
    
    def get_volume_by_date(self, date: str) -> Optional[VolumeData]:
        """指定日の出来高データを取得"""
        for volume in self.volume_data:
            if volume.date == date:
                return volume
        return None
    
    def get_latest_price(self) -> Optional[PriceData]:
        """最新の価格データを取得"""
        return self.price_data[-1] if self.price_data else None
    
    def get_latest_volume(self) -> Optional[VolumeData]:
        """最新の出来高データを取得"""
        return self.volume_data[-1] if self.volume_data else None
    
    def get_price_range(self, start_date: str, end_date: str) -> List[PriceData]:
        """指定期間の価格データを取得"""
        return [
            price for price in self.price_data
            if start_date <= price.date <= end_date
        ]
    
    def get_recent_prices(self, days: int) -> List[PriceData]:
        """直近N日の価格データを取得"""
        return self.price_data[-days:] if len(self.price_data) >= days else self.price_data


@dataclass
class CacheEntry:
    """キャッシュエントリ"""
    data: HistoricalDataset
    cache_time: datetime
    ttl_seconds: int = 3600  # 1時間のデフォルトTTL
    
    @property
    def is_expired(self) -> bool:
        """キャッシュが期限切れかチェック"""
        return datetime.now() > self.cache_time + timedelta(seconds=self.ttl_seconds)


@dataclass
class DataRetrievalResult:
    """データ取得結果"""
    success: bool
    dataset: Optional[HistoricalDataset] = None
    cache_hit: bool = False
    error_message: Optional[str] = None
    retrieval_time: float = 0.0
    source: DataSource = DataSource.YAHOO_FINANCE


class HistoricalDataManager:
    """履歴データ管理サービス"""
    
    def __init__(self, 
                 stock_data_service: StockDataService,
                 cache_dir: Optional[str] = None,
                 enable_cache: bool = True,
                 default_cache_ttl: int = 3600):
        """
        Args:
            stock_data_service: 株式データサービス
            cache_dir: キャッシュディレクトリ
            enable_cache: キャッシュ有効化
            default_cache_ttl: デフォルトキャッシュTTL（秒）
        """
        self.stock_data_service = stock_data_service
        self.enable_cache = enable_cache
        self.default_cache_ttl = default_cache_ttl
        self.logger = logging.getLogger(__name__)
        
        # キャッシュディレクトリの設定
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            self.cache_dir = Path.home() / ".stock_analysis" / "cache"
        
        # キャッシュディレクトリの作成
        if self.enable_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        # メモリキャッシュ
        self._memory_cache: Dict[str, CacheEntry] = {}
    
    def get_historical_data(self, 
                          symbol: str,
                          period: Period = Period.ONE_YEAR,
                          interval: Interval = Interval.ONE_DAY,
                          start_date: Optional[datetime] = None,
                          end_date: Optional[datetime] = None,
                          use_cache: bool = True) -> DataRetrievalResult:
        """
        履歴データを取得
        
        Args:
            symbol: 株式シンボル
            period: 取得期間
            interval: 取得間隔
            start_date: 開始日
            end_date: 終了日
            use_cache: キャッシュ使用
            
        Returns:
            DataRetrievalResult: 取得結果
        """
        import time
        start_time = time.time()
        
        try:
            # 銘柄コード検証
            StockValidator.validate_stock_symbol(symbol)
            
            # キャッシュキーの生成
            cache_key = self._generate_cache_key(symbol, period, interval, start_date, end_date)
            
            # キャッシュチェック
            if use_cache and self.enable_cache:
                cached_data = self._get_from_cache(cache_key)
                if cached_data and not cached_data.is_expired:
                    retrieval_time = time.time() - start_time
                    self.logger.info(f"キャッシュからデータ取得: {symbol}")
                    return DataRetrievalResult(
                        success=True,
                        dataset=cached_data.data,
                        cache_hit=True,
                        retrieval_time=retrieval_time
                    )
            
            # APIからデータ取得
            request = HistoricalDataRequest(
                symbol=symbol,
                period=period,
                interval=interval,
                start_date=start_date,
                end_date=end_date
            )
            
            api_result = self.stock_data_service.get_historical_data(request)
            
            if not api_result.success:
                return DataRetrievalResult(
                    success=False,
                    error_message=api_result.error_message,
                    retrieval_time=time.time() - start_time
                )
            
            # HistoricalDatasetの作成
            dataset = self._create_dataset_from_stock_data(
                api_result.data, period, interval, api_result.source
            )
            
            # 出来高分析の追加
            self._enhance_volume_data(dataset)
            
            # キャッシュに保存
            if use_cache and self.enable_cache:
                self._save_to_cache(cache_key, dataset)
            
            retrieval_time = time.time() - start_time
            
            self.logger.info(
                f"履歴データ取得完了: {symbol} "
                f"({dataset.total_records}レコード, {retrieval_time:.2f}秒)"
            )
            
            return DataRetrievalResult(
                success=True,
                dataset=dataset,
                cache_hit=False,
                retrieval_time=retrieval_time,
                source=api_result.source
            )
            
        except ValidationError as e:
            error_msg = f"銘柄コード検証エラー: {e}"
            self.logger.error(error_msg)
            return DataRetrievalResult(
                success=False,
                error_message=error_msg,
                retrieval_time=time.time() - start_time
            )
        
        except Exception as e:
            error_msg = f"履歴データ取得エラー: {e}"
            self.logger.error(error_msg)
            return DataRetrievalResult(
                success=False,
                error_message=error_msg,
                retrieval_time=time.time() - start_time
            )
    
    def get_batch_historical_data(self, 
                                symbols: List[str],
                                period: Period = Period.ONE_YEAR,
                                interval: Interval = Interval.ONE_DAY,
                                use_cache: bool = True) -> List[DataRetrievalResult]:
        """
        複数銘柄の履歴データを一括取得
        
        Args:
            symbols: 銘柄シンボルのリスト
            period: 取得期間
            interval: 取得間隔
            use_cache: キャッシュ使用
            
        Returns:
            List[DataRetrievalResult]: 取得結果のリスト
        """
        results = []
        
        self.logger.info(f"バッチ履歴データ取得開始: {len(symbols)}銘柄")
        
        for i, symbol in enumerate(symbols):
            try:
                result = self.get_historical_data(
                    symbol=symbol,
                    period=period,
                    interval=interval,
                    use_cache=use_cache
                )
                results.append(result)
                
                # 進捗ログ
                if (i + 1) % 5 == 0:
                    success_count = sum(1 for r in results if r.success)
                    self.logger.info(f"進捗: {i + 1}/{len(symbols)} 完了 (成功: {success_count})")
                
            except Exception as e:
                error_msg = f"履歴データ取得エラー ({symbol}): {e}"
                self.logger.error(error_msg)
                results.append(DataRetrievalResult(
                    success=False,
                    error_message=error_msg
                ))
        
        success_count = sum(1 for r in results if r.success)
        cache_hit_count = sum(1 for r in results if r.cache_hit)
        
        self.logger.info(
            f"バッチ履歴データ取得完了: {success_count}/{len(symbols)} 成功 "
            f"(キャッシュヒット: {cache_hit_count})"
        )
        
        return results
    
    def _create_dataset_from_stock_data(self, 
                                      stock_data: StockData,
                                      period: Period,
                                      interval: Interval,
                                      source: DataSource) -> HistoricalDataset:
        """StockDataからHistoricalDatasetを作成"""
        price_data = []
        volume_data = []
        
        if stock_data.historical_data:
            for record in stock_data.historical_data:
                # 価格データ
                price_data.append(PriceData(
                    date=record['date'],
                    open=float(record['open']),
                    high=float(record['high']),
                    low=float(record['low']),
                    close=float(record['close']),
                    adjusted_close=float(record.get('adjusted_close', record['close']))
                ))
                
                # 出来高データ
                volume_data.append(VolumeData(
                    date=record['date'],
                    volume=int(record['volume'])
                ))
        
        return HistoricalDataset(
            symbol=stock_data.symbol,
            name=stock_data.name,
            currency=stock_data.currency,
            exchange=stock_data.exchange,
            period=period,
            interval=interval,
            price_data=price_data,
            volume_data=volume_data,
            last_updated=datetime.now(),
            data_source=source,
            total_records=len(price_data)
        )
    
    def _enhance_volume_data(self, dataset: HistoricalDataset):
        """出来高データを拡張（移動平均、変化率を追加）"""
        if len(dataset.volume_data) < 5:
            return
        
        volumes = [v.volume for v in dataset.volume_data]
        
        for i, volume_entry in enumerate(dataset.volume_data):
            # 5日移動平均
            if i >= 4:
                volume_entry.volume_sma_5 = sum(volumes[i-4:i+1]) / 5
            
            # 20日移動平均
            if i >= 19:
                volume_entry.volume_sma_20 = sum(volumes[i-19:i+1]) / 20
            
            # 前日比変化率
            if i > 0:
                prev_volume = volumes[i-1]
                if prev_volume > 0:
                    volume_entry.volume_change_pct = (
                        (volumes[i] - prev_volume) / prev_volume * 100
                    )
    
    def _generate_cache_key(self, 
                          symbol: str,
                          period: Period,
                          interval: Interval,
                          start_date: Optional[datetime],
                          end_date: Optional[datetime]) -> str:
        """キャッシュキーを生成"""
        key_parts = [
            symbol,
            period.value,
            interval.value
        ]
        
        if start_date and end_date:
            key_parts.extend([
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            ])
        
        key_string = '_'.join(key_parts)
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _get_from_cache(self, cache_key: str) -> Optional[CacheEntry]:
        """キャッシュからデータを取得"""
        # メモリキャッシュをチェック
        if cache_key in self._memory_cache:
            entry = self._memory_cache[cache_key]
            if not entry.is_expired:
                return entry
            else:
                del self._memory_cache[cache_key]
        
        # ディスクキャッシュをチェック
        cache_file = self.cache_dir / f"{cache_key}.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    entry = pickle.load(f)
                
                if not entry.is_expired:
                    # メモリキャッシュにも保存
                    self._memory_cache[cache_key] = entry
                    return entry
                else:
                    # 期限切れファイルを削除
                    cache_file.unlink()
                    
            except Exception as e:
                self.logger.warning(f"キャッシュファイル読み込みエラー: {e}")
                if cache_file.exists():
                    cache_file.unlink()
        
        return None
    
    def _save_to_cache(self, cache_key: str, dataset: HistoricalDataset):
        """キャッシュにデータを保存"""
        try:
            entry = CacheEntry(
                data=dataset,
                cache_time=datetime.now(),
                ttl_seconds=self.default_cache_ttl
            )
            
            # メモリキャッシュに保存
            self._memory_cache[cache_key] = entry
            
            # ディスクキャッシュに保存
            cache_file = self.cache_dir / f"{cache_key}.pkl"
            with open(cache_file, 'wb') as f:
                pickle.dump(entry, f)
            
            self.logger.debug(f"キャッシュ保存: {cache_key}")
            
        except Exception as e:
            self.logger.warning(f"キャッシュ保存エラー: {e}")
    
    def clear_cache(self, symbol: Optional[str] = None):
        """キャッシュをクリア"""
        if symbol:
            # 特定銘柄のキャッシュを削除
            keys_to_remove = [
                key for key in self._memory_cache.keys()
                if symbol in key
            ]
            
            for key in keys_to_remove:
                del self._memory_cache[key]
                
                cache_file = self.cache_dir / f"{key}.pkl"
                if cache_file.exists():
                    cache_file.unlink()
            
            self.logger.info(f"キャッシュクリア完了: {symbol} ({len(keys_to_remove)}個)")
        
        else:
            # 全キャッシュを削除
            self._memory_cache.clear()
            
            if self.cache_dir.exists():
                for cache_file in self.cache_dir.glob("*.pkl"):
                    cache_file.unlink()
            
            self.logger.info("全キャッシュクリア完了")
    
    def get_cache_info(self) -> Dict[str, Any]:
        """キャッシュ情報を取得"""
        memory_count = len(self._memory_cache)
        disk_count = len(list(self.cache_dir.glob("*.pkl"))) if self.cache_dir.exists() else 0
        
        # 期限切れキャッシュ数
        expired_memory = sum(
            1 for entry in self._memory_cache.values() if entry.is_expired
        )
        
        cache_size = 0
        if self.cache_dir.exists():
            cache_size = sum(
                f.stat().st_size for f in self.cache_dir.glob("*.pkl")
            )
        
        return {
            "enabled": self.enable_cache,
            "cache_dir": str(self.cache_dir),
            "memory_entries": memory_count,
            "disk_entries": disk_count,
            "expired_memory_entries": expired_memory,
            "total_cache_size_bytes": cache_size,
            "default_ttl_seconds": self.default_cache_ttl
        }
    
    def cleanup_expired_cache(self):
        """期限切れキャッシュのクリーンアップ"""
        # メモリキャッシュのクリーンアップ
        expired_keys = [
            key for key, entry in self._memory_cache.items()
            if entry.is_expired
        ]
        
        for key in expired_keys:
            del self._memory_cache[key]
        
        # ディスクキャッシュのクリーンアップ
        disk_cleaned = 0
        if self.cache_dir.exists():
            for cache_file in self.cache_dir.glob("*.pkl"):
                try:
                    with open(cache_file, 'rb') as f:
                        entry = pickle.load(f)
                    
                    if entry.is_expired:
                        cache_file.unlink()
                        disk_cleaned += 1
                        
                except Exception as e:
                    self.logger.warning(f"期限切れキャッシュチェックエラー: {e}")
                    cache_file.unlink()
                    disk_cleaned += 1
        
        self.logger.info(
            f"期限切れキャッシュクリーンアップ完了: "
            f"メモリ {len(expired_keys)}個, ディスク {disk_cleaned}個"
        )
    
    def get_service_status(self) -> Dict[str, Any]:
        """サービス状況を取得"""
        cache_info = self.get_cache_info()
        
        return {
            "available": self.stock_data_service.is_available,
            "cache_enabled": self.enable_cache,
            "cache_info": cache_info,
            "stock_data_service_status": self.stock_data_service.get_service_status()
        }