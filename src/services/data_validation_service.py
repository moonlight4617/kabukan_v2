# -*- coding: utf-8 -*-
"""
データ検証と正規化サービス
取得データの妥当性チェック、正規化、エラーハンドリングを提供
"""

import logging
import math
from typing import Dict, List, Optional, Any, Tuple, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
import re

from src.models.data_models import StockData, StockConfig, WatchlistStock
from src.services.historical_data_manager import HistoricalDataset, PriceData, VolumeData
from src.utils.validators import ValidationError


logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """検証エラーの重要度"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ValidationCategory(Enum):
    """検証カテゴリ"""
    DATA_INTEGRITY = "data_integrity"
    BUSINESS_LOGIC = "business_logic"
    TECHNICAL_ANALYSIS = "technical_analysis"
    DATA_QUALITY = "data_quality"
    CONSISTENCY = "consistency"


@dataclass
class ValidationIssue:
    """検証問題"""
    category: ValidationCategory
    severity: ValidationSeverity
    field: str
    message: str
    value: Any = None
    expected_value: Any = None
    suggestion: Optional[str] = None
    
    def __str__(self) -> str:
        return f"[{self.severity.value.upper()}] {self.category.value}: {self.field} - {self.message}"


@dataclass
class ValidationResult:
    """検証結果"""
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    warnings_count: int = 0
    errors_count: int = 0
    critical_count: int = 0
    
    def __post_init__(self):
        self.warnings_count = sum(1 for issue in self.issues if issue.severity == ValidationSeverity.WARNING)
        self.errors_count = sum(1 for issue in self.issues if issue.severity == ValidationSeverity.ERROR)
        self.critical_count = sum(1 for issue in self.issues if issue.severity == ValidationSeverity.CRITICAL)
        
        # クリティカル、エラーがあれば無効
        self.is_valid = self.critical_count == 0 and self.errors_count == 0
    
    def add_issue(self, issue: ValidationIssue):
        """問題を追加"""
        self.issues.append(issue)
        if issue.severity == ValidationSeverity.WARNING:
            self.warnings_count += 1
        elif issue.severity == ValidationSeverity.ERROR:
            self.errors_count += 1
        elif issue.severity == ValidationSeverity.CRITICAL:
            self.critical_count += 1
        
        self.is_valid = self.critical_count == 0 and self.errors_count == 0
    
    def get_issues_by_severity(self, severity: ValidationSeverity) -> List[ValidationIssue]:
        """重要度別の問題を取得"""
        return [issue for issue in self.issues if issue.severity == severity]
    
    def get_issues_by_category(self, category: ValidationCategory) -> List[ValidationIssue]:
        """カテゴリ別の問題を取得"""
        return [issue for issue in self.issues if issue.category == category]


@dataclass
class NormalizationResult:
    """正規化結果"""
    success: bool
    normalized_data: Any = None
    changes_made: List[str] = field(default_factory=list)
    issues: List[ValidationIssue] = field(default_factory=list)
    
    def add_change(self, description: str):
        """変更を記録"""
        self.changes_made.append(description)


class DataValidationService:
    """データ検証と正規化サービス"""
    
    def __init__(self, strict_mode: bool = False, auto_fix: bool = True):
        """
        Args:
            strict_mode: 厳格モード（軽微な問題もエラーとする）
            auto_fix: 自動修正モード
        """
        self.strict_mode = strict_mode
        self.auto_fix = auto_fix
        self.logger = logging.getLogger(__name__)
    
    def validate_stock_data(self, stock_data: StockData) -> ValidationResult:
        """
        株式データの検証
        
        Args:
            stock_data: 株式データ
            
        Returns:
            ValidationResult: 検証結果
        """
        result = ValidationResult(is_valid=True)
        
        try:
            # 基本フィールドの検証
            self._validate_basic_fields(stock_data, result)
            
            # 価格データの検証
            self._validate_price_data(stock_data, result)
            
            # 出来高データの検証
            self._validate_volume_data(stock_data, result)
            
            # 市場情報の検証
            self._validate_market_info(stock_data, result)
            
            # 履歴データの検証
            if stock_data.historical_data:
                self._validate_historical_data(stock_data.historical_data, result)
            
            # ビジネスロジックの検証
            self._validate_business_logic(stock_data, result)
            
            self.logger.debug(f"株式データ検証完了: {stock_data.symbol} - {len(result.issues)}個の問題")
            
        except Exception as e:
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.CRITICAL,
                field="validation_process",
                message=f"検証処理中にエラーが発生: {e}"
            ))
        
        return result
    
    def validate_historical_dataset(self, dataset: HistoricalDataset) -> ValidationResult:
        """
        履歴データセットの検証
        
        Args:
            dataset: 履歴データセット
            
        Returns:
            ValidationResult: 検証結果
        """
        result = ValidationResult(is_valid=True)
        
        try:
            # データセット基本情報の検証
            self._validate_dataset_basic_info(dataset, result)
            
            # 価格データの整合性検証
            self._validate_price_data_consistency(dataset.price_data, result)
            
            # 出来高データの整合性検証
            self._validate_volume_data_consistency(dataset.volume_data, result)
            
            # 日付の連続性検証
            self._validate_date_continuity(dataset, result)
            
            # テクニカル分析適用可能性の検証
            self._validate_technical_analysis_readiness(dataset, result)
            
            self.logger.debug(f"履歴データセット検証完了: {dataset.symbol} - {len(result.issues)}個の問題")
            
        except Exception as e:
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.CRITICAL,
                field="validation_process",
                message=f"履歴データセット検証中にエラーが発生: {e}"
            ))
        
        return result
    
    def normalize_stock_data(self, stock_data: StockData) -> NormalizationResult:
        """
        株式データの正規化
        
        Args:
            stock_data: 株式データ
            
        Returns:
            NormalizationResult: 正規化結果
        """
        result = NormalizationResult(success=True, normalized_data=stock_data)
        
        try:
            # シンボルの正規化
            self._normalize_symbol(stock_data, result)
            
            # 価格データの正規化
            self._normalize_price_values(stock_data, result)
            
            # 出来高の正規化
            self._normalize_volume(stock_data, result)
            
            # 市場情報の正規化
            self._normalize_market_info(stock_data, result)
            
            # 履歴データの正規化
            if stock_data.historical_data:
                self._normalize_historical_data(stock_data, result)
            
            self.logger.debug(f"株式データ正規化完了: {stock_data.symbol} - {len(result.changes_made)}個の変更")
            
        except Exception as e:
            result.success = False
            result.issues.append(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.CRITICAL,
                field="normalization_process",
                message=f"正規化処理中にエラーが発生: {e}"
            ))
        
        return result
    
    def _validate_basic_fields(self, stock_data: StockData, result: ValidationResult):
        """基本フィールドの検証"""
        # シンボルの検証
        if not stock_data.symbol or not stock_data.symbol.strip():
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.CRITICAL,
                field="symbol",
                message="株式シンボルが空です"
            ))
        
        # 名前の検証
        if not stock_data.name or not stock_data.name.strip():
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_QUALITY,
                severity=ValidationSeverity.WARNING,
                field="name",
                message="株式名が空です",
                suggestion="シンボルから名前を推定することを検討してください"
            ))
        
        # タイムスタンプの検証
        if stock_data.timestamp:
            now = datetime.now()
            age = now - stock_data.timestamp
            
            if age > timedelta(hours=24):
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_QUALITY,
                    severity=ValidationSeverity.WARNING,
                    field="timestamp",
                    message=f"データが古い可能性があります ({age.days}日前)",
                    value=stock_data.timestamp
                ))
    
    def _validate_price_data(self, stock_data: StockData, result: ValidationResult):
        """価格データの検証"""
        prices = [
            ("current_price", stock_data.current_price),
            ("previous_close", stock_data.previous_close),
            ("open_price", stock_data.open_price),
            ("high_price", stock_data.high_price),
            ("low_price", stock_data.low_price)
        ]
        
        for field_name, price in prices:
            # 価格の非負性チェック
            if price is not None and price < 0:
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field=field_name,
                    message="価格が負の値です",
                    value=price
                ))
            
            # 価格の妥当性チェック（極端な値）
            if price is not None and (price > 1000000 or (price > 0 and price < 0.01)):
                severity = ValidationSeverity.WARNING if self.strict_mode else ValidationSeverity.INFO
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_QUALITY,
                    severity=severity,
                    field=field_name,
                    message="価格が極端な値です",
                    value=price
                ))
        
        # 高値・安値の関係性チェック
        if (stock_data.high_price is not None and stock_data.low_price is not None and
            stock_data.high_price < stock_data.low_price):
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.ERROR,
                field="high_low_relationship",
                message="高値が安値より低いです",
                value=f"高値: {stock_data.high_price}, 安値: {stock_data.low_price}"
            ))
        
        # 始値・終値が高値・安値の範囲内かチェック
        if all(p is not None for p in [stock_data.open_price, stock_data.current_price, 
                                       stock_data.high_price, stock_data.low_price]):
            if not (stock_data.low_price <= stock_data.open_price <= stock_data.high_price):
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field="open_price_range",
                    message="始値が高値・安値の範囲外です"
                ))
            
            if not (stock_data.low_price <= stock_data.current_price <= stock_data.high_price):
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field="current_price_range",
                    message="現在価格が高値・安値の範囲外です"
                ))
    
    def _validate_volume_data(self, stock_data: StockData, result: ValidationResult):
        """出来高データの検証"""
        if stock_data.volume is not None:
            # 出来高の非負性チェック
            if stock_data.volume < 0:
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field="volume",
                    message="出来高が負の値です",
                    value=stock_data.volume
                ))
            
            # 異常な出来高のチェック
            if stock_data.volume > 1000000000:  # 10億株
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_QUALITY,
                    severity=ValidationSeverity.WARNING,
                    field="volume",
                    message="出来高が異常に大きいです",
                    value=stock_data.volume
                ))
            
            # 出来高ゼロのチェック
            if stock_data.volume == 0:
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_QUALITY,
                    severity=ValidationSeverity.INFO,
                    field="volume",
                    message="出来高がゼロです（取引停止の可能性）",
                    value=stock_data.volume
                ))
    
    def _validate_market_info(self, stock_data: StockData, result: ValidationResult):
        """市場情報の検証"""
        # 通貨コードの検証
        if stock_data.currency:
            valid_currencies = {"USD", "JPY", "EUR", "GBP", "CAD", "AUD", "CNY", "KRW"}
            if stock_data.currency not in valid_currencies:
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_QUALITY,
                    severity=ValidationSeverity.WARNING,
                    field="currency",
                    message="認識されない通貨コードです",
                    value=stock_data.currency
                ))
        
        # 取引所の検証
        if stock_data.exchange:
            known_exchanges = {
                "NYSE", "NASDAQ", "TSE", "LSE", "TSX", "ASX", "HKEX", "SSE", "SZSE"
            }
            if stock_data.exchange not in known_exchanges:
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_QUALITY,
                    severity=ValidationSeverity.INFO,
                    field="exchange",
                    message="認識されない取引所コードです",
                    value=stock_data.exchange
                ))
        
        # 時価総額の検証
        if stock_data.market_cap is not None:
            if stock_data.market_cap <= 0:
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field="market_cap",
                    message="時価総額が無効な値です",
                    value=stock_data.market_cap
                ))
    
    def _validate_historical_data(self, historical_data: List[Dict], result: ValidationResult):
        """履歴データの検証"""
        if not historical_data:
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_QUALITY,
                severity=ValidationSeverity.WARNING,
                field="historical_data",
                message="履歴データが空です"
            ))
            return
        
        required_fields = ["date", "open", "high", "low", "close", "volume"]
        
        for i, record in enumerate(historical_data):
            # 必須フィールドの存在チェック
            for field in required_fields:
                if field not in record:
                    result.add_issue(ValidationIssue(
                        category=ValidationCategory.DATA_INTEGRITY,
                        severity=ValidationSeverity.ERROR,
                        field=f"historical_data[{i}].{field}",
                        message=f"必須フィールド '{field}' が不足しています"
                    ))
            
            # 日付形式の検証
            if "date" in record:
                try:
                    datetime.strptime(record["date"], "%Y-%m-%d")
                except ValueError:
                    result.add_issue(ValidationIssue(
                        category=ValidationCategory.DATA_INTEGRITY,
                        severity=ValidationSeverity.ERROR,
                        field=f"historical_data[{i}].date",
                        message="日付形式が無効です",
                        value=record["date"]
                    ))
            
            # 価格データの妥当性チェック
            price_fields = ["open", "high", "low", "close"]
            prices = {}
            
            for field in price_fields:
                if field in record:
                    try:
                        price = float(record[field])
                        if price < 0:
                            result.add_issue(ValidationIssue(
                                category=ValidationCategory.DATA_INTEGRITY,
                                severity=ValidationSeverity.ERROR,
                                field=f"historical_data[{i}].{field}",
                                message="価格が負の値です",
                                value=price
                            ))
                        prices[field] = price
                    except (ValueError, TypeError):
                        result.add_issue(ValidationIssue(
                            category=ValidationCategory.DATA_INTEGRITY,
                            severity=ValidationSeverity.ERROR,
                            field=f"historical_data[{i}].{field}",
                            message="価格が数値ではありません",
                            value=record[field]
                        ))
            
            # 高値・安値の関係性チェック
            if "high" in prices and "low" in prices and prices["high"] < prices["low"]:
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field=f"historical_data[{i}].high_low",
                    message="高値が安値より低いです",
                    value=f"高値: {prices['high']}, 安値: {prices['low']}"
                ))
    
    def _validate_business_logic(self, stock_data: StockData, result: ValidationResult):
        """ビジネスロジックの検証"""
        # 価格変動の妥当性チェック
        if (stock_data.current_price is not None and stock_data.previous_close is not None and
            stock_data.previous_close > 0):
            
            change_pct = abs(stock_data.current_price - stock_data.previous_close) / stock_data.previous_close * 100
            
            # 極端な価格変動のチェック
            if change_pct > 50:  # 50%以上の変動
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.BUSINESS_LOGIC,
                    severity=ValidationSeverity.WARNING,
                    field="price_change",
                    message=f"極端な価格変動です ({change_pct:.2f}%)",
                    value=change_pct,
                    suggestion="市場イベントやデータエラーの可能性を確認してください"
                ))
        
        # 出来高と価格変動の関係性チェック
        if (stock_data.volume is not None and stock_data.current_price is not None and
            stock_data.previous_close is not None and stock_data.volume > 0):
            
            price_change = abs(stock_data.current_price - stock_data.previous_close)
            relative_price_change = price_change / stock_data.previous_close if stock_data.previous_close > 0 else 0
            
            # 大きな価格変動なのに出来高が少ない場合
            if relative_price_change > 0.1 and stock_data.volume < 10000:  # 10%以上の変動で出来高1万未満
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.BUSINESS_LOGIC,
                    severity=ValidationSeverity.INFO,
                    field="volume_price_relationship",
                    message="大きな価格変動に対して出来高が少ないです",
                    suggestion="データの信頼性を確認してください"
                ))
    
    def _validate_dataset_basic_info(self, dataset: HistoricalDataset, result: ValidationResult):
        """データセット基本情報の検証"""
        if not dataset.symbol:
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.CRITICAL,
                field="symbol",
                message="シンボルが空です"
            ))
        
        if dataset.total_records != len(dataset.price_data):
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.ERROR,
                field="total_records",
                message="記録数が価格データ数と一致しません",
                value=f"記録数: {dataset.total_records}, 価格データ数: {len(dataset.price_data)}"
            ))
        
        if len(dataset.price_data) != len(dataset.volume_data):
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.ERROR,
                field="data_length_mismatch",
                message="価格データと出来高データの数が一致しません",
                value=f"価格: {len(dataset.price_data)}, 出来高: {len(dataset.volume_data)}"
            ))
    
    def _validate_price_data_consistency(self, price_data: List[PriceData], result: ValidationResult):
        """価格データの整合性検証"""
        for i, price in enumerate(price_data):
            # 各価格データの内部整合性
            if price.high < price.low:
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field=f"price_data[{i}]",
                    message=f"{price.date}: 高値が安値より低いです"
                ))
            
            # 始値・終値が高値・安値の範囲内か
            if not (price.low <= price.open <= price.high):
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field=f"price_data[{i}].open",
                    message=f"{price.date}: 始値が高値・安値の範囲外です"
                ))
            
            if not (price.low <= price.close <= price.high):
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field=f"price_data[{i}].close",
                    message=f"{price.date}: 終値が高値・安値の範囲外です"
                ))
    
    def _validate_volume_data_consistency(self, volume_data: List[VolumeData], result: ValidationResult):
        """出来高データの整合性検証"""
        for i, volume in enumerate(volume_data):
            if volume.volume < 0:
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_INTEGRITY,
                    severity=ValidationSeverity.ERROR,
                    field=f"volume_data[{i}]",
                    message=f"{volume.date}: 出来高が負の値です"
                ))
    
    def _validate_date_continuity(self, dataset: HistoricalDataset, result: ValidationResult):
        """日付の連続性検証"""
        if len(dataset.price_data) < 2:
            return
        
        dates = [datetime.strptime(price.date, "%Y-%m-%d") for price in dataset.price_data]
        dates.sort()
        
        # 重複日付のチェック
        unique_dates = set(dates)
        if len(unique_dates) != len(dates):
            result.add_issue(ValidationIssue(
                category=ValidationCategory.DATA_INTEGRITY,
                severity=ValidationSeverity.ERROR,
                field="date_duplicates",
                message="重複する日付があります"
            ))
        
        # 大きな日付の間隔のチェック
        for i in range(1, len(dates)):
            gap = (dates[i] - dates[i-1]).days
            if gap > 7:  # 7日以上の間隔
                result.add_issue(ValidationIssue(
                    category=ValidationCategory.DATA_QUALITY,
                    severity=ValidationSeverity.WARNING,
                    field="date_gaps",
                    message=f"大きな日付間隔があります: {dates[i-1].date()} → {dates[i].date()} ({gap}日)",
                    suggestion="市場休場日やデータ欠損の可能性があります"
                ))
    
    def _validate_technical_analysis_readiness(self, dataset: HistoricalDataset, result: ValidationResult):
        """テクニカル分析適用可能性の検証"""
        min_required_days = 50  # 最小必要日数
        
        if len(dataset.price_data) < min_required_days:
            result.add_issue(ValidationIssue(
                category=ValidationCategory.TECHNICAL_ANALYSIS,
                severity=ValidationSeverity.WARNING,
                field="data_length",
                message=f"テクニカル分析には不十分なデータ長です (現在: {len(dataset.price_data)}日, 推奨: {min_required_days}日以上)",
                suggestion="より長期間のデータを取得してください"
            ))
        
        # 価格のゼロ値チェック
        zero_price_count = sum(1 for price in dataset.price_data if price.close == 0)
        if zero_price_count > 0:
            result.add_issue(ValidationIssue(
                category=ValidationCategory.TECHNICAL_ANALYSIS,
                severity=ValidationSeverity.ERROR,
                field="zero_prices",
                message=f"終値がゼロの日が {zero_price_count} 日あります",
                suggestion="データの品質を確認してください"
            ))
    
    def _normalize_symbol(self, stock_data: StockData, result: NormalizationResult):
        """シンボルの正規化"""
        if stock_data.symbol:
            original_symbol = stock_data.symbol
            normalized_symbol = stock_data.symbol.upper().strip()
            
            if normalized_symbol != original_symbol:
                stock_data.symbol = normalized_symbol
                result.add_change(f"シンボルを正規化: '{original_symbol}' → '{normalized_symbol}'")
    
    def _normalize_price_values(self, stock_data: StockData, result: NormalizationResult):
        """価格値の正規化"""
        price_fields = [
            ("current_price", "current_price"),
            ("previous_close", "previous_close"),
            ("open_price", "open_price"),
            ("high_price", "high_price"),
            ("low_price", "low_price")
        ]
        
        for field_name, attr_name in price_fields:
            value = getattr(stock_data, attr_name)
            if value is not None:
                # 小数点以下を適切な桁数に丸める
                if stock_data.currency == "JPY":
                    normalized_value = round(value, 0)  # 円は整数
                else:
                    normalized_value = round(value, 2)  # その他は小数点2桁
                
                if normalized_value != value:
                    setattr(stock_data, attr_name, normalized_value)
                    result.add_change(f"{field_name}を正規化: {value} → {normalized_value}")
    
    def _normalize_volume(self, stock_data: StockData, result: NormalizationResult):
        """出来高の正規化"""
        if stock_data.volume is not None:
            # 出来高は整数にする
            if isinstance(stock_data.volume, float):
                original_volume = stock_data.volume
                stock_data.volume = int(stock_data.volume)
                result.add_change(f"出来高を整数に正規化: {original_volume} → {stock_data.volume}")
    
    def _normalize_market_info(self, stock_data: StockData, result: NormalizationResult):
        """市場情報の正規化"""
        # 通貨コードの正規化
        if stock_data.currency:
            original_currency = stock_data.currency
            normalized_currency = stock_data.currency.upper().strip()
            
            if normalized_currency != original_currency:
                stock_data.currency = normalized_currency
                result.add_change(f"通貨コードを正規化: '{original_currency}' → '{normalized_currency}'")
        
        # 取引所コードの正規化
        if stock_data.exchange:
            original_exchange = stock_data.exchange
            normalized_exchange = stock_data.exchange.upper().strip()
            
            if normalized_exchange != original_exchange:
                stock_data.exchange = normalized_exchange
                result.add_change(f"取引所コードを正規化: '{original_exchange}' → '{normalized_exchange}'")
    
    def _normalize_historical_data(self, stock_data: StockData, result: NormalizationResult):
        """履歴データの正規化"""
        if not stock_data.historical_data:
            return
        
        changes_count = 0
        
        for i, record in enumerate(stock_data.historical_data):
            # 価格フィールドの正規化
            price_fields = ["open", "high", "low", "close"]
            for field in price_fields:
                if field in record and record[field] is not None:
                    original_value = record[field]
                    if stock_data.currency == "JPY":
                        normalized_value = round(float(original_value), 0)
                    else:
                        normalized_value = round(float(original_value), 2)
                    
                    if normalized_value != original_value:
                        record[field] = normalized_value
                        changes_count += 1
            
            # 出来高の正規化
            if "volume" in record and record["volume"] is not None:
                original_volume = record["volume"]
                normalized_volume = int(float(original_volume))
                
                if normalized_volume != original_volume:
                    record["volume"] = normalized_volume
                    changes_count += 1
        
        if changes_count > 0:
            result.add_change(f"履歴データの {changes_count} 個のフィールドを正規化")
    
    def get_validation_summary(self, results: List[ValidationResult]) -> Dict[str, Any]:
        """検証結果のサマリーを取得"""
        total_issues = sum(len(result.issues) for result in results)
        total_warnings = sum(result.warnings_count for result in results)
        total_errors = sum(result.errors_count for result in results)
        total_critical = sum(result.critical_count for result in results)
        
        valid_count = sum(1 for result in results if result.is_valid)
        
        return {
            "total_validated": len(results),
            "valid_count": valid_count,
            "invalid_count": len(results) - valid_count,
            "success_rate": valid_count / len(results) if results else 0,
            "total_issues": total_issues,
            "warnings": total_warnings,
            "errors": total_errors,
            "critical": total_critical,
            "most_common_issues": self._get_most_common_issues(results)
        }
    
    def _get_most_common_issues(self, results: List[ValidationResult]) -> List[Dict[str, Any]]:
        """最も一般的な問題を取得"""
        issue_counts = {}
        
        for result in results:
            for issue in result.issues:
                key = f"{issue.category.value}_{issue.field}"
                if key not in issue_counts:
                    issue_counts[key] = {
                        "category": issue.category.value,
                        "field": issue.field,
                        "count": 0,
                        "severity": issue.severity.value,
                        "example_message": issue.message
                    }
                issue_counts[key]["count"] += 1
        
        # 発生回数順にソート
        sorted_issues = sorted(issue_counts.values(), key=lambda x: x["count"], reverse=True)
        
        return sorted_issues[:10]  # 上位10個を返す