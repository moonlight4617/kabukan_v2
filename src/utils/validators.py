"""
データ検証ユーティリティ
各種データクラスの検証機能を提供
"""

import re
import logging
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """バリデーションエラー"""
    pass


class StockValidator:
    """株式データの検証クラス"""
    
    # 日本株式コードの正規表現（4桁数字）
    JP_STOCK_CODE_PATTERN = re.compile(r'^\d{4}$')
    # 米国株式コードの正規表現（英数字1-5文字）
    US_STOCK_CODE_PATTERN = re.compile(r'^[A-Z]{1,5}$')
    
    @classmethod
    def validate_stock_symbol(cls, symbol: str) -> bool:
        """
        銘柄コードの妥当性をチェック
        
        Args:
            symbol: 銘柄コード
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効な銘柄コードの場合
        """
        if not symbol:
            raise ValidationError("銘柄コードが空です")
        
        symbol = symbol.upper().strip()
        
        # 日本株または米国株のパターンにマッチするかチェック
        if not (cls.JP_STOCK_CODE_PATTERN.match(symbol) or 
                cls.US_STOCK_CODE_PATTERN.match(symbol)):
            raise ValidationError(
                f"無効な銘柄コード形式: {symbol}。"
                "日本株は4桁数字、米国株は1-5文字の英字を使用してください。"
            )
        
        return True
    
    @classmethod
    def validate_stock_name(cls, name: str) -> bool:
        """
        銘柄名の妥当性をチェック
        
        Args:
            name: 銘柄名
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効な銘柄名の場合
        """
        if not name or not name.strip():
            raise ValidationError("銘柄名が空です")
        
        if len(name.strip()) < 2:
            raise ValidationError("銘柄名は2文字以上である必要があります")
        
        if len(name.strip()) > 100:
            raise ValidationError("銘柄名は100文字以内である必要があります")
        
        return True
    
    @classmethod
    def validate_quantity(cls, quantity: Union[int, float]) -> bool:
        """
        保有数量の妥当性をチェック
        
        Args:
            quantity: 保有数量
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効な数量の場合
        """
        if quantity is None:
            raise ValidationError("保有数量が設定されていません")
        
        try:
            quantity_int = int(quantity)
        except (ValueError, TypeError):
            raise ValidationError("保有数量は数値である必要があります")
        
        if quantity_int <= 0:
            raise ValidationError("保有数量は1以上である必要があります")
        
        if quantity_int > 1000000:
            raise ValidationError("保有数量は1,000,000以下である必要があります")
        
        return True
    
    @classmethod
    def validate_price(cls, price: Union[float, int], field_name: str = "価格") -> bool:
        """
        価格の妥当性をチェック
        
        Args:
            price: 価格
            field_name: フィールド名（エラーメッセージ用）
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効な価格の場合
        """
        if price is None:
            raise ValidationError(f"{field_name}が設定されていません")
        
        try:
            price_float = float(price)
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name}は数値である必要があります")
        
        if price_float <= 0:
            raise ValidationError(f"{field_name}は0より大きい値である必要があります")
        
        if price_float > 1000000:
            raise ValidationError(f"{field_name}は1,000,000以下である必要があります")
        
        return True
    
    @classmethod
    def validate_volume(cls, volume: Union[int, float]) -> bool:
        """
        出来高の妥当性をチェック
        
        Args:
            volume: 出来高
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効な出来高の場合
        """
        if volume is None:
            raise ValidationError("出来高が設定されていません")
        
        try:
            volume_int = int(volume)
        except (ValueError, TypeError):
            raise ValidationError("出来高は数値である必要があります")
        
        if volume_int < 0:
            raise ValidationError("出来高は0以上である必要があります")
        
        return True
    
    @classmethod
    def validate_timestamp(cls, timestamp: datetime, max_age_hours: int = 48) -> bool:
        """
        タイムスタンプの妥当性をチェック
        
        Args:
            timestamp: タイムスタンプ
            max_age_hours: 最大経過時間（時間）
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効なタイムスタンプの場合
        """
        if not isinstance(timestamp, datetime):
            raise ValidationError("タイムスタンプはdatetime型である必要があります")
        
        now = datetime.now()
        age = now - timestamp
        
        # 未来の時刻はエラー
        if age.total_seconds() < 0:
            raise ValidationError("タイムスタンプが未来の時刻です")
        
        # 古すぎるデータはエラー
        if age.total_seconds() > max_age_hours * 3600:
            raise ValidationError(
                f"データが古すぎます（{age.total_seconds()/3600:.1f}時間前）。"
                f"最大{max_age_hours}時間以内のデータを使用してください。"
            )
        
        return True


class ConfigValidator:
    """設定データの検証クラス"""
    
    @classmethod
    def validate_google_sheets_id(cls, sheets_id: str) -> bool:
        """
        Google Sheets IDの妥当性をチェック
        
        Args:
            sheets_id: Google Sheets ID
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効なIDの場合
        """
        if not sheets_id or not sheets_id.strip():
            raise ValidationError("Google Sheets IDが空です")
        
        # Google Sheets IDの基本的な形式チェック
        sheets_id = sheets_id.strip()
        if len(sheets_id) < 40 or len(sheets_id) > 50:
            raise ValidationError(
                "Google Sheets IDの長さが無効です。"
                "正しいスプレッドシートIDを確認してください。"
            )
        
        # 英数字、ハイフン、アンダースコアのみ許可
        if not re.match(r'^[a-zA-Z0-9_-]+$', sheets_id):
            raise ValidationError(
                "Google Sheets IDに無効な文字が含まれています。"
                "英数字、ハイフン、アンダースコアのみ使用可能です。"
            )
        
        return True
    
    @classmethod
    def validate_api_key(cls, api_key: str, service_name: str = "API") -> bool:
        """
        APIキーの妥当性をチェック
        
        Args:
            api_key: APIキー
            service_name: サービス名（エラーメッセージ用）
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効なAPIキーの場合
        """
        if not api_key or not api_key.strip():
            raise ValidationError(f"{service_name} APIキーが空です")
        
        api_key = api_key.strip()
        
        # 最小長チェック
        if len(api_key) < 10:
            raise ValidationError(f"{service_name} APIキーが短すぎます")
        
        # 最大長チェック
        if len(api_key) > 200:
            raise ValidationError(f"{service_name} APIキーが長すぎます")
        
        return True
    
    @classmethod
    def validate_webhook_url(cls, webhook_url: str) -> bool:
        """
        Webhook URLの妥当性をチェック
        
        Args:
            webhook_url: Webhook URL
            
        Returns:
            bool: 有効な場合True
            
        Raises:
            ValidationError: 無効なURLの場合
        """
        if not webhook_url or not webhook_url.strip():
            raise ValidationError("Webhook URLが空です")
        
        webhook_url = webhook_url.strip()
        
        # HTTPSチェック
        if not webhook_url.startswith("https://"):
            raise ValidationError("Webhook URLはHTTPSである必要があります")
        
        # Slack Webhook URLの基本的な形式チェック
        if "hooks.slack.com" in webhook_url:
            if not re.match(
                r'^https://hooks\.slack\.com/services/[A-Z0-9]+/[A-Z0-9]+/[a-zA-Z0-9]+$',
                webhook_url
            ):
                raise ValidationError(
                    "無効なSlack Webhook URL形式です。"
                    "正しいWebhook URLを確認してください。"
                )
        
        return True


class DataCollectionValidator:
    """データコレクションの検証クラス"""
    
    @classmethod
    def validate_stock_data_list(cls, stock_data_list: List[Dict[str, Any]]) -> List[str]:
        """
        株式データリストの一括検証
        
        Args:
            stock_data_list: 株式データのリスト
            
        Returns:
            List[str]: エラーメッセージのリスト（エラーがない場合は空リスト）
        """
        errors = []
        
        if not stock_data_list:
            errors.append("株式データが空です")
            return errors
        
        for i, stock_data in enumerate(stock_data_list):
            try:
                # 必須フィールドの存在チェック
                required_fields = ['symbol', 'current_price', 'previous_close', 'volume']
                for field in required_fields:
                    if field not in stock_data:
                        errors.append(f"データ{i+1}: {field}が不足しています")
                
                # 個別フィールドの検証
                if 'symbol' in stock_data:
                    try:
                        StockValidator.validate_stock_symbol(stock_data['symbol'])
                    except ValidationError as e:
                        errors.append(f"データ{i+1}: {str(e)}")
                
                if 'current_price' in stock_data:
                    try:
                        StockValidator.validate_price(stock_data['current_price'], "現在価格")
                    except ValidationError as e:
                        errors.append(f"データ{i+1}: {str(e)}")
                
                if 'previous_close' in stock_data:
                    try:
                        StockValidator.validate_price(stock_data['previous_close'], "前日終値")
                    except ValidationError as e:
                        errors.append(f"データ{i+1}: {str(e)}")
                
                if 'volume' in stock_data:
                    try:
                        StockValidator.validate_volume(stock_data['volume'])
                    except ValidationError as e:
                        errors.append(f"データ{i+1}: {str(e)}")
                        
            except Exception as e:
                errors.append(f"データ{i+1}: 予期しないエラー - {str(e)}")
        
        return errors
    
    @classmethod
    def validate_sheets_data(cls, holdings_data: List[List[str]], 
                           watchlist_data: List[List[str]]) -> List[str]:
        """
        Google Sheetsから取得したデータの検証
        
        Args:
            holdings_data: 保有銘柄データ
            watchlist_data: ウォッチリストデータ
            
        Returns:
            List[str]: エラーメッセージのリスト
        """
        errors = []
        
        # 保有銘柄データの検証
        if not holdings_data:
            errors.append("保有銘柄データが空です")
        else:
            for i, row in enumerate(holdings_data):
                if len(row) < 3:  # 最低限：銘柄コード、銘柄名、数量
                    errors.append(f"保有銘柄{i+1}: データが不足しています")
                    continue
                
                try:
                    StockValidator.validate_stock_symbol(row[0])
                except ValidationError as e:
                    errors.append(f"保有銘柄{i+1}: {str(e)}")
                
                try:
                    StockValidator.validate_stock_name(row[1])
                except ValidationError as e:
                    errors.append(f"保有銘柄{i+1}: {str(e)}")
                
                try:
                    StockValidator.validate_quantity(row[2])
                except ValidationError as e:
                    errors.append(f"保有銘柄{i+1}: {str(e)}")
                
                # 購入価格（オプション）
                if len(row) > 3 and row[3]:
                    try:
                        StockValidator.validate_price(row[3], "購入価格")
                    except ValidationError as e:
                        errors.append(f"保有銘柄{i+1}: {str(e)}")
        
        # ウォッチリストデータの検証
        if not watchlist_data:
            errors.append("ウォッチリストデータが空です")
        else:
            for i, row in enumerate(watchlist_data):
                if len(row) < 2:  # 最低限：銘柄コード、銘柄名
                    errors.append(f"ウォッチリスト{i+1}: データが不足しています")
                    continue
                
                try:
                    StockValidator.validate_stock_symbol(row[0])
                except ValidationError as e:
                    errors.append(f"ウォッチリスト{i+1}: {str(e)}")
                
                try:
                    StockValidator.validate_stock_name(row[1])
                except ValidationError as e:
                    errors.append(f"ウォッチリスト{i+1}: {str(e)}")
        
        return errors