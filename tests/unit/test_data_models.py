"""
データモデルのテスト
"""

import pytest
from datetime import datetime, timedelta
from src.models.data_models import (
    StockConfig,
    WatchlistStock, 
    StockData,
    StockHolding,
    Portfolio,
    GoogleSheetsConfig
)


class TestStockConfig:
    """StockConfigクラスのテスト"""
    
    def test_valid_stock_config(self):
        """有効な株式設定"""
        config = StockConfig(
            symbol="7203",
            name="トヨタ自動車",
            quantity=100,
            purchase_price=2500.0
        )
        assert config.is_valid
        assert config.symbol == "7203"
        assert config.name == "トヨタ自動車"
        assert config.quantity == 100
        assert config.purchase_price == 2500.0
    
    def test_stock_config_without_purchase_price(self):
        """購入価格なしの株式設定"""
        config = StockConfig(
            symbol="AAPL",
            name="Apple Inc.",
            quantity=50
        )
        assert config.is_valid
        assert config.purchase_price is None
    
    def test_invalid_symbol(self):
        """無効な銘柄コード"""
        with pytest.raises(ValueError, match="銘柄コードが空です"):
            StockConfig(symbol="", name="Test", quantity=100)
    
    def test_invalid_name(self):
        """無効な銘柄名"""
        with pytest.raises(ValueError, match="銘柄名が空です"):
            StockConfig(symbol="7203", name="", quantity=100)
    
    def test_invalid_quantity(self):
        """無効な保有数量"""
        with pytest.raises(ValueError, match="保有数量は1以上である必要があります"):
            StockConfig(symbol="7203", name="トヨタ", quantity=0)
    
    def test_invalid_purchase_price(self):
        """無効な購入価格"""
        with pytest.raises(ValueError, match="購入価格は0より大きい値である必要があります"):
            StockConfig(symbol="7203", name="トヨタ", quantity=100, purchase_price=-100)


class TestWatchlistStock:
    """WatchlistStockクラスのテスト"""
    
    def test_valid_watchlist_stock(self):
        """有効なウォッチリスト株式"""
        stock = WatchlistStock(symbol="MSFT", name="Microsoft Corporation")
        assert stock.is_valid
        assert stock.symbol == "MSFT"
        assert stock.name == "Microsoft Corporation"
    
    def test_invalid_symbol(self):
        """無効な銘柄コード"""
        with pytest.raises(ValueError, match="銘柄コードが空です"):
            WatchlistStock(symbol="", name="Test")
    
    def test_invalid_name(self):
        """無効な銘柄名"""
        with pytest.raises(ValueError, match="銘柄名が空です"):
            WatchlistStock(symbol="MSFT", name="")


class TestStockData:
    """StockDataクラスのテスト"""
    
    def test_valid_stock_data(self):
        """有効な株式データ"""
        timestamp = datetime.now()
        data = StockData(
            symbol="7203",
            current_price=2600.0,
            previous_close=2550.0,
            change=50.0,
            change_percent=1.96,
            volume=1000000,
            timestamp=timestamp
        )
        assert data.is_valid
        assert data.is_price_up
        assert not data.is_price_down
        assert "+" in data.get_formatted_change()
    
    def test_price_down_stock_data(self):
        """下落株式データ"""
        timestamp = datetime.now()
        data = StockData(
            symbol="7203",
            current_price=2500.0,
            previous_close=2550.0,
            change=-50.0,
            change_percent=-1.96,
            volume=1000000,
            timestamp=timestamp
        )
        assert data.is_valid
        assert not data.is_price_up
        assert data.is_price_down
        assert "-" in data.get_formatted_change()
    
    def test_invalid_price(self):
        """無効な価格"""
        with pytest.raises(ValueError, match="現在価格は0より大きい値である必要があります"):
            StockData(
                symbol="7203",
                current_price=0,
                previous_close=2550.0,
                change=-50.0,
                change_percent=-1.96,
                volume=1000000,
                timestamp=datetime.now()
            )
    
    def test_invalid_timestamp(self):
        """無効なタイムスタンプ"""
        with pytest.raises(ValueError, match="タイムスタンプはdatetime型である必要があります"):
            StockData(
                symbol="7203",
                current_price=2600.0,
                previous_close=2550.0,
                change=50.0,
                change_percent=1.96,
                volume=1000000,
                timestamp="2023-01-01"  # 文字列は無効
            )


class TestStockHolding:
    """StockHoldingクラスのテスト"""
    
    def test_profitable_holding(self):
        """利益の出ている保有株式"""
        config = StockConfig(
            symbol="7203",
            name="トヨタ自動車",
            quantity=100,
            purchase_price=2500.0
        )
        data = StockData(
            symbol="7203",
            current_price=2600.0,
            previous_close=2550.0,
            change=50.0,
            change_percent=1.96,
            volume=1000000,
            timestamp=datetime.now()
        )
        holding = StockHolding(config=config, data=data)
        
        assert holding.current_value == 260000.0  # 2600 * 100
        assert holding.unrealized_gain_loss == 10000.0  # (2600 - 2500) * 100
        assert holding.unrealized_gain_loss_percent == 4.0  # 10000 / 250000 * 100
        assert holding.is_profitable
        assert not holding.is_loss
        assert "+" in holding.get_formatted_gain_loss()
    
    def test_loss_holding(self):
        """損失の出ている保有株式"""
        config = StockConfig(
            symbol="7203",
            name="トヨタ自動車", 
            quantity=100,
            purchase_price=2700.0
        )
        data = StockData(
            symbol="7203",
            current_price=2600.0,
            previous_close=2550.0,
            change=50.0,
            change_percent=1.96,
            volume=1000000,
            timestamp=datetime.now()
        )
        holding = StockHolding(config=config, data=data)
        
        assert holding.unrealized_gain_loss == -10000.0  # (2600 - 2700) * 100
        assert not holding.is_profitable
        assert holding.is_loss
        assert "-" in holding.get_formatted_gain_loss()
    
    def test_holding_without_purchase_price(self):
        """購入価格なしの保有株式"""
        config = StockConfig(
            symbol="7203",
            name="トヨタ自動車",
            quantity=100
        )
        data = StockData(
            symbol="7203",
            current_price=2600.0,
            previous_close=2550.0,
            change=50.0,
            change_percent=1.96,
            volume=1000000,
            timestamp=datetime.now()
        )
        holding = StockHolding(config=config, data=data)
        
        assert holding.current_value == 260000.0
        assert holding.unrealized_gain_loss is None
        assert holding.get_formatted_gain_loss() == "N/A"
    
    def test_mismatched_symbols(self):
        """銘柄コードが一致しない場合"""
        config = StockConfig(symbol="7203", name="トヨタ", quantity=100)
        data = StockData(
            symbol="7201",  # 異なる銘柄コード
            current_price=2600.0,
            previous_close=2550.0,
            change=50.0,
            change_percent=1.96,
            volume=1000000,
            timestamp=datetime.now()
        )
        
        with pytest.raises(ValueError, match="設定と市場データの銘柄コードが一致しません"):
            StockHolding(config=config, data=data)


class TestPortfolio:
    """Portfolioクラスのテスト"""
    
    def test_empty_portfolio(self):
        """空のポートフォリオ"""
        portfolio = Portfolio()
        assert portfolio.stock_count == 0
        assert portfolio.total_value == 0.0
        assert portfolio.total_change == 0.0
    
    def test_portfolio_with_stocks(self):
        """株式を含むポートフォリオ"""
        # 株式1
        config1 = StockConfig("7203", "トヨタ", 100, 2500.0)
        data1 = StockData("7203", 2600.0, 2550.0, 50.0, 1.96, 1000000, datetime.now())
        holding1 = StockHolding(config1, data1)
        
        # 株式2
        config2 = StockConfig("AAPL", "Apple", 50, 150.0)
        data2 = StockData("AAPL", 155.0, 152.0, 3.0, 1.97, 500000, datetime.now())
        holding2 = StockHolding(config2, data2)
        
        portfolio = Portfolio()
        portfolio.add_stock(holding1)
        portfolio.add_stock(holding2)
        
        assert portfolio.stock_count == 2
        assert portfolio.total_value == 267750.0  # 260000 + 7750
        assert portfolio.profitable_stocks_count == 2
        assert portfolio.is_portfolio_profitable
    
    def test_portfolio_operations(self):
        """ポートフォリオの操作"""
        config = StockConfig("7203", "トヨタ", 100, 2500.0)
        data = StockData("7203", 2600.0, 2550.0, 50.0, 1.96, 1000000, datetime.now())
        holding = StockHolding(config, data)
        
        portfolio = Portfolio()
        
        # 追加
        portfolio.add_stock(holding)
        assert portfolio.stock_count == 1
        
        # 取得
        retrieved = portfolio.get_stock("7203")
        assert retrieved is not None
        assert retrieved.config.symbol == "7203"
        
        # 削除
        removed = portfolio.remove_stock("7203")
        assert removed
        assert portfolio.stock_count == 0
        assert portfolio.get_stock("7203") is None


class TestGoogleSheetsConfig:
    """GoogleSheetsConfigクラスのテスト"""
    
    def test_valid_config(self):
        """有効なGoogle Sheets設定"""
        config = GoogleSheetsConfig(
            spreadsheet_id="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
        )
        assert config.is_valid
        assert config.holdings_sheet_name == "保有銘柄"
        assert config.watchlist_sheet_name == "ウォッチリスト"
    
    def test_invalid_spreadsheet_id(self):
        """無効なスプレッドシートID"""
        with pytest.raises(ValueError, match="スプレッドシートIDが空です"):
            GoogleSheetsConfig(spreadsheet_id="")