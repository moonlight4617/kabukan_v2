# -*- coding: utf-8 -*-
"""
データ検証サービスのテスト
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock

from src.services.data_validation_service import (
    DataValidationService,
    ValidationResult,
    ValidationIssue,
    NormalizationResult,
    ValidationSeverity,
    ValidationCategory
)
from src.models.data_models import StockData
from src.services.historical_data_manager import HistoricalDataset, PriceData, VolumeData, Period, Interval, DataSource


class TestValidationIssue:
    """ValidationIssueクラスのテスト"""
    
    def test_issue_creation(self):
        """検証問題の作成"""
        issue = ValidationIssue(
            category=ValidationCategory.DATA_INTEGRITY,
            severity=ValidationSeverity.ERROR,
            field="price",
            message="価格が負の値です",
            value=-10.0,
            suggestion="価格を正の値に修正してください"
        )
        
        assert issue.category == ValidationCategory.DATA_INTEGRITY
        assert issue.severity == ValidationSeverity.ERROR
        assert issue.field == "price"
        assert issue.message == "価格が負の値です"
        assert issue.value == -10.0
        assert issue.suggestion == "価格を正の値に修正してください"
    
    def test_issue_string_representation(self):
        """文字列表現のテスト"""
        issue = ValidationIssue(
            category=ValidationCategory.BUSINESS_LOGIC,
            severity=ValidationSeverity.WARNING,
            field="volume",
            message="出来高が異常に大きいです"
        )
        
        str_repr = str(issue)
        assert "[WARNING]" in str_repr
        assert "business_logic" in str_repr
        assert "volume" in str_repr
        assert "出来高が異常に大きいです" in str_repr


class TestValidationResult:
    """ValidationResultクラスのテスト"""
    
    def test_empty_result(self):
        """空の検証結果"""
        result = ValidationResult(is_valid=True)
        
        assert result.is_valid
        assert len(result.issues) == 0
        assert result.warnings_count == 0
        assert result.errors_count == 0
        assert result.critical_count == 0
    
    def test_add_issues(self):
        """問題の追加"""
        result = ValidationResult(is_valid=True)
        
        # 警告を追加
        warning = ValidationIssue(
            category=ValidationCategory.DATA_QUALITY,
            severity=ValidationSeverity.WARNING,
            field="name",
            message="株式名が空です"
        )
        result.add_issue(warning)
        
        assert result.warnings_count == 1
        assert result.is_valid  # 警告だけなら有効
        
        # エラーを追加
        error = ValidationIssue(
            category=ValidationCategory.DATA_INTEGRITY,
            severity=ValidationSeverity.ERROR,
            field="price",
            message="価格が負の値です"
        )
        result.add_issue(error)
        
        assert result.errors_count == 1
        assert not result.is_valid  # エラーがあれば無効
        
        # クリティカルを追加
        critical = ValidationIssue(
            category=ValidationCategory.DATA_INTEGRITY,
            severity=ValidationSeverity.CRITICAL,
            field="symbol",
            message="シンボルが空です"
        )
        result.add_issue(critical)
        
        assert result.critical_count == 1
        assert not result.is_valid
    
    def test_get_issues_by_severity(self):
        """重要度別問題取得"""
        result = ValidationResult(is_valid=True)
        
        warning = ValidationIssue(ValidationCategory.DATA_QUALITY, ValidationSeverity.WARNING, "field1", "warning")
        error = ValidationIssue(ValidationCategory.DATA_INTEGRITY, ValidationSeverity.ERROR, "field2", "error")
        
        result.add_issue(warning)
        result.add_issue(error)
        
        warnings = result.get_issues_by_severity(ValidationSeverity.WARNING)
        errors = result.get_issues_by_severity(ValidationSeverity.ERROR)
        
        assert len(warnings) == 1
        assert len(errors) == 1
        assert warnings[0].message == "warning"
        assert errors[0].message == "error"
    
    def test_get_issues_by_category(self):
        """カテゴリ別問題取得"""
        result = ValidationResult(is_valid=True)
        
        data_quality = ValidationIssue(ValidationCategory.DATA_QUALITY, ValidationSeverity.WARNING, "field1", "quality")
        data_integrity = ValidationIssue(ValidationCategory.DATA_INTEGRITY, ValidationSeverity.ERROR, "field2", "integrity")
        
        result.add_issue(data_quality)
        result.add_issue(data_integrity)
        
        quality_issues = result.get_issues_by_category(ValidationCategory.DATA_QUALITY)
        integrity_issues = result.get_issues_by_category(ValidationCategory.DATA_INTEGRITY)
        
        assert len(quality_issues) == 1
        assert len(integrity_issues) == 1
        assert quality_issues[0].message == "quality"
        assert integrity_issues[0].message == "integrity"


class TestNormalizationResult:
    """NormalizationResultクラスのテスト"""
    
    def test_normalization_result(self):
        """正規化結果の作成"""
        mock_data = Mock()
        result = NormalizationResult(
            success=True,
            normalized_data=mock_data
        )
        
        assert result.success
        assert result.normalized_data == mock_data
        assert len(result.changes_made) == 0
        assert len(result.issues) == 0
    
    def test_add_change(self):
        """変更の追加"""
        result = NormalizationResult(success=True)
        
        result.add_change("シンボルを大文字に変換")
        result.add_change("価格を小数点2桁に丸め")
        
        assert len(result.changes_made) == 2
        assert "シンボルを大文字に変換" in result.changes_made
        assert "価格を小数点2桁に丸め" in result.changes_made


class TestDataValidationService:
    """DataValidationServiceクラスのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.service = DataValidationService(strict_mode=False, auto_fix=True)
        self.strict_service = DataValidationService(strict_mode=True, auto_fix=True)
    
    def test_service_initialization(self):
        """サービス初期化"""
        assert self.service.strict_mode is False
        assert self.service.auto_fix is True
        
        assert self.strict_service.strict_mode is True
        assert self.strict_service.auto_fix is True
    
    def test_validate_valid_stock_data(self):
        """有効な株式データの検証"""
        stock_data = StockData(
            symbol="AAPL",
            name="Apple Inc.",
            current_price=150.0,
            previous_close=149.0,
            open_price=148.0,
            high_price=151.0,
            low_price=147.0,
            volume=1000000,
            market_cap=2500000000000,
            currency="USD",
            exchange="NASDAQ",
            timestamp=datetime.now()
        )
        
        result = self.service.validate_stock_data(stock_data)
        
        assert result.is_valid
        assert result.errors_count == 0
        assert result.critical_count == 0
    
    def test_validate_invalid_stock_data(self):
        """無効な株式データの検証"""
        stock_data = StockData(
            symbol="",  # 空のシンボル
            name="",    # 空の名前
            current_price=-10.0,  # 負の価格
            previous_close=100.0,
            open_price=95.0,
            high_price=90.0,  # 高値が安値より低い
            low_price=105.0,
            volume=-1000,  # 負の出来高
            currency="INVALID",  # 無効な通貨
            exchange="UNKNOWN",
            timestamp=datetime.now()
        )
        
        result = self.service.validate_stock_data(stock_data)
        
        assert not result.is_valid
        assert result.errors_count > 0
        assert result.critical_count > 0
        
        # 特定の問題が検出されているかチェック
        issues = [issue.message for issue in result.issues]
        assert any("シンボルが空" in issue for issue in issues)
        assert any("価格が負の値" in issue for issue in issues)
        assert any("高値が安値より低い" in issue for issue in issues)
        assert any("出来高が負の値" in issue for issue in issues)
    
    def test_validate_price_relationships(self):
        """価格関係の検証"""
        # 高値・安値の関係が正しくない場合
        stock_data = StockData(
            symbol="TEST",
            name="Test Stock",
            current_price=100.0,
            previous_close=99.0,
            open_price=110.0,  # 始値が高値より高い
            high_price=105.0,
            low_price=95.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        result = self.service.validate_stock_data(stock_data)
        
        assert not result.is_valid
        errors = [issue.message for issue in result.get_issues_by_severity(ValidationSeverity.ERROR)]
        assert any("始値が高値・安値の範囲外" in error for error in errors)
    
    def test_validate_extreme_price_changes(self):
        """極端な価格変動の検証"""
        stock_data = StockData(
            symbol="VOLATILE",
            name="Volatile Stock",
            current_price=200.0,  # 100%の価格変動
            previous_close=100.0,
            open_price=100.0,
            high_price=200.0,
            low_price=100.0,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        result = self.service.validate_stock_data(stock_data)
        
        # 極端な価格変動は警告レベル
        warnings = result.get_issues_by_severity(ValidationSeverity.WARNING)
        assert any("極端な価格変動" in warning.message for warning in warnings)
    
    def test_validate_historical_data(self):
        """履歴データの検証"""
        historical_data = [
            {
                "date": "2023-01-01",
                "open": 100.0,
                "high": 105.0,
                "low": 99.0,
                "close": 104.0,
                "volume": 1000000
            },
            {
                "date": "invalid-date",  # 無効な日付
                "open": -10.0,  # 負の価格
                "high": 100.0,
                "low": 110.0,  # 高値・安値の関係が逆
                "close": 105.0,
                "volume": -5000  # 負の出来高
            }
        ]
        
        stock_data = StockData(
            symbol="TEST",
            name="Test Stock",
            current_price=105.0,
            previous_close=104.0,
            open_price=104.0,
            high_price=106.0,
            low_price=103.0,
            volume=1100000,
            timestamp=datetime.now(),
            historical_data=historical_data
        )
        
        result = self.service.validate_stock_data(stock_data)
        
        assert not result.is_valid
        errors = [issue.message for issue in result.issues]
        assert any("日付形式が無効" in error for error in errors)
        assert any("価格が負の値" in error for error in errors)
    
    def test_validate_historical_dataset(self):
        """履歴データセットの検証"""
        price_data = [
            PriceData("2023-01-01", 100.0, 105.0, 99.0, 104.0),
            PriceData("2023-01-02", 104.0, 106.0, 103.0, 105.0),
            PriceData("2023-01-03", 105.0, 107.0, 104.0, 106.0)
        ]
        
        volume_data = [
            VolumeData("2023-01-01", 1000000),
            VolumeData("2023-01-02", 1100000),
            VolumeData("2023-01-03", 1200000)
        ]
        
        dataset = HistoricalDataset(
            symbol="AAPL",
            name="Apple Inc.",
            currency="USD",
            exchange="NASDAQ",
            period=Period.THREE_MONTHS,
            interval=Interval.ONE_DAY,
            price_data=price_data,
            volume_data=volume_data,
            last_updated=datetime.now(),
            data_source=DataSource.YAHOO_FINANCE,
            total_records=3
        )
        
        result = self.service.validate_historical_dataset(dataset)
        
        assert result.is_valid
        assert result.errors_count == 0
    
    def test_validate_dataset_with_insufficient_data(self):
        """データ不足のデータセット検証"""
        # テクニカル分析には不十分な少量データ
        price_data = [
            PriceData("2023-01-01", 100.0, 105.0, 99.0, 104.0)
        ]
        
        volume_data = [
            VolumeData("2023-01-01", 1000000)
        ]
        
        dataset = HistoricalDataset(
            symbol="SHORT",
            name="Short Data",
            currency="USD",
            exchange="NASDAQ",
            period=Period.ONE_MONTH,
            interval=Interval.ONE_DAY,
            price_data=price_data,
            volume_data=volume_data,
            last_updated=datetime.now(),
            data_source=DataSource.YAHOO_FINANCE,
            total_records=1
        )
        
        result = self.service.validate_historical_dataset(dataset)
        
        # データ不足は警告レベル
        technical_issues = result.get_issues_by_category(ValidationCategory.TECHNICAL_ANALYSIS)
        assert any("テクニカル分析には不十分" in issue.message for issue in technical_issues)
    
    def test_normalize_stock_data(self):
        """株式データの正規化"""
        stock_data = StockData(
            symbol="  aapl  ",  # 前後の空白と小文字
            name="Apple Inc.",
            current_price=150.123456,  # 小数点以下多数
            previous_close=149.987654,
            open_price=148.555555,
            high_price=151.777777,
            low_price=147.111111,
            volume=1000000.5,  # 小数点のある出来高
            currency="  usd  ",  # 前後の空白と小文字
            exchange="  nasdaq  ",
            timestamp=datetime.now()
        )
        
        result = self.service.normalize_stock_data(stock_data)
        
        assert result.success
        assert len(result.changes_made) > 0
        
        # 正規化後の値をチェック
        assert stock_data.symbol == "AAPL"
        assert stock_data.current_price == 150.12  # 小数点2桁
        assert stock_data.volume == 1000000  # 整数
        assert stock_data.currency == "USD"
        assert stock_data.exchange == "NASDAQ"
    
    def test_normalize_japanese_stock(self):
        """日本株の正規化"""
        stock_data = StockData(
            symbol="7203",
            name="トヨタ自動車",
            current_price=2500.75,  # 円なので整数にする
            previous_close=2499.25,
            open_price=2498.50,
            high_price=2501.00,
            low_price=2497.00,
            volume=1000000,
            currency="JPY",
            exchange="TSE",
            timestamp=datetime.now()
        )
        
        result = self.service.normalize_stock_data(stock_data)
        
        assert result.success
        
        # 日本株は整数に正規化される
        assert stock_data.current_price == 2501.0  # 整数
        assert stock_data.previous_close == 2499.0
    
    def test_normalize_historical_data(self):
        """履歴データの正規化"""
        historical_data = [
            {
                "date": "2023-01-01",
                "open": 100.123456,
                "high": 105.987654,
                "low": 99.555555,
                "close": 104.777777,
                "volume": 1000000.5
            }
        ]
        
        stock_data = StockData(
            symbol="TEST",
            name="Test Stock",
            current_price=104.78,
            previous_close=100.12,
            open_price=100.12,
            high_price=105.99,
            low_price=99.56,
            volume=1000000,
            currency="USD",
            timestamp=datetime.now(),
            historical_data=historical_data
        )
        
        result = self.service.normalize_stock_data(stock_data)
        
        assert result.success
        
        # 履歴データも正規化される
        hist_record = stock_data.historical_data[0]
        assert hist_record["open"] == 100.12
        assert hist_record["volume"] == 1000000
    
    def test_validation_summary(self):
        """検証サマリーの生成"""
        # 複数の検証結果を作成
        results = []
        
        # 有効な結果
        valid_result = ValidationResult(is_valid=True)
        results.append(valid_result)
        
        # 警告付きの結果
        warning_result = ValidationResult(is_valid=True)
        warning_result.add_issue(ValidationIssue(
            ValidationCategory.DATA_QUALITY,
            ValidationSeverity.WARNING,
            "name",
            "株式名が空です"
        ))
        results.append(warning_result)
        
        # エラー付きの結果
        error_result = ValidationResult(is_valid=False)
        error_result.add_issue(ValidationIssue(
            ValidationCategory.DATA_INTEGRITY,
            ValidationSeverity.ERROR,
            "price",
            "価格が負の値です"
        ))
        results.append(error_result)
        
        summary = self.service.get_validation_summary(results)
        
        assert summary["total_validated"] == 3
        assert summary["valid_count"] == 2  # 有効なもの2つ
        assert summary["invalid_count"] == 1  # 無効なもの1つ
        assert summary["success_rate"] == 2/3
        assert summary["total_issues"] == 2
        assert summary["warnings"] == 1
        assert summary["errors"] == 1
        assert summary["critical"] == 0
        assert "most_common_issues" in summary
    
    def test_strict_mode_differences(self):
        """厳格モードの違い"""
        stock_data = StockData(
            symbol="EXTREME",
            name="Extreme Stock",
            current_price=0.005,  # 極端に低い価格
            previous_close=0.004,
            open_price=0.004,
            high_price=0.006,
            low_price=0.003,
            volume=100,
            timestamp=datetime.now()
        )
        
        # 通常モード
        normal_result = self.service.validate_stock_data(stock_data)
        
        # 厳格モード
        strict_result = self.strict_service.validate_stock_data(stock_data)
        
        # 厳格モードの方が多くの問題を検出する可能性がある
        # （極端な値に対してより厳しい）
        normal_issues = len(normal_result.issues)
        strict_issues = len(strict_result.issues)
        
        # 少なくとも同じかそれ以上の問題が検出される
        assert strict_issues >= normal_issues
    
    def test_error_handling_in_validation(self):
        """検証中のエラーハンドリング"""
        # 不正なデータ型を持つオブジェクト
        invalid_stock_data = Mock()
        invalid_stock_data.symbol = None
        invalid_stock_data.name = None
        
        # attributeエラーが発生する可能性のあるオブジェクト
        def side_effect(*args, **kwargs):
            raise AttributeError("Test attribute error")
        
        invalid_stock_data.current_price = property(side_effect)
        
        result = self.service.validate_stock_data(invalid_stock_data)
        
        # エラーが発生してもクラッシュせず、適切にハンドリングされる
        assert not result.is_valid
        critical_issues = result.get_issues_by_severity(ValidationSeverity.CRITICAL)
        assert len(critical_issues) > 0
        assert any("検証処理中にエラーが発生" in issue.message for issue in critical_issues)