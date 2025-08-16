# -*- coding: utf-8 -*-
"""
株式データAPIクライアント
Yahoo Finance APIとの統合でリアルタイム・履歴データを取得
"""

import os
import json
import logging
import time
import random
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

try:
    import yfinance as yf
    import requests
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

from src.models.data_models import StockData, StockConfig, WatchlistStock
from src.utils.validators import StockValidator, ValidationError


logger = logging.getLogger(__name__)


class DataSource(Enum):
    """データソース"""
    YAHOO_FINANCE = "yahoo_finance"
    MOCK = "mock"


class Period(Enum):
    """データ取得期間"""
    ONE_DAY = "1d"
    FIVE_DAYS = "5d"
    ONE_MONTH = "1mo"
    THREE_MONTHS = "3mo"
    SIX_MONTHS = "6mo"
    ONE_YEAR = "1y"
    TWO_YEARS = "2y"
    FIVE_YEARS = "5y"
    TEN_YEARS = "10y"
    MAX = "max"


class Interval(Enum):
    """データ取得間隔"""
    ONE_MINUTE = "1m"
    TWO_MINUTES = "2m"
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    SIXTY_MINUTES = "60m"
    NINETY_MINUTES = "90m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    FIVE_DAYS = "5d"
    ONE_WEEK = "1wk"
    ONE_MONTH = "1mo"
    THREE_MONTHS = "3mo"


@dataclass
class HistoricalDataRequest:
    """履歴データリクエスト"""
    symbol: str
    period: Period = Period.ONE_YEAR
    interval: Interval = Interval.ONE_DAY
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    def __post_init__(self):
        # 日付範囲が指定されている場合はperiodを無視
        if self.start_date and self.end_date:
            self.period = None


@dataclass
class StockDataResult:
    """株式データ取得結果"""
    success: bool
    symbol: str
    data: Optional[StockData] = None
    error_message: Optional[str] = None
    source: DataSource = DataSource.YAHOO_FINANCE
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class BatchDataResult:
    """バッチデータ取得結果"""
    success_count: int
    total_count: int
    results: List[StockDataResult]
    errors: List[str]
    warnings: List[str]
    execution_time: float
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        return self.success_count / self.total_count if self.total_count > 0 else 0.0


class RateLimiter:
    """レート制限管理"""
    
    def __init__(self, requests_per_minute: int = 60, burst_limit: int = 10):
        self.requests_per_minute = requests_per_minute
        self.burst_limit = burst_limit
        self.request_times = []
        self.last_request_time = 0
    
    def wait_if_needed(self):
        """必要に応じて待機"""
        current_time = time.time()
        
        # バースト制限チェック
        if current_time - self.last_request_time < 60 / self.burst_limit:
            sleep_time = 60 / self.burst_limit - (current_time - self.last_request_time)
            time.sleep(sleep_time)
        
        # 分単位レート制限チェック
        minute_ago = current_time - 60
        self.request_times = [t for t in self.request_times if t > minute_ago]
        
        if len(self.request_times) >= self.requests_per_minute:
            sleep_time = self.request_times[0] + 60 - current_time
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.request_times.append(current_time)
        self.last_request_time = current_time


class RetryPolicy:
    """リトライポリシー"""
    
    def __init__(self, max_retries: int = 3, base_delay: float = 1.0, max_delay: float = 30.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
    
    def get_delay(self, attempt: int) -> float:
        """指数バックオフによる遅延時間を計算"""
        if attempt <= 0:
            return 0
        
        # 指数バックオフ + ランダムジッター
        delay = self.base_delay * (2 ** (attempt - 1))
        delay = min(delay, self.max_delay)
        jitter = random.uniform(0.1, 0.3) * delay
        return delay + jitter


class StockDataService:
    """株式データAPIクライアント"""
    
    def __init__(self, 
                 data_source: DataSource = DataSource.YAHOO_FINANCE,
                 rate_limiter: Optional[RateLimiter] = None,
                 retry_policy: Optional[RetryPolicy] = None,
                 timeout: float = 30.0,
                 mock_mode: bool = False):
        """
        Args:
            data_source: データソース
            rate_limiter: レート制限管理
            retry_policy: リトライポリシー
            timeout: リクエストタイムアウト
            mock_mode: モックモード
        """
        self.data_source = data_source
        self.rate_limiter = rate_limiter or RateLimiter()
        self.retry_policy = retry_policy or RetryPolicy()
        self.timeout = timeout
        self.mock_mode = mock_mode
        self.logger = logging.getLogger(__name__)
        
        # Yahoo Finance可用性チェック
        if not YFINANCE_AVAILABLE and not mock_mode:
            self.logger.warning("yfinanceライブラリがインストールされていません。")
    
    @property
    def is_available(self) -> bool:
        """サービスが利用可能かチェック"""
        return YFINANCE_AVAILABLE or self.mock_mode
    
    def get_current_data(self, symbol: str) -> StockDataResult:
        """
        現在の株式データを取得
        
        Args:
            symbol: 株式シンボル
            
        Returns:
            StockDataResult: 取得結果
        """
        if not self.is_available:
            return StockDataResult(
                success=False,
                symbol=symbol,
                error_message="株式データサービスが利用できません"
            )
        
        try:
            # 銘柄コード検証
            StockValidator.validate_stock_symbol(symbol)
            
            if self.mock_mode:
                return self._get_mock_data(symbol)
            
            # リトライ付きでデータ取得
            for attempt in range(self.retry_policy.max_retries + 1):
                try:
                    self.rate_limiter.wait_if_needed()
                    
                    # Yahoo Financeからデータ取得
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    hist = ticker.history(period="1d", interval="1m")
                    
                    if hist.empty:
                        raise ValueError(f"株式データが見つかりません: {symbol}")
                    
                    # 最新データを取得
                    latest_data = hist.iloc[-1]
                    
                    # StockDataオブジェクト作成
                    stock_data = StockData(
                        symbol=symbol,
                        name=info.get('longName', symbol),
                        current_price=float(latest_data['Close']),
                        previous_close=float(info.get('previousClose', latest_data['Close'])),
                        open_price=float(latest_data['Open']),
                        high_price=float(latest_data['High']),
                        low_price=float(latest_data['Low']),
                        volume=int(latest_data['Volume']),
                        market_cap=info.get('marketCap'),
                        currency=info.get('currency', 'USD'),
                        exchange=info.get('exchange', 'Unknown'),
                        timestamp=datetime.now()
                    )
                    
                    self.logger.info(f"株式データ取得成功: {symbol}")
                    return StockDataResult(
                        success=True,
                        symbol=symbol,
                        data=stock_data
                    )
                    
                except Exception as e:
                    if attempt < self.retry_policy.max_retries:
                        delay = self.retry_policy.get_delay(attempt + 1)
                        self.logger.warning(f"データ取得失敗 (試行{attempt + 1}/{self.retry_policy.max_retries + 1}): {symbol} - {e}")
                        time.sleep(delay)
                        continue
                    else:
                        raise e
            
        except ValidationError as e:
            error_msg = f"銘柄コード検証エラー: {e}"
            self.logger.error(error_msg)
            return StockDataResult(
                success=False,
                symbol=symbol,
                error_message=error_msg
            )
        
        except Exception as e:
            error_msg = f"データ取得エラー: {e}"
            self.logger.error(error_msg)
            return StockDataResult(
                success=False,
                symbol=symbol,
                error_message=error_msg
            )
    
    def get_historical_data(self, request: HistoricalDataRequest) -> StockDataResult:
        """
        履歴データを取得
        
        Args:
            request: 履歴データリクエスト
            
        Returns:
            StockDataResult: 取得結果（履歴データを含む）
        """
        if not self.is_available:
            return StockDataResult(
                success=False,
                symbol=request.symbol,
                error_message="株式データサービスが利用できません"
            )
        
        try:
            # 銘柄コード検証
            StockValidator.validate_stock_symbol(request.symbol)
            
            if self.mock_mode:
                return self._get_mock_historical_data(request)
            
            # リトライ付きでデータ取得
            for attempt in range(self.retry_policy.max_retries + 1):
                try:
                    self.rate_limiter.wait_if_needed()
                    
                    # Yahoo Financeからデータ取得
                    ticker = yf.Ticker(request.symbol)
                    
                    # 履歴データ取得
                    if request.start_date and request.end_date:
                        hist = ticker.history(
                            start=request.start_date,
                            end=request.end_date,
                            interval=request.interval.value
                        )
                    else:
                        hist = ticker.history(
                            period=request.period.value,
                            interval=request.interval.value
                        )
                    
                    if hist.empty:
                        raise ValueError(f"履歴データが見つかりません: {request.symbol}")
                    
                    # 基本情報も取得
                    info = ticker.info
                    
                    # 最新データ作成
                    latest_data = hist.iloc[-1]
                    
                    # 履歴データをリストに変換
                    historical_data = []
                    for index, row in hist.iterrows():
                        historical_data.append({
                            'date': index.strftime('%Y-%m-%d'),
                            'open': float(row['Open']),
                            'high': float(row['High']),
                            'low': float(row['Low']),
                            'close': float(row['Close']),
                            'volume': int(row['Volume'])
                        })
                    
                    # StockDataオブジェクト作成
                    stock_data = StockData(
                        symbol=request.symbol,
                        name=info.get('longName', request.symbol),
                        current_price=float(latest_data['Close']),
                        previous_close=float(info.get('previousClose', latest_data['Close'])),
                        open_price=float(latest_data['Open']),
                        high_price=float(latest_data['High']),
                        low_price=float(latest_data['Low']),
                        volume=int(latest_data['Volume']),
                        market_cap=info.get('marketCap'),
                        currency=info.get('currency', 'USD'),
                        exchange=info.get('exchange', 'Unknown'),
                        timestamp=datetime.now(),
                        historical_data=historical_data
                    )
                    
                    self.logger.info(f"履歴データ取得成功: {request.symbol} ({len(historical_data)}日分)")
                    return StockDataResult(
                        success=True,
                        symbol=request.symbol,
                        data=stock_data
                    )
                    
                except Exception as e:
                    if attempt < self.retry_policy.max_retries:
                        delay = self.retry_policy.get_delay(attempt + 1)
                        self.logger.warning(f"履歴データ取得失敗 (試行{attempt + 1}/{self.retry_policy.max_retries + 1}): {request.symbol} - {e}")
                        time.sleep(delay)
                        continue
                    else:
                        raise e
            
        except ValidationError as e:
            error_msg = f"銘柄コード検証エラー: {e}"
            self.logger.error(error_msg)
            return StockDataResult(
                success=False,
                symbol=request.symbol,
                error_message=error_msg
            )
        
        except Exception as e:
            error_msg = f"履歴データ取得エラー: {e}"
            self.logger.error(error_msg)
            return StockDataResult(
                success=False,
                symbol=request.symbol,
                error_message=error_msg
            )
    
    def get_batch_data(self, symbols: List[str]) -> BatchDataResult:
        """
        複数銘柄のデータを一括取得
        
        Args:
            symbols: 銘柄シンボルのリスト
            
        Returns:
            BatchDataResult: バッチ取得結果
        """
        start_time = time.time()
        results = []
        errors = []
        warnings = []
        success_count = 0
        
        if not symbols:
            return BatchDataResult(
                success_count=0,
                total_count=0,
                results=[],
                errors=["銘柄リストが空です"],
                warnings=[],
                execution_time=0.0
            )
        
        # 重複除去
        unique_symbols = list(set(symbols))
        if len(unique_symbols) != len(symbols):
            warnings.append(f"重複する銘柄を除去しました: {len(symbols)} → {len(unique_symbols)}")
        
        self.logger.info(f"バッチデータ取得開始: {len(unique_symbols)}銘柄")
        
        for i, symbol in enumerate(unique_symbols):
            try:
                result = self.get_current_data(symbol)
                results.append(result)
                
                if result.success:
                    success_count += 1
                else:
                    errors.append(f"{symbol}: {result.error_message}")
                
                # 進捗ログ
                if (i + 1) % 10 == 0:
                    self.logger.info(f"進捗: {i + 1}/{len(unique_symbols)} 完了")
                
            except Exception as e:
                error_msg = f"{symbol}: 予期しないエラー - {e}"
                errors.append(error_msg)
                self.logger.error(error_msg)
                
                results.append(StockDataResult(
                    success=False,
                    symbol=symbol,
                    error_message=str(e)
                ))
        
        execution_time = time.time() - start_time
        
        # 結果サマリー
        batch_result = BatchDataResult(
            success_count=success_count,
            total_count=len(unique_symbols),
            results=results,
            errors=errors,
            warnings=warnings,
            execution_time=execution_time
        )
        
        self.logger.info(
            f"バッチデータ取得完了: {success_count}/{len(unique_symbols)} 成功 "
            f"(成功率: {batch_result.success_rate:.1%}, 実行時間: {execution_time:.2f}秒)"
        )
        
        return batch_result
    
    def _get_mock_data(self, symbol: str) -> StockDataResult:
        """モックデータを生成"""
        import random
        
        base_price = 100.0
        if symbol.startswith('7'):  # 日本株
            base_price = 2500.0
        
        current_price = base_price * (1 + random.uniform(-0.05, 0.05))
        previous_close = base_price * (1 + random.uniform(-0.03, 0.03))
        
        stock_data = StockData(
            symbol=symbol,
            name=f"Mock Company {symbol}",
            current_price=current_price,
            previous_close=previous_close,
            open_price=base_price * (1 + random.uniform(-0.02, 0.02)),
            high_price=current_price * (1 + random.uniform(0, 0.03)),
            low_price=current_price * (1 - random.uniform(0, 0.03)),
            volume=random.randint(100000, 10000000),
            market_cap=random.randint(1000000000, 100000000000),
            currency="JPY" if symbol.startswith('7') else "USD",
            exchange="TSE" if symbol.startswith('7') else "NASDAQ",
            timestamp=datetime.now()
        )
        
        return StockDataResult(
            success=True,
            symbol=symbol,
            data=stock_data,
            source=DataSource.MOCK
        )
    
    def _get_mock_historical_data(self, request: HistoricalDataRequest) -> StockDataResult:
        """モック履歴データを生成"""
        import random
        
        # 期間に応じた日数を決定
        days = 30
        if request.period == Period.ONE_YEAR:
            days = 365
        elif request.period == Period.SIX_MONTHS:
            days = 180
        elif request.period == Period.THREE_MONTHS:
            days = 90
        elif request.start_date and request.end_date:
            days = (request.end_date - request.start_date).days
        
        # 履歴データ生成
        historical_data = []
        base_date = datetime.now() - timedelta(days=days)
        base_price = 100.0 if not request.symbol.startswith('7') else 2500.0
        
        for i in range(days):
            date = base_date + timedelta(days=i)
            price = base_price * (1 + random.uniform(-0.02, 0.02))
            
            historical_data.append({
                'date': date.strftime('%Y-%m-%d'),
                'open': price * (1 + random.uniform(-0.01, 0.01)),
                'high': price * (1 + random.uniform(0, 0.02)),
                'low': price * (1 - random.uniform(0, 0.02)),
                'close': price,
                'volume': random.randint(100000, 1000000)
            })
        
        # 最新データ
        latest = historical_data[-1]
        
        stock_data = StockData(
            symbol=request.symbol,
            name=f"Mock Company {request.symbol}",
            current_price=latest['close'],
            previous_close=historical_data[-2]['close'] if len(historical_data) > 1 else latest['close'],
            open_price=latest['open'],
            high_price=latest['high'],
            low_price=latest['low'],
            volume=latest['volume'],
            market_cap=random.randint(1000000000, 100000000000),
            currency="JPY" if request.symbol.startswith('7') else "USD",
            exchange="TSE" if request.symbol.startswith('7') else "NASDAQ",
            timestamp=datetime.now(),
            historical_data=historical_data
        )
        
        return StockDataResult(
            success=True,
            symbol=request.symbol,
            data=stock_data,
            source=DataSource.MOCK
        )
    
    def validate_connection(self) -> bool:
        """APIへの接続を検証"""
        if self.mock_mode:
            return True
        
        if not self.is_available:
            return False
        
        try:
            # 簡単なテストクエリでAPIアクセスを確認
            ticker = yf.Ticker("AAPL")
            info = ticker.info
            return 'symbol' in info or 'shortName' in info
            
        except Exception as e:
            self.logger.error(f"API接続検証に失敗: {e}")
            return False
    
    def get_service_status(self) -> Dict[str, Any]:
        """サービス状況を取得"""
        return {
            "available": self.is_available,
            "yfinance_installed": YFINANCE_AVAILABLE,
            "data_source": self.data_source.value,
            "mock_mode": self.mock_mode,
            "rate_limit": {
                "requests_per_minute": self.rate_limiter.requests_per_minute,
                "burst_limit": self.rate_limiter.burst_limit
            },
            "retry_policy": {
                "max_retries": self.retry_policy.max_retries,
                "base_delay": self.retry_policy.base_delay,
                "max_delay": self.retry_policy.max_delay
            },
            "connection_valid": self.validate_connection()
        }