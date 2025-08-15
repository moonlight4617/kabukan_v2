"""
株式分析システムのコアデータモデル
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
from enum import Enum
import logging

logger = logging.getLogger(__name__)


@dataclass
class StockConfig:
    """
    株式設定データクラス
    保有銘柄の基本情報を保持
    """
    symbol: str
    name: str
    quantity: int
    purchase_price: Optional[float] = None
    
    def __post_init__(self):
        """データ検証"""
        if not self.symbol:
            raise ValueError("銘柄コードが空です")
        if not self.name:
            raise ValueError("銘柄名が空です")
        if self.quantity <= 0:
            raise ValueError("保有数量は1以上である必要があります")
        if self.purchase_price is not None and self.purchase_price <= 0:
            raise ValueError("購入価格は0より大きい値である必要があります")
    
    @property
    def is_valid(self) -> bool:
        """設定の有効性をチェック"""
        try:
            self.__post_init__()
            return True
        except ValueError:
            return False


@dataclass
class WatchlistStock:
    """
    ウォッチリスト株式データクラス
    監視対象銘柄の情報を保持
    """
    symbol: str
    name: str
    
    def __post_init__(self):
        """データ検証"""
        if not self.symbol:
            raise ValueError("銘柄コードが空です")
        if not self.name:
            raise ValueError("銘柄名が空です")
    
    @property
    def is_valid(self) -> bool:
        """設定の有効性をチェック"""
        try:
            self.__post_init__()
            return True
        except ValueError:
            return False


@dataclass
class StockData:
    """
    株式データクラス
    市場から取得した株価データを保持
    """
    symbol: str
    current_price: float
    previous_close: float
    change: float
    change_percent: float
    volume: int
    timestamp: datetime
    # テクニカル分析用履歴データ
    price_history: Optional[List[float]] = field(default_factory=list)
    volume_history: Optional[List[int]] = field(default_factory=list)
    # 追加市場データ
    market_cap: Optional[float] = None
    pe_ratio: Optional[float] = None
    dividend_yield: Optional[float] = None
    
    def __post_init__(self):
        """データ検証"""
        if not self.symbol:
            raise ValueError("銘柄コードが空です")
        if self.current_price <= 0:
            raise ValueError("現在価格は0より大きい値である必要があります")
        if self.previous_close <= 0:
            raise ValueError("前日終値は0より大きい値である必要があります")
        if self.volume < 0:
            raise ValueError("出来高は0以上である必要があります")
        if not isinstance(self.timestamp, datetime):
            raise ValueError("タイムスタンプはdatetime型である必要があります")
    
    @property
    def is_valid(self) -> bool:
        """データの有効性をチェック"""
        try:
            self.__post_init__()
            return True
        except ValueError:
            return False
    
    @property
    def is_price_up(self) -> bool:
        """株価が上昇しているかチェック"""
        return self.change > 0
    
    @property
    def is_price_down(self) -> bool:
        """株価が下落しているかチェック"""
        return self.change < 0
    
    def get_formatted_change(self) -> str:
        """変動額と変動率をフォーマットした文字列を取得"""
        sign = "+" if self.change >= 0 else ""
        return f"{sign}{self.change:.2f} ({sign}{self.change_percent:.2f}%)"


@dataclass
class StockHolding:
    """
    保有株式データクラス
    設定と市場データを組み合わせた保有株式情報
    """
    config: StockConfig
    data: StockData
    current_value: float = 0.0
    unrealized_gain_loss: Optional[float] = None
    unrealized_gain_loss_percent: Optional[float] = None
    
    def __post_init__(self):
        """計算値を自動設定"""
        if self.config.symbol != self.data.symbol:
            raise ValueError("設定と市場データの銘柄コードが一致しません")
        
        # 現在価値を計算
        self.current_value = self.data.current_price * self.config.quantity
        
        # 含み損益を計算（購入価格が設定されている場合）
        if self.config.purchase_price is not None:
            purchase_value = self.config.purchase_price * self.config.quantity
            self.unrealized_gain_loss = self.current_value - purchase_value
            if purchase_value > 0:
                self.unrealized_gain_loss_percent = (self.unrealized_gain_loss / purchase_value) * 100
    
    @property
    def is_profitable(self) -> bool:
        """利益が出ているかチェック"""
        return self.unrealized_gain_loss is not None and self.unrealized_gain_loss > 0
    
    @property
    def is_loss(self) -> bool:
        """損失が出ているかチェック"""
        return self.unrealized_gain_loss is not None and self.unrealized_gain_loss < 0
    
    def get_formatted_gain_loss(self) -> str:
        """含み損益をフォーマットした文字列を取得"""
        if self.unrealized_gain_loss is None:
            return "N/A"
        
        sign = "+" if self.unrealized_gain_loss >= 0 else ""
        if self.unrealized_gain_loss_percent is not None:
            return f"{sign}{self.unrealized_gain_loss:.0f}円 ({sign}{self.unrealized_gain_loss_percent:.2f}%)"
        else:
            return f"{sign}{self.unrealized_gain_loss:.0f}円"


@dataclass
class Portfolio:
    """
    ポートフォリオデータクラス
    保有株式全体の情報を保持
    """
    stocks: List[StockHolding] = field(default_factory=list)
    total_value: float = 0.0
    total_change: float = 0.0
    total_change_percent: float = 0.0
    last_updated: datetime = field(default_factory=datetime.now)
    # ポートフォリオ統計
    total_unrealized_gain_loss: Optional[float] = None
    total_unrealized_gain_loss_percent: Optional[float] = None
    
    def __post_init__(self):
        """計算値を自動更新"""
        self.update_totals()
    
    def add_stock(self, holding: StockHolding) -> None:
        """保有株式を追加"""
        # 既存の銘柄かチェック
        for i, existing in enumerate(self.stocks):
            if existing.config.symbol == holding.config.symbol:
                # 既存銘柄を更新
                self.stocks[i] = holding
                self.update_totals()
                return
        
        # 新規追加
        self.stocks.append(holding)
        self.update_totals()
    
    def remove_stock(self, symbol: str) -> bool:
        """指定銘柄を削除"""
        for i, holding in enumerate(self.stocks):
            if holding.config.symbol == symbol:
                del self.stocks[i]
                self.update_totals()
                return True
        return False
    
    def get_stock(self, symbol: str) -> Optional[StockHolding]:
        """指定銘柄の保有情報を取得"""
        for holding in self.stocks:
            if holding.config.symbol == symbol:
                return holding
        return None
    
    def update_totals(self) -> None:
        """合計値を再計算"""
        if not self.stocks:
            self.total_value = 0.0
            self.total_change = 0.0
            self.total_change_percent = 0.0
            self.total_unrealized_gain_loss = None
            self.total_unrealized_gain_loss_percent = None
            return
        
        # 総価値
        self.total_value = sum(holding.current_value for holding in self.stocks)
        
        # 日次変動
        total_previous_value = sum(
            holding.data.previous_close * holding.config.quantity 
            for holding in self.stocks
        )
        self.total_change = self.total_value - total_previous_value
        if total_previous_value > 0:
            self.total_change_percent = (self.total_change / total_previous_value) * 100
        
        # 含み損益（購入価格が設定されている銘柄のみ）
        holdings_with_purchase_price = [
            holding for holding in self.stocks 
            if holding.unrealized_gain_loss is not None
        ]
        
        if holdings_with_purchase_price:
            self.total_unrealized_gain_loss = sum(
                holding.unrealized_gain_loss for holding in holdings_with_purchase_price
            )
            
            total_purchase_value = sum(
                holding.config.purchase_price * holding.config.quantity
                for holding in holdings_with_purchase_price
                if holding.config.purchase_price is not None
            )
            
            if total_purchase_value > 0:
                self.total_unrealized_gain_loss_percent = (
                    self.total_unrealized_gain_loss / total_purchase_value
                ) * 100
        
        self.last_updated = datetime.now()
    
    @property
    def stock_count(self) -> int:
        """保有銘柄数"""
        return len(self.stocks)
    
    @property
    def profitable_stocks_count(self) -> int:
        """利益銘柄数"""
        return sum(1 for holding in self.stocks if holding.is_profitable)
    
    @property
    def loss_stocks_count(self) -> int:
        """損失銘柄数"""
        return sum(1 for holding in self.stocks if holding.is_loss)
    
    @property
    def is_portfolio_profitable(self) -> bool:
        """ポートフォリオ全体が利益かチェック"""
        return (self.total_unrealized_gain_loss is not None and 
                self.total_unrealized_gain_loss > 0)
    
    def get_top_performers(self, limit: int = 5) -> List[StockHolding]:
        """パフォーマンス上位銘柄を取得"""
        return sorted(
            [h for h in self.stocks if h.unrealized_gain_loss_percent is not None],
            key=lambda h: h.unrealized_gain_loss_percent or 0,
            reverse=True
        )[:limit]
    
    def get_worst_performers(self, limit: int = 5) -> List[StockHolding]:
        """パフォーマンス下位銘柄を取得"""
        return sorted(
            [h for h in self.stocks if h.unrealized_gain_loss_percent is not None],
            key=lambda h: h.unrealized_gain_loss_percent or 0
        )[:limit]
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """ポートフォリオサマリーを取得"""
        return {
            "total_value": self.total_value,
            "total_change": self.total_change,
            "total_change_percent": self.total_change_percent,
            "stock_count": self.stock_count,
            "profitable_stocks": self.profitable_stocks_count,
            "loss_stocks": self.loss_stocks_count,
            "total_unrealized_gain_loss": self.total_unrealized_gain_loss,
            "total_unrealized_gain_loss_percent": self.total_unrealized_gain_loss_percent,
            "last_updated": self.last_updated.isoformat()
        }


@dataclass
class GoogleSheetsConfig:
    """
    Google Sheets設定データクラス
    """
    spreadsheet_id: str
    holdings_sheet_name: str = "保有銘柄"
    watchlist_sheet_name: str = "ウォッチリスト"
    credentials_json_path: str = "credentials.json"
    
    def __post_init__(self):
        """データ検証"""
        if not self.spreadsheet_id:
            raise ValueError("スプレッドシートIDが空です")
        if not self.holdings_sheet_name:
            raise ValueError("保有銘柄シート名が空です")
        if not self.watchlist_sheet_name:
            raise ValueError("ウォッチリストシート名が空です")
        if not self.credentials_json_path:
            raise ValueError("認証情報ファイルパスが空です")
    
    @property
    def is_valid(self) -> bool:
        """設定の有効性をチェック"""
        try:
            self.__post_init__()
            return True
        except ValueError:
            return False


