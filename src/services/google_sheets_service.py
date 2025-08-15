"""
Google Sheets統合サービス
保有銘柄とウォッチリストデータの取得機能を提供
"""

import os
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import re

try:
    from google.oauth2.service_account import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_API_AVAILABLE = True
except ImportError:
    GOOGLE_API_AVAILABLE = False

from src.models.data_models import StockConfig, WatchlistStock, GoogleSheetsConfig
from src.utils.validators import StockValidator, ValidationError


logger = logging.getLogger(__name__)


@dataclass
class SheetValidationResult:
    """シート検証結果"""
    is_valid: bool
    sheet_name: str
    expected_headers: List[str]
    actual_headers: List[str]
    errors: List[str]
    warnings: List[str]


@dataclass 
class DataExtractionResult:
    """データ抽出結果"""
    success: bool
    data: List[Any]
    errors: List[str]
    warnings: List[str]
    total_rows: int
    valid_rows: int


class GoogleSheetsService:
    """Google Sheets統合サービス"""
    
    # シート名の定義
    HOLDINGS_SHEET_NAME = "保有銘柄"
    WATCHLIST_SHEET_NAME = "ウォッチリスト"
    
    # 期待するヘッダー
    HOLDINGS_HEADERS = ["symbol", "name", "quantity", "purchase_price"]
    WATCHLIST_HEADERS = ["symbol", "name"]
    
    def __init__(self, config: GoogleSheetsConfig, credentials_json: Optional[Dict[str, Any]] = None):
        """
        Args:
            config: Google Sheets設定
            credentials_json: 認証情報JSON（Parameter Storeから取得）
        """
        self.config = config
        self.credentials_json = credentials_json
        self.logger = logging.getLogger(__name__)
        self._service = None
        
        # Google API可用性チェック
        if not GOOGLE_API_AVAILABLE:
            self.logger.warning("Google APIライブラリがインストールされていません。")
            return
        
        try:
            self._initialize_service()
        except Exception as e:
            self.logger.error(f"Google Sheets サービス初期化に失敗: {e}")
    
    def _initialize_service(self):
        """Google Sheets サービスを初期化"""
        if not GOOGLE_API_AVAILABLE:
            raise RuntimeError("Google APIライブラリが利用できません")
        
        try:
            # 認証情報の取得
            credentials = self._get_credentials()
            
            # Google Sheets API サービス構築
            self._service = build('sheets', 'v4', credentials=credentials)
            
            self.logger.info("Google Sheets サービス初期化完了")
            
        except Exception as e:
            self.logger.error(f"Google Sheets サービス初期化エラー: {e}")
            raise
    
    def _get_credentials(self) -> Credentials:
        """認証情報を取得"""
        scopes = ['https://www.googleapis.com/auth/spreadsheets.readonly']
        
        if self.credentials_json:
            # Parameter Storeから取得したJSON認証情報を使用
            return Credentials.from_service_account_info(self.credentials_json, scopes=scopes)
        
        elif self.config.credentials_json_path and os.path.exists(self.config.credentials_json_path):
            # ローカルファイルから認証情報を読み込み
            return Credentials.from_service_account_file(self.config.credentials_json_path, scopes=scopes)
        
        else:
            raise ValueError(
                "Google Sheets認証情報が設定されていません。"
                "credentials_json_pathまたはcredentials_jsonを設定してください。"
            )
    
    @property
    def is_available(self) -> bool:
        """Google Sheetsサービスが利用可能かチェック"""
        return GOOGLE_API_AVAILABLE and self._service is not None
    
    def validate_sheet_structure(self, sheet_name: str) -> SheetValidationResult:
        """
        シート構造の検証
        
        Args:
            sheet_name: シート名
            
        Returns:
            SheetValidationResult: 検証結果
        """
        if not self.is_available:
            return SheetValidationResult(
                is_valid=False,
                sheet_name=sheet_name,
                expected_headers=[],
                actual_headers=[],
                errors=["Google Sheetsサービスが利用できません"],
                warnings=[]
            )
        
        try:
            # 期待するヘッダーを取得
            expected_headers = self._get_expected_headers(sheet_name)
            if not expected_headers:
                return SheetValidationResult(
                    is_valid=False,
                    sheet_name=sheet_name,
                    expected_headers=[],
                    actual_headers=[],
                    errors=[f"未対応のシート名: {sheet_name}"],
                    warnings=[]
                )
            
            # シートからヘッダー行を取得
            range_name = f"{sheet_name}!1:1"
            result = self._service.spreadsheets().values().get(
                spreadsheetId=self.config.spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            actual_headers = values[0] if values else []
            
            # ヘッダーの正規化（小文字化、空白除去）
            actual_headers_normalized = [
                header.strip().lower() for header in actual_headers if header.strip()
            ]
            expected_headers_normalized = [header.lower() for header in expected_headers]
            
            # 検証
            errors = []
            warnings = []
            
            # 必須ヘッダーの存在チェック
            missing_headers = set(expected_headers_normalized) - set(actual_headers_normalized)
            if missing_headers:
                errors.append(f"必須ヘッダーが不足: {', '.join(missing_headers)}")
            
            # 余分なヘッダーの警告
            extra_headers = set(actual_headers_normalized) - set(expected_headers_normalized)
            if extra_headers:
                warnings.append(f"余分なヘッダー: {', '.join(extra_headers)}")
            
            # 空のヘッダーチェック
            empty_headers = [i for i, header in enumerate(actual_headers) if not header.strip()]
            if empty_headers:
                warnings.append(f"空のヘッダーセル: {', '.join(f'列{i+1}' for i in empty_headers)}")
            
            is_valid = len(errors) == 0
            
            return SheetValidationResult(
                is_valid=is_valid,
                sheet_name=sheet_name,
                expected_headers=expected_headers,
                actual_headers=actual_headers,
                errors=errors,
                warnings=warnings
            )
            
        except HttpError as e:
            error_details = e.error_details[0] if e.error_details else {}
            error_reason = error_details.get('reason', 'Unknown')
            
            if error_reason == 'notFound':
                errors = [f"スプレッドシートまたはシート '{sheet_name}' が見つかりません"]
            elif error_reason == 'forbidden':
                errors = [f"スプレッドシートへのアクセス権限がありません"]
            else:
                errors = [f"Google Sheets APIエラー: {e}"]
            
            return SheetValidationResult(
                is_valid=False,
                sheet_name=sheet_name,
                expected_headers=expected_headers,
                actual_headers=[],
                errors=errors,
                warnings=[]
            )
        
        except Exception as e:
            return SheetValidationResult(
                is_valid=False,
                sheet_name=sheet_name,
                expected_headers=expected_headers,
                actual_headers=[],
                errors=[f"予期しないエラー: {e}"],
                warnings=[]
            )
    
    def _get_expected_headers(self, sheet_name: str) -> List[str]:
        """シート名に応じた期待ヘッダーを取得"""
        if sheet_name == self.HOLDINGS_SHEET_NAME:
            return self.HOLDINGS_HEADERS.copy()
        elif sheet_name == self.WATCHLIST_SHEET_NAME:
            return self.WATCHLIST_HEADERS.copy()
        else:
            return []
    
    def get_holdings_data(self) -> DataExtractionResult:
        """
        保有銘柄データを取得
        
        Returns:
            DataExtractionResult: 抽出結果とStockConfigのリスト
        """
        if not self.is_available:
            return DataExtractionResult(
                success=False,
                data=[],
                errors=["Google Sheetsサービスが利用できません"],
                warnings=[],
                total_rows=0,
                valid_rows=0
            )
        
        try:
            # シート構造検証
            validation_result = self.validate_sheet_structure(self.HOLDINGS_SHEET_NAME)
            warnings = validation_result.warnings.copy()
            
            if not validation_result.is_valid:
                return DataExtractionResult(
                    success=False,
                    data=[],
                    errors=validation_result.errors,
                    warnings=warnings,
                    total_rows=0,
                    valid_rows=0
                )
            
            # データ範囲を取得（ヘッダー行以降）
            range_name = f"{self.HOLDINGS_SHEET_NAME}!A2:Z"
            result = self._service.spreadsheets().values().get(
                spreadsheetId=self.config.spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            total_rows = len(values)
            
            if total_rows == 0:
                warnings.append("保有銘柄データが空です")
                return DataExtractionResult(
                    success=True,
                    data=[],
                    errors=[],
                    warnings=warnings,
                    total_rows=0,
                    valid_rows=0
                )
            
            # データの解析と検証
            holdings = []
            errors = []
            valid_rows = 0
            
            # ヘッダーマッピングを作成
            header_mapping = self._create_header_mapping(
                validation_result.actual_headers,
                self.HOLDINGS_HEADERS
            )
            
            for row_idx, row in enumerate(values, start=2):  # 2行目から開始
                try:
                    # 空行をスキップ
                    if not any(cell.strip() for cell in row if cell):
                        continue
                    
                    # データを抽出
                    stock_data = self._extract_holdings_row_data(row, header_mapping, row_idx)
                    
                    if stock_data:
                        holdings.append(stock_data)
                        valid_rows += 1
                    
                except Exception as e:
                    errors.append(f"行{row_idx}: {str(e)}")
            
            success = len(errors) == 0 or valid_rows > 0
            
            return DataExtractionResult(
                success=success,
                data=holdings,
                errors=errors,
                warnings=warnings,
                total_rows=total_rows,
                valid_rows=valid_rows
            )
            
        except Exception as e:
            self.logger.error(f"保有銘柄データ取得エラー: {e}")
            return DataExtractionResult(
                success=False,
                data=[],
                errors=[f"データ取得に失敗: {e}"],
                warnings=[],
                total_rows=0,
                valid_rows=0
            )
    
    def get_watchlist_data(self) -> DataExtractionResult:
        """
        ウォッチリストデータを取得
        
        Returns:
            DataExtractionResult: 抽出結果とWatchlistStockのリスト
        """
        if not self.is_available:
            return DataExtractionResult(
                success=False,
                data=[],
                errors=["Google Sheetsサービスが利用できません"],
                warnings=[],
                total_rows=0,
                valid_rows=0
            )
        
        try:
            # シート構造検証
            validation_result = self.validate_sheet_structure(self.WATCHLIST_SHEET_NAME)
            warnings = validation_result.warnings.copy()
            
            if not validation_result.is_valid:
                return DataExtractionResult(
                    success=False,
                    data=[],
                    errors=validation_result.errors,
                    warnings=warnings,
                    total_rows=0,
                    valid_rows=0
                )
            
            # データ範囲を取得
            range_name = f"{self.WATCHLIST_SHEET_NAME}!A2:Z"
            result = self._service.spreadsheets().values().get(
                spreadsheetId=self.config.spreadsheet_id,
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            total_rows = len(values)
            
            if total_rows == 0:
                warnings.append("ウォッチリストデータが空です")
                return DataExtractionResult(
                    success=True,
                    data=[],
                    errors=[],
                    warnings=warnings,
                    total_rows=0,
                    valid_rows=0
                )
            
            # データの解析と検証
            watchlist = []
            errors = []
            valid_rows = 0
            
            # ヘッダーマッピングを作成
            header_mapping = self._create_header_mapping(
                validation_result.actual_headers,
                self.WATCHLIST_HEADERS
            )
            
            for row_idx, row in enumerate(values, start=2):
                try:
                    # 空行をスキップ
                    if not any(cell.strip() for cell in row if cell):
                        continue
                    
                    # データを抽出
                    stock_data = self._extract_watchlist_row_data(row, header_mapping, row_idx)
                    
                    if stock_data:
                        watchlist.append(stock_data)
                        valid_rows += 1
                    
                except Exception as e:
                    errors.append(f"行{row_idx}: {str(e)}")
            
            success = len(errors) == 0 or valid_rows > 0
            
            return DataExtractionResult(
                success=success,
                data=watchlist,
                errors=errors,
                warnings=warnings,
                total_rows=total_rows,
                valid_rows=valid_rows
            )
            
        except Exception as e:
            self.logger.error(f"ウォッチリストデータ取得エラー: {e}")
            return DataExtractionResult(
                success=False,
                data=[],
                errors=[f"データ取得に失敗: {e}"],
                warnings=[],
                total_rows=0,
                valid_rows=0
            )
    
    def _create_header_mapping(self, actual_headers: List[str], expected_headers: List[str]) -> Dict[str, int]:
        """ヘッダーマッピングを作成"""
        mapping = {}
        actual_headers_normalized = [header.strip().lower() for header in actual_headers]
        
        for expected_header in expected_headers:
            expected_normalized = expected_header.lower()
            if expected_normalized in actual_headers_normalized:
                mapping[expected_header] = actual_headers_normalized.index(expected_normalized)
        
        return mapping
    
    def _extract_holdings_row_data(self, row: List[str], header_mapping: Dict[str, int], row_idx: int) -> Optional[StockConfig]:
        """保有銘柄行データを抽出"""
        try:
            # 必要なデータを抽出
            symbol_idx = header_mapping.get("symbol")
            name_idx = header_mapping.get("name")
            quantity_idx = header_mapping.get("quantity")
            purchase_price_idx = header_mapping.get("purchase_price")
            
            # 必須フィールドの存在確認
            if any(idx is None for idx in [symbol_idx, name_idx, quantity_idx, purchase_price_idx]):
                raise ValueError("必須フィールドのマッピングが不完全です")
            
            # データ取得（範囲外アクセス防止）
            symbol = row[symbol_idx].strip() if symbol_idx < len(row) else ""
            name = row[name_idx].strip() if name_idx < len(row) else ""
            quantity_str = row[quantity_idx].strip() if quantity_idx < len(row) else ""
            purchase_price_str = row[purchase_price_idx].strip() if purchase_price_idx < len(row) else ""
            
            # 空データのチェック
            if not all([symbol, name, quantity_str, purchase_price_str]):
                raise ValueError("必須フィールドが空です")
            
            # データ型変換と検証
            try:
                quantity = float(quantity_str)
                purchase_price = float(purchase_price_str)
            except ValueError:
                raise ValueError("数量または購入価格が数値ではありません")
            
            # ビジネスロジック検証
            if quantity <= 0:
                raise ValueError("数量は正の値である必要があります")
            
            if purchase_price <= 0:
                raise ValueError("購入価格は正の値である必要があります")
            
            # 銘柄コードの検証
            try:
                StockValidator.validate_stock_symbol(symbol)
            except ValidationError as e:
                raise ValueError(f"銘柄コード不正: {str(e)}")
            
            # StockConfigオブジェクトを作成
            return StockConfig(
                symbol=symbol,
                name=name,
                quantity=quantity,
                purchase_price=purchase_price
            )
            
        except Exception as e:
            raise ValueError(f"データ抽出エラー: {str(e)}")
    
    def _extract_watchlist_row_data(self, row: List[str], header_mapping: Dict[str, int], row_idx: int) -> Optional[WatchlistStock]:
        """ウォッチリスト行データを抽出"""
        try:
            # 必要なデータを抽出
            symbol_idx = header_mapping.get("symbol")
            name_idx = header_mapping.get("name")
            
            # 必須フィールドの存在確認
            if symbol_idx is None or name_idx is None:
                raise ValueError("必須フィールドのマッピングが不完全です")
            
            # データ取得
            symbol = row[symbol_idx].strip() if symbol_idx < len(row) else ""
            name = row[name_idx].strip() if name_idx < len(row) else ""
            
            # 空データのチェック
            if not all([symbol, name]):
                raise ValueError("必須フィールドが空です")
            
            # 銘柄コードの検証
            try:
                StockValidator.validate_stock_symbol(symbol)
            except ValidationError as e:
                raise ValueError(f"銘柄コード不正: {str(e)}")
            
            # WatchlistStockオブジェクトを作成
            return WatchlistStock(
                symbol=symbol,
                name=name
            )
            
        except Exception as e:
            raise ValueError(f"データ抽出エラー: {str(e)}")
    
    def validate_connection(self) -> bool:
        """Google Sheetsへの接続を検証"""
        if not self.is_available:
            return False
        
        try:
            # スプレッドシートのメタデータを取得してアクセス可能性を確認
            self._service.spreadsheets().get(
                spreadsheetId=self.config.spreadsheet_id
            ).execute()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Google Sheets接続検証に失敗: {e}")
            return False
    
    def get_spreadsheet_info(self) -> Dict[str, Any]:
        """スプレッドシート情報を取得"""
        if not self.is_available:
            return {"error": "Google Sheetsサービスが利用できません"}
        
        try:
            response = self._service.spreadsheets().get(
                spreadsheetId=self.config.spreadsheet_id
            ).execute()
            
            sheet_names = [sheet['properties']['title'] for sheet in response.get('sheets', [])]
            
            return {
                "title": response.get("properties", {}).get("title", "Unknown"),
                "sheet_names": sheet_names,
                "url": f"https://docs.google.com/spreadsheets/d/{self.config.spreadsheet_id}",
                "has_holdings_sheet": self.HOLDINGS_SHEET_NAME in sheet_names,
                "has_watchlist_sheet": self.WATCHLIST_SHEET_NAME in sheet_names
            }
            
        except Exception as e:
            self.logger.error(f"スプレッドシート情報取得エラー: {e}")
            return {"error": str(e)}
    
    def get_service_status(self) -> Dict[str, Any]:
        """サービス状況を取得"""
        return {
            "available": self.is_available,
            "google_api_installed": GOOGLE_API_AVAILABLE,
            "spreadsheet_id": self.config.spreadsheet_id,
            "credentials_source": "parameter_store" if self.credentials_json else "local_file",
            "connection_valid": self.validate_connection() if self.is_available else False
        }