"""
バリデーション機能のテスト
"""

import pytest
from datetime import datetime, timedelta
from src.utils.validators import (
    ValidationError,
    StockValidator,
    ConfigValidator,
    DataCollectionValidator
)


class TestStockValidator:
    """StockValidatorクラスのテスト"""
    
    def test_valid_jp_stock_symbol(self):
        """有効な日本株銘柄コード"""
        assert StockValidator.validate_stock_symbol("7203")
        assert StockValidator.validate_stock_symbol("9984")
        assert StockValidator.validate_stock_symbol("6758")
    
    def test_valid_us_stock_symbol(self):
        """有効な米国株銘柄コード"""
        assert StockValidator.validate_stock_symbol("AAPL")
        assert StockValidator.validate_stock_symbol("MSFT")
        assert StockValidator.validate_stock_symbol("GOOGL")
        assert StockValidator.validate_stock_symbol("A")  # 1文字
    
    def test_invalid_stock_symbols(self):
        """無効な銘柄コード"""
        with pytest.raises(ValidationError, match="銘柄コードが空です"):
            StockValidator.validate_stock_symbol("")
        
        with pytest.raises(ValidationError, match="無効な銘柄コード形式"):
            StockValidator.validate_stock_symbol("123")  # 3桁
        
        with pytest.raises(ValidationError, match="無効な銘柄コード形式"):
            StockValidator.validate_stock_symbol("12345")  # 5桁数字
        
        with pytest.raises(ValidationError, match="無効な銘柄コード形式"):
            StockValidator.validate_stock_symbol("ABCDEF")  # 6文字
        
        with pytest.raises(ValidationError, match="無効な銘柄コード形式"):
            StockValidator.validate_stock_symbol("ABC123")  # 英数字混在
    
    def test_valid_stock_name(self):
        """有効な銘柄名"""
        assert StockValidator.validate_stock_name("トヨタ自動車")
        assert StockValidator.validate_stock_name("Apple Inc.")
        assert StockValidator.validate_stock_name("AB")  # 最小長
    
    def test_invalid_stock_names(self):
        """無効な銘柄名"""
        with pytest.raises(ValidationError, match="銘柄名が空です"):
            StockValidator.validate_stock_name("")
        
        with pytest.raises(ValidationError, match="銘柄名が空です"):
            StockValidator.validate_stock_name("   ")  # 空白のみ
        
        with pytest.raises(ValidationError, match="銘柄名は2文字以上である必要があります"):
            StockValidator.validate_stock_name("A")
        
        with pytest.raises(ValidationError, match="銘柄名は100文字以内である必要があります"):
            StockValidator.validate_stock_name("A" * 101)
    
    def test_valid_quantity(self):
        """有効な数量"""
        assert StockValidator.validate_quantity(1)
        assert StockValidator.validate_quantity(100)
        assert StockValidator.validate_quantity(1000000)
        assert StockValidator.validate_quantity("100")  # 文字列数値
        assert StockValidator.validate_quantity(100.0)  # float
    
    def test_invalid_quantities(self):
        """無効な数量"""
        with pytest.raises(ValidationError, match="保有数量が設定されていません"):
            StockValidator.validate_quantity(None)
        
        with pytest.raises(ValidationError, match="保有数量は数値である必要があります"):
            StockValidator.validate_quantity("abc")
        
        with pytest.raises(ValidationError, match="保有数量は1以上である必要があります"):
            StockValidator.validate_quantity(0)
        
        with pytest.raises(ValidationError, match="保有数量は1以上である必要があります"):
            StockValidator.validate_quantity(-1)
        
        with pytest.raises(ValidationError, match="保有数量は1,000,000以下である必要があります"):
            StockValidator.validate_quantity(1000001)
    
    def test_valid_price(self):
        """有効な価格"""
        assert StockValidator.validate_price(100.0)
        assert StockValidator.validate_price(2500)
        assert StockValidator.validate_price("150.5")
    
    def test_invalid_prices(self):
        """無効な価格"""
        with pytest.raises(ValidationError, match="価格が設定されていません"):
            StockValidator.validate_price(None)
        
        with pytest.raises(ValidationError, match="価格は数値である必要があります"):
            StockValidator.validate_price("abc")
        
        with pytest.raises(ValidationError, match="価格は0より大きい値である必要があります"):
            StockValidator.validate_price(0)
        
        with pytest.raises(ValidationError, match="価格は0より大きい値である必要があります"):
            StockValidator.validate_price(-100)
        
        with pytest.raises(ValidationError, match="価格は1,000,000以下である必要があります"):
            StockValidator.validate_price(1000001)
    
    def test_valid_volume(self):
        """有効な出来高"""
        assert StockValidator.validate_volume(0)
        assert StockValidator.validate_volume(1000000)
        assert StockValidator.validate_volume("500000")
    
    def test_invalid_volumes(self):
        """無効な出来高"""
        with pytest.raises(ValidationError, match="出来高が設定されていません"):
            StockValidator.validate_volume(None)
        
        with pytest.raises(ValidationError, match="出来高は数値である必要があります"):
            StockValidator.validate_volume("abc")
        
        with pytest.raises(ValidationError, match="出来高は0以上である必要があります"):
            StockValidator.validate_volume(-1)
    
    def test_valid_timestamp(self):
        """有効なタイムスタンプ"""
        now = datetime.now()
        assert StockValidator.validate_timestamp(now)
        
        # 1時間前
        one_hour_ago = now - timedelta(hours=1)
        assert StockValidator.validate_timestamp(one_hour_ago)
        
        # 最大経過時間以内
        forty_seven_hours_ago = now - timedelta(hours=47)
        assert StockValidator.validate_timestamp(forty_seven_hours_ago, max_age_hours=48)
    
    def test_invalid_timestamps(self):
        """無効なタイムスタンプ"""
        with pytest.raises(ValidationError, match="タイムスタンプはdatetime型である必要があります"):
            StockValidator.validate_timestamp("2023-01-01")
        
        # 未来の時刻
        future = datetime.now() + timedelta(hours=1)
        with pytest.raises(ValidationError, match="タイムスタンプが未来の時刻です"):
            StockValidator.validate_timestamp(future)
        
        # 古すぎるデータ
        too_old = datetime.now() - timedelta(hours=49)
        with pytest.raises(ValidationError, match="データが古すぎます"):
            StockValidator.validate_timestamp(too_old, max_age_hours=48)


class TestConfigValidator:
    """ConfigValidatorクラスのテスト"""
    
    def test_valid_google_sheets_id(self):
        """有効なGoogle Sheets ID"""
        valid_id = "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        assert ConfigValidator.validate_google_sheets_id(valid_id)
    
    def test_invalid_google_sheets_ids(self):
        """無効なGoogle Sheets ID"""
        with pytest.raises(ValidationError, match="Google Sheets IDが空です"):
            ConfigValidator.validate_google_sheets_id("")
        
        with pytest.raises(ValidationError, match="Google Sheets IDの長さが無効です"):
            ConfigValidator.validate_google_sheets_id("short")
        
        with pytest.raises(ValidationError, match="Google Sheets IDの長さが無効です"):
            ConfigValidator.validate_google_sheets_id("a" * 60)
        
        with pytest.raises(ValidationError, match="Google Sheets IDに無効な文字が含まれています"):
            ConfigValidator.validate_google_sheets_id("1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2up@s")
    
    def test_valid_api_key(self):
        """有効なAPIキー"""
        valid_key = "AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI"
        assert ConfigValidator.validate_api_key(valid_key, "Test")
    
    def test_invalid_api_keys(self):
        """無効なAPIキー"""
        with pytest.raises(ValidationError, match="Test APIキーが空です"):
            ConfigValidator.validate_api_key("", "Test")
        
        with pytest.raises(ValidationError, match="Test APIキーが短すぎます"):
            ConfigValidator.validate_api_key("short", "Test")
        
        with pytest.raises(ValidationError, match="Test APIキーが長すぎます"):
            ConfigValidator.validate_api_key("a" * 201, "Test")
    
    def test_valid_webhook_url(self):
        """有効なWebhook URL"""
        valid_slack_url = "https://hooks.slack.com/services/T00000000/B00000000/XXXXXXXXXXXXXXXXXXXXXXXX"
        assert ConfigValidator.validate_webhook_url(valid_slack_url)
        
        valid_https_url = "https://example.com/webhook"
        assert ConfigValidator.validate_webhook_url(valid_https_url)
    
    def test_invalid_webhook_urls(self):
        """無効なWebhook URL"""
        with pytest.raises(ValidationError, match="Webhook URLが空です"):
            ConfigValidator.validate_webhook_url("")
        
        with pytest.raises(ValidationError, match="Webhook URLはHTTPSである必要があります"):
            ConfigValidator.validate_webhook_url("http://example.com/webhook")
        
        with pytest.raises(ValidationError, match="無効なSlack Webhook URL形式です"):
            ConfigValidator.validate_webhook_url("https://hooks.slack.com/services/invalid")


class TestDataCollectionValidator:
    """DataCollectionValidatorクラスのテスト"""
    
    def test_valid_stock_data_list(self):
        """有効な株式データリスト"""
        stock_data_list = [
            {
                "symbol": "7203",
                "current_price": 2600.0,
                "previous_close": 2550.0,
                "volume": 1000000
            },
            {
                "symbol": "AAPL",
                "current_price": 155.0,
                "previous_close": 152.0,
                "volume": 500000
            }
        ]
        errors = DataCollectionValidator.validate_stock_data_list(stock_data_list)
        assert len(errors) == 0
    
    def test_invalid_stock_data_list(self):
        """無効な株式データリスト"""
        # 空のリスト
        errors = DataCollectionValidator.validate_stock_data_list([])
        assert "株式データが空です" in errors
        
        # 必須フィールドが不足
        invalid_data = [
            {
                "symbol": "7203",
                "current_price": 2600.0
                # previous_close, volume が不足
            }
        ]
        errors = DataCollectionValidator.validate_stock_data_list(invalid_data)
        assert any("previous_close" in error for error in errors)
        assert any("volume" in error for error in errors)
        
        # 無効な値
        invalid_values = [
            {
                "symbol": "",  # 空の銘柄コード
                "current_price": -100,  # 負の価格
                "previous_close": 2550.0,
                "volume": -1000  # 負の出来高
            }
        ]
        errors = DataCollectionValidator.validate_stock_data_list(invalid_values)
        assert len(errors) > 0
    
    def test_valid_sheets_data(self):
        """有効なSheetsデータ"""
        holdings_data = [
            ["7203", "トヨタ自動車", "100", "2500"],
            ["AAPL", "Apple Inc.", "50", "150.0"]
        ]
        watchlist_data = [
            ["MSFT", "Microsoft Corporation"],
            ["GOOGL", "Alphabet Inc."]
        ]
        
        errors = DataCollectionValidator.validate_sheets_data(holdings_data, watchlist_data)
        assert len(errors) == 0
    
    def test_invalid_sheets_data(self):
        """無効なSheetsデータ"""
        # 空のデータ
        errors = DataCollectionValidator.validate_sheets_data([], [])
        assert "保有銘柄データが空です" in errors
        assert "ウォッチリストデータが空です" in errors
        
        # 不完全なデータ
        incomplete_holdings = [
            ["7203", "トヨタ自動車"],  # 数量が不足
            ["", "名前のみ", "100"]     # 銘柄コードが空
        ]
        incomplete_watchlist = [
            ["AAPL"],  # 銘柄名が不足
            ["", "名前のみ"]  # 銘柄コードが空
        ]
        
        errors = DataCollectionValidator.validate_sheets_data(incomplete_holdings, incomplete_watchlist)
        assert len(errors) > 0
        assert any("データが不足" in error for error in errors)