"""
Google Sheets統合サービスのテスト
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from googleapiclient.errors import HttpError

from src.services.google_sheets_service import (
    GoogleSheetsService,
    SheetValidationResult,
    DataExtractionResult
)
from src.models.data_models import GoogleSheetsConfig, StockConfig, WatchlistStock


class TestGoogleSheetsService:
    """GoogleSheetsServiceクラスのテスト"""
    
    def setup_method(self):
        """テスト用セットアップ"""
        self.config = GoogleSheetsConfig(
            spreadsheet_id="test_spreadsheet_id",
            credentials_json_path="test_credentials.json"
        )
        
        self.mock_credentials_json = {
            "type": "service_account",
            "project_id": "test-project",
            "private_key_id": "key-id",
            "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
            "client_email": "test@test-project.iam.gserviceaccount.com",
            "client_id": "123456789",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token"
        }
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_initialization_success_with_json(self, mock_credentials, mock_build):
        """JSON認証情報での正常な初期化"""
        mock_creds = Mock()
        mock_credentials.from_service_account_info.return_value = mock_creds
        
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        
        assert service.is_available
        mock_credentials.from_service_account_info.assert_called_once()
        mock_build.assert_called_once_with('sheets', 'v4', credentials=mock_creds)
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    @patch('src.services.google_sheets_service.os.path.exists')
    def test_initialization_success_with_file(self, mock_exists, mock_credentials, mock_build):
        """ファイル認証情報での正常な初期化"""
        mock_exists.return_value = True
        mock_creds = Mock()
        mock_credentials.from_service_account_file.return_value = mock_creds
        
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        service = GoogleSheetsService(self.config)
        
        assert service.is_available
        mock_credentials.from_service_account_file.assert_called_once()
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.os.path.exists')
    def test_initialization_no_credentials(self, mock_exists):
        """認証情報なしの初期化"""
        mock_exists.return_value = False
        
        with pytest.raises(ValueError, match="Google Sheets認証情報が設定されていません"):
            GoogleSheetsService(self.config)
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', False)
    def test_initialization_no_google_api(self):
        """Google APIライブラリなしの初期化"""
        service = GoogleSheetsService(self.config)
        assert not service.is_available
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_validate_sheet_structure_success(self, mock_credentials, mock_build):
        """シート構造検証成功"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        
        # 正しいヘッダーを返すモック
        mock_service.spreadsheets().values().get().execute.return_value = {
            'values': [['symbol', 'name', 'quantity', 'purchase_price']]
        }
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        result = service.validate_sheet_structure("保有銘柄")
        
        assert result.is_valid
        assert result.sheet_name == "保有銘柄"
        assert len(result.errors) == 0
        assert result.expected_headers == ['symbol', 'name', 'quantity', 'purchase_price']
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_validate_sheet_structure_missing_headers(self, mock_credentials, mock_build):
        """シート構造検証：ヘッダー不足"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        
        # 不完全なヘッダーを返すモック
        mock_service.spreadsheets().values().get().execute.return_value = {
            'values': [['symbol', 'name']]  # quantity, purchase_priceが不足
        }
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        result = service.validate_sheet_structure("保有銘柄")
        
        assert not result.is_valid
        assert len(result.errors) > 0
        assert any("必須ヘッダーが不足" in error for error in result.errors)
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_validate_sheet_structure_http_error(self, mock_credentials, mock_build):
        """シート構造検証：HTTPエラー"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        
        # HTTPエラーを発生させるモック
        error_response = Mock()
        error_response.error_details = [{'reason': 'notFound'}]
        mock_service.spreadsheets().values().get().execute.side_effect = HttpError(
            resp=Mock(status=404), content=b'Not Found'
        )
        mock_service.spreadsheets().values().get().execute.side_effect.error_details = [{'reason': 'notFound'}]
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        result = service.validate_sheet_structure("保有銘柄")
        
        assert not result.is_valid
        assert len(result.errors) > 0
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_get_holdings_data_success(self, mock_credentials, mock_build):
        """保有銘柄データ取得成功"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        
        # ヘッダー行
        mock_service.spreadsheets().values().get.side_effect = [
            # ヘッダー検証用の呼び出し
            Mock(execute=Mock(return_value={'values': [['symbol', 'name', 'quantity', 'purchase_price']]})),
            # データ取得用の呼び出し
            Mock(execute=Mock(return_value={
                'values': [
                    ['7203', 'トヨタ自動車', '100', '2500.0'],
                    ['AAPL', 'Apple Inc.', '50', '150.0']
                ]
            }))
        ]
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        result = service.get_holdings_data()
        
        assert result.success
        assert len(result.data) == 2
        assert result.valid_rows == 2
        assert result.total_rows == 2
        assert len(result.errors) == 0
        
        # データの検証
        stock1 = result.data[0]
        assert isinstance(stock1, StockConfig)
        assert stock1.symbol == '7203'
        assert stock1.name == 'トヨタ自動車'
        assert stock1.quantity == 100
        assert stock1.purchase_price == 2500.0
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_get_holdings_data_validation_errors(self, mock_credentials, mock_build):
        """保有銘柄データ取得：検証エラー"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        
        mock_service.spreadsheets().values().get.side_effect = [
            # ヘッダー検証
            Mock(execute=Mock(return_value={'values': [['symbol', 'name', 'quantity', 'purchase_price']]})),
            # 不正なデータ
            Mock(execute=Mock(return_value={
                'values': [
                    ['7203', 'トヨタ自動車', '100', '2500.0'],  # 正常
                    ['INVALID', '', '-50', 'not_a_number'],     # 複数エラー
                    ['AAPL', 'Apple', '25', '150.0']            # 正常
                ]
            }))
        ]
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        result = service.get_holdings_data()
        
        assert result.success  # 一部成功があるのでTrue
        assert len(result.data) == 2  # 正常な2行のみ
        assert result.valid_rows == 2
        assert result.total_rows == 3
        assert len(result.errors) == 1  # 1行でエラー
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_get_watchlist_data_success(self, mock_credentials, mock_build):
        """ウォッチリストデータ取得成功"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        
        mock_service.spreadsheets().values().get.side_effect = [
            # ヘッダー検証
            Mock(execute=Mock(return_value={'values': [['symbol', 'name']]})),
            # データ取得
            Mock(execute=Mock(return_value={
                'values': [
                    ['MSFT', 'Microsoft Corporation'],
                    ['6758', 'ソニーグループ']
                ]
            }))
        ]
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        result = service.get_watchlist_data()
        
        assert result.success
        assert len(result.data) == 2
        assert result.valid_rows == 2
        assert len(result.errors) == 0
        
        # データの検証
        stock1 = result.data[0]
        assert isinstance(stock1, WatchlistStock)
        assert stock1.symbol == 'MSFT'
        assert stock1.name == 'Microsoft Corporation'
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_get_watchlist_data_empty(self, mock_credentials, mock_build):
        """ウォッチリストデータ取得：空データ"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        
        mock_service.spreadsheets().values().get.side_effect = [
            # ヘッダー検証
            Mock(execute=Mock(return_value={'values': [['symbol', 'name']]})),
            # 空のデータ
            Mock(execute=Mock(return_value={'values': []}))
        ]
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        result = service.get_watchlist_data()
        
        assert result.success
        assert len(result.data) == 0
        assert result.valid_rows == 0
        assert result.total_rows == 0
        assert len(result.warnings) > 0
        assert any("ウォッチリストデータが空" in warning for warning in result.warnings)
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_validate_connection_success(self, mock_credentials, mock_build):
        """接続検証成功"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        mock_service.spreadsheets().get().execute.return_value = {"properties": {"title": "Test Sheet"}}
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        result = service.validate_connection()
        
        assert result is True
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_validate_connection_failure(self, mock_credentials, mock_build):
        """接続検証失敗"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        mock_service.spreadsheets().get().execute.side_effect = Exception("Connection failed")
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        result = service.validate_connection()
        
        assert result is False
    
    @patch('src.services.google_sheets_service.GOOGLE_API_AVAILABLE', True)
    @patch('src.services.google_sheets_service.build')
    @patch('src.services.google_sheets_service.Credentials')
    def test_get_spreadsheet_info(self, mock_credentials, mock_build):
        """スプレッドシート情報取得"""
        mock_service = self._setup_mock_service(mock_credentials, mock_build)
        mock_service.spreadsheets().get().execute.return_value = {
            "properties": {"title": "投資管理シート"},
            "sheets": [
                {"properties": {"title": "保有銘柄"}},
                {"properties": {"title": "ウォッチリスト"}},
                {"properties": {"title": "その他"}}
            ]
        }
        
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        info = service.get_spreadsheet_info()
        
        assert info["title"] == "投資管理シート"
        assert "保有銘柄" in info["sheet_names"]
        assert "ウォッチリスト" in info["sheet_names"]
        assert info["has_holdings_sheet"] is True
        assert info["has_watchlist_sheet"] is True
        assert "url" in info
    
    def test_service_not_available(self):
        """サービス利用不可時の動作"""
        service = GoogleSheetsService(self.config)
        service._service = None
        
        # シート検証
        validation_result = service.validate_sheet_structure("保有銘柄")
        assert not validation_result.is_valid
        assert "サービスが利用できません" in validation_result.errors[0]
        
        # 保有銘柄データ取得
        holdings_result = service.get_holdings_data()
        assert not holdings_result.success
        assert "サービスが利用できません" in holdings_result.errors[0]
        
        # ウォッチリストデータ取得
        watchlist_result = service.get_watchlist_data()
        assert not watchlist_result.success
        assert "サービスが利用できません" in watchlist_result.errors[0]
        
        # 接続検証
        connection_result = service.validate_connection()
        assert connection_result is False
    
    def test_get_service_status(self):
        """サービス状況取得"""
        service = GoogleSheetsService(self.config, self.mock_credentials_json)
        status = service.get_service_status()
        
        assert "available" in status
        assert "google_api_installed" in status
        assert "spreadsheet_id" in status
        assert "credentials_source" in status
        assert "connection_valid" in status
        assert status["spreadsheet_id"] == "test_spreadsheet_id"
        assert status["credentials_source"] == "parameter_store"
    
    def test_header_mapping_creation(self):
        """ヘッダーマッピング作成のテスト"""
        service = GoogleSheetsService(self.config)
        
        actual_headers = ["Symbol", "Name", "Quantity", "Purchase_Price", "Extra"]
        expected_headers = ["symbol", "name", "quantity", "purchase_price"]
        
        mapping = service._create_header_mapping(actual_headers, expected_headers)
        
        assert mapping["symbol"] == 0
        assert mapping["name"] == 1
        assert mapping["quantity"] == 2
        assert mapping["purchase_price"] == 3
        assert "extra" not in mapping
    
    def test_extract_holdings_row_data_success(self):
        """保有銘柄行データ抽出成功"""
        service = GoogleSheetsService(self.config)
        
        row = ["7203", "トヨタ自動車", "100", "2500.0"]
        header_mapping = {"symbol": 0, "name": 1, "quantity": 2, "purchase_price": 3}
        
        result = service._extract_holdings_row_data(row, header_mapping, 2)
        
        assert isinstance(result, StockConfig)
        assert result.symbol == "7203"
        assert result.name == "トヨタ自動車"
        assert result.quantity == 100
        assert result.purchase_price == 2500.0
    
    def test_extract_holdings_row_data_validation_errors(self):
        """保有銘柄行データ抽出：検証エラー"""
        service = GoogleSheetsService(self.config)
        header_mapping = {"symbol": 0, "name": 1, "quantity": 2, "purchase_price": 3}
        
        # 空のフィールド
        with pytest.raises(ValueError, match="必須フィールドが空"):
            service._extract_holdings_row_data(["", "name", "100", "2500"], header_mapping, 2)
        
        # 無効な数量
        with pytest.raises(ValueError, match="数量または購入価格が数値ではありません"):
            service._extract_holdings_row_data(["7203", "name", "invalid", "2500"], header_mapping, 2)
        
        # 負の数量
        with pytest.raises(ValueError, match="数量は正の値である必要があります"):
            service._extract_holdings_row_data(["7203", "name", "-100", "2500"], header_mapping, 2)
        
        # 無効な銘柄コード
        with pytest.raises(ValueError, match="銘柄コード不正"):
            service._extract_holdings_row_data(["", "name", "100", "2500"], header_mapping, 2)
    
    def test_extract_watchlist_row_data_success(self):
        """ウォッチリスト行データ抽出成功"""
        service = GoogleSheetsService(self.config)
        
        row = ["AAPL", "Apple Inc."]
        header_mapping = {"symbol": 0, "name": 1}
        
        result = service._extract_watchlist_row_data(row, header_mapping, 2)
        
        assert isinstance(result, WatchlistStock)
        assert result.symbol == "AAPL"
        assert result.name == "Apple Inc."
    
    def test_extract_watchlist_row_data_validation_errors(self):
        """ウォッチリスト行データ抽出：検証エラー"""
        service = GoogleSheetsService(self.config)
        header_mapping = {"symbol": 0, "name": 1}
        
        # 空のフィールド
        with pytest.raises(ValueError, match="必須フィールドが空"):
            service._extract_watchlist_row_data(["", "name"], header_mapping, 2)
        
        # 無効な銘柄コード
        with pytest.raises(ValueError, match="銘柄コード不正"):
            service._extract_watchlist_row_data(["", "Apple"], header_mapping, 2)
    
    def _setup_mock_service(self, mock_credentials, mock_build):
        """モックサービスのセットアップ"""
        mock_creds = Mock()
        mock_credentials.from_service_account_info.return_value = mock_creds
        
        mock_service = Mock()
        mock_build.return_value = mock_service
        
        return mock_service


class TestSheetValidationResult:
    """SheetValidationResultクラスのテスト"""
    
    def test_validation_result_creation(self):
        """検証結果の作成"""
        result = SheetValidationResult(
            is_valid=True,
            sheet_name="保有銘柄",
            expected_headers=["symbol", "name"],
            actual_headers=["Symbol", "Name"],
            errors=[],
            warnings=["余分なヘッダー: extra"]
        )
        
        assert result.is_valid
        assert result.sheet_name == "保有銘柄"
        assert len(result.expected_headers) == 2
        assert len(result.warnings) == 1


class TestDataExtractionResult:
    """DataExtractionResultクラスのテスト"""
    
    def test_extraction_result_creation(self):
        """抽出結果の作成"""
        mock_data = [
            StockConfig("7203", "トヨタ", 100, 2500.0),
            StockConfig("AAPL", "Apple", 50, 150.0)
        ]
        
        result = DataExtractionResult(
            success=True,
            data=mock_data,
            errors=[],
            warnings=["警告メッセージ"],
            total_rows=2,
            valid_rows=2
        )
        
        assert result.success
        assert len(result.data) == 2
        assert result.total_rows == 2
        assert result.valid_rows == 2
        assert len(result.warnings) == 1