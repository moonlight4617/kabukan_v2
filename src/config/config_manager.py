"""
設定管理クラス
ローカル環境とAWS環境の両方に対応した設定読み込み機能
"""

import os
import json
import logging
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path

try:
    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    AWS_AVAILABLE = True
except ImportError:
    AWS_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class StockConfig:
    """株式設定"""
    symbol: str
    name: str
    quantity: int
    purchase_price: Optional[float] = None


@dataclass
class WatchlistStock:
    """ウォッチリスト株式"""
    symbol: str
    name: str


@dataclass
class GoogleSheetsConfig:
    """Google Sheets設定"""
    spreadsheet_id: str
    holdings_sheet_name: str = "保有銘柄"
    watchlist_sheet_name: str = "ウォッチリスト"
    credentials_json_path: str = "credentials.json"


@dataclass
class GeminiConfig:
    """Gemini AI設定"""
    api_key: str
    model: str = "gemini-pro"
    max_tokens: int = 1000
    temperature: float = 0.7


@dataclass
class SlackConfig:
    """Slack設定"""
    webhook_url: str
    channel: str = "#stock-analysis"
    username: str = "Stock Analysis Bot"


@dataclass
class AppConfig:
    """アプリケーション設定"""
    environment: str
    log_level: str
    google_sheets: GoogleSheetsConfig
    gemini: GeminiConfig
    slack: SlackConfig
    stocks: List[StockConfig] = field(default_factory=list)
    watchlist: List[WatchlistStock] = field(default_factory=list)
    aws_region: str = "ap-northeast-1"
    test_mode: bool = False
    mock_external_apis: bool = False


class ConfigManager:
    """設定管理クラス"""
    
    def __init__(self):
        self.environment = os.getenv("ENVIRONMENT", "local")
        self.logger = logging.getLogger(__name__)
        self._config: Optional[AppConfig] = None
        self._parameter_store_client = None
        
        if AWS_AVAILABLE and self.environment == "aws":
            try:
                self._parameter_store_client = boto3.client("ssm")
            except Exception as e:
                self.logger.warning(f"AWS SSM client初期化に失敗: {e}")
    
    def get_config(self) -> AppConfig:
        """設定を取得"""
        if self._config is None:
            self._config = self._load_config()
        return self._config
    
    def _load_config(self) -> AppConfig:
        """環境に応じて設定を読み込み"""
        self.logger.info(f"環境 '{self.environment}' の設定を読み込み中...")
        
        if self.environment == "aws":
            return self._load_aws_config()
        else:
            return self._load_local_config()
    
    def _load_local_config(self) -> AppConfig:
        """ローカル環境の設定を読み込み"""
        self.logger.info("ローカル環境設定を読み込み中...")
        
        # 必須設定のチェック
        required_vars = [
            "GOOGLE_SHEETS_ID",
            "GEMINI_API_KEY",
            "SLACK_WEBHOOK_URL"
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"必須環境変数が設定されていません: {', '.join(missing_vars)}")
        
        # Google Sheets設定
        google_sheets_config = GoogleSheetsConfig(
            spreadsheet_id=os.getenv("GOOGLE_SHEETS_ID"),
            credentials_json_path=os.getenv("GOOGLE_CREDENTIALS_JSON_PATH", "credentials.json")
        )
        
        # Gemini設定
        gemini_config = GeminiConfig(
            api_key=os.getenv("GEMINI_API_KEY"),
            model=os.getenv("GEMINI_MODEL", "gemini-pro")
        )
        
        # Slack設定
        slack_config = SlackConfig(
            webhook_url=os.getenv("SLACK_WEBHOOK_URL"),
            channel=os.getenv("SLACK_CHANNEL", "#stock-analysis")
        )
        
        return AppConfig(
            environment=self.environment,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            google_sheets=google_sheets_config,
            gemini=gemini_config,
            slack=slack_config,
            aws_region=os.getenv("AWS_REGION", "ap-northeast-1"),
            test_mode=os.getenv("TEST_MODE", "false").lower() == "true",
            mock_external_apis=os.getenv("MOCK_EXTERNAL_APIS", "false").lower() == "true"
        )
    
    def _load_aws_config(self) -> AppConfig:
        """AWS環境の設定を読み込み"""
        self.logger.info("AWS環境設定を読み込み中...")
        
        if not self._parameter_store_client:
            raise RuntimeError("AWS SSM clientが初期化されていません")
        
        # Parameter Storeから設定を取得
        try:
            google_sheets_id = self._get_parameter("/stock-analysis/google-sheets-id")
            google_credentials = self._get_parameter("/stock-analysis/google-credentials", decrypt=True)
            gemini_api_key = self._get_parameter("/stock-analysis/gemini-api-key", decrypt=True)
            slack_webhook = self._get_parameter("/stock-analysis/slack-webhook", decrypt=True)
            
            # Google Sheets設定
            google_sheets_config = GoogleSheetsConfig(
                spreadsheet_id=google_sheets_id
            )
            
            # Gemini設定
            gemini_config = GeminiConfig(
                api_key=gemini_api_key
            )
            
            # Slack設定
            slack_config = SlackConfig(
                webhook_url=slack_webhook
            )
            
            return AppConfig(
                environment=self.environment,
                log_level=os.getenv("LOG_LEVEL", "INFO"),
                google_sheets=google_sheets_config,
                gemini=gemini_config,
                slack=slack_config,
                aws_region=os.getenv("AWS_REGION", "ap-northeast-1")
            )
            
        except Exception as e:
            self.logger.error(f"AWS設定の読み込みに失敗: {e}")
            raise
    
    def _get_parameter(self, parameter_name: str, decrypt: bool = False) -> str:
        """Parameter Storeからパラメータを取得"""
        try:
            response = self._parameter_store_client.get_parameter(
                Name=parameter_name,
                WithDecryption=decrypt
            )
            return response["Parameter"]["Value"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "ParameterNotFound":
                raise ValueError(f"パラメータが見つかりません: {parameter_name}")
            raise
    
    def validate_config(self, config: AppConfig) -> bool:
        """設定の妥当性を検証"""
        errors = []
        
        # Google Sheets設定の検証
        if not config.google_sheets.spreadsheet_id:
            errors.append("Google Sheets IDが設定されていません")
        
        # Gemini設定の検証
        if not config.gemini.api_key:
            errors.append("Gemini API keyが設定されていません")
        
        # Slack設定の検証
        if not config.slack.webhook_url or not config.slack.webhook_url.startswith("https://"):
            errors.append("有効なSlack webhook URLが設定されていません")
        
        if errors:
            error_message = "設定検証エラー:\n" + "\n".join(f"- {error}" for error in errors)
            self.logger.error(error_message)
            return False
        
        self.logger.info("設定の検証が完了しました")
        return True
    
    def get_credentials_path(self) -> Path:
        """Google Sheets認証情報ファイルのパスを取得"""
        config = self.get_config()
        creds_path = Path(config.google_sheets.credentials_json_path)
        
        if not creds_path.is_absolute():
            # 相対パスの場合はプロジェクトルートからの相対パス
            project_root = Path(__file__).parent.parent.parent
            creds_path = project_root / creds_path
        
        return creds_path
    
    def load_stock_data_from_cache(self) -> Dict[str, Any]:
        """キャッシュから株式データを読み込み"""
        cache_file = Path("stock_cache.json")
        if cache_file.exists():
            try:
                with open(cache_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.warning(f"キャッシュファイルの読み込みに失敗: {e}")
        
        return {"holdings": [], "watchlist": []}
    
    def save_stock_data_to_cache(self, data: Dict[str, Any]) -> None:
        """株式データをキャッシュに保存"""
        try:
            with open("stock_cache.json", "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.logger.info("株式データをキャッシュに保存しました")
        except Exception as e:
            self.logger.warning(f"キャッシュファイルの保存に失敗: {e}")